"""
Cache Warmup - Pre-carga consultas comunes en Redis para acelerar respuestas iniciales

Este script consulta la API de ORDS para obtener datos comunes (como TRM del último mes)
y los almacena en el caché de Redis antes de que los usuarios los soliciten.

Uso:
    python cache_warmup.py                          # Ejecutar warmup completo (últimos 30 días)
    python cache_warmup.py --trm                    # Solo TRM del último mes
    python cache_warmup.py --month 1 --year 2025    # Warmup de enero 2025
    python cache_warmup.py --csv datos_trm.csv      # Cargar desde archivo CSV
    python cache_warmup.py --schedule 30            # Programar cada 30 minutos
"""

import requests
import json
import calendar
import locale
import csv
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import argparse
import time
import sys

# Nombres de meses en español
MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}

import config
from cache_manager import cache, ORDS_CACHE_TTL

# Configuración del warmup
WARMUP_TTL = 7200  # 2 horas - mayor TTL para datos pre-cargados


class CacheWarmup:
    """Gestor de pre-carga de caché."""
    
    def __init__(self):
        self.base_url = config.ORDS_BASE_URL
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
    
    def _call_ords(self, endpoint: str, question: str) -> Optional[dict]:
        """
        Llama a la API de ORDS y retorna la respuesta.
        """
        url = f"{self.base_url}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        payload = {"question": question}
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            
            try:
                result = response.json()
                # Envolver listas en diccionario
                if isinstance(result, list):
                    result = {"data": result}
                return result
            except json.JSONDecodeError:
                return {"answer": response.text}
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Error: {e}")
            return None
    
    def warmup_query(self, endpoint: str, question: str, ttl: int = WARMUP_TTL) -> bool:
        """
        Pre-carga una consulta específica en el caché.
        
        Returns:
            True si se guardó en caché, False si falló o ya existía
        """
        self.stats["total"] += 1
        
        # Verificar si ya está en caché
        existing = cache.get_ords_cache(endpoint, question)
        if existing:
            print(f"   ⏭️  Ya en caché: {question[:60]}...")
            self.stats["skipped"] += 1
            return False
        
        print(f"   🔄 Consultando: {question[:60]}...")
        result = self._call_ords(endpoint, question)
        
        if result and "error" not in result:
            success = cache.set_ords_cache(endpoint, question, result, ttl)
            if success:
                self.stats["success"] += 1
                return True
        
        self.stats["failed"] += 1
        return False
    
    def cache_direct(self, endpoint: str, question: str, response: Dict[str, Any], ttl: int = WARMUP_TTL) -> bool:
        """
        Guarda directamente una respuesta en caché sin llamar a la API.
        
        Args:
            endpoint: Endpoint simulado (runsql, narrate, etc.)
            question: Pregunta que se cacheará
            response: Respuesta a guardar
            ttl: Tiempo de vida en segundos
        """
        self.stats["total"] += 1
        
        # Verificar si ya está en caché
        existing = cache.get_ords_cache(endpoint, question)
        if existing:
            self.stats["skipped"] += 1
            return False
        
        success = cache.set_ords_cache(endpoint, question, response, ttl)
        if success:
            self.stats["success"] += 1
            return True
        
        self.stats["failed"] += 1
        return False
    
    def warmup_from_csv(self, csv_path: str, date_column: str = None, value_column: str = None, 
                        filter_month: int = None, filter_year: int = None,
                        endpoint: str = "runsql", ttl: int = WARMUP_TTL) -> int:
        """
        Pre-carga datos TRM/UVR desde un archivo CSV directamente al caché.
        No llama a la API, inserta directamente los datos en Redis.
        
        Args:
            csv_path: Ruta al archivo CSV
            date_column: Nombre de la columna de fecha (auto-detecta si no se especifica)
            value_column: Nombre de la columna de valor (auto-detecta si no se especifica)
            filter_month: Filtrar solo este mes (1-12)
            filter_year: Filtrar solo este año
            endpoint: Endpoint para la clave de caché
            ttl: Tiempo de vida en segundos
            
        Returns:
            Número de registros cacheados exitosamente
        """
        if not os.path.exists(csv_path):
            print(f"❌ Archivo no encontrado: {csv_path}")
            return 0
        
        print(f"\n🔥 Cargando datos desde CSV: {csv_path}")
        print("=" * 60)
        
        cached_count = 0
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                # Detectar el delimitador
                sample = f.read(2048)
                f.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=',;')
                
                reader = csv.DictReader(f, dialect=dialect)
                headers = reader.fieldnames
                
                # Auto-detectar columnas si no se especificaron
                if not date_column:
                    date_column = headers[0]  # Primera columna es fecha
                if not value_column:
                    value_column = headers[1]  # Segunda columna es valor
                
                print(f"   📅 Columna fecha: {date_column}")
                print(f"   💰 Columna valor: {value_column}")
                
                # Detectar tipo de dato (TRM o UVR) del nombre de la columna
                is_trm = "trm" in value_column.lower() or "tasa" in value_column.lower()
                data_type = "TRM" if is_trm else "UVR"
                
                processed = 0
                skipped_filter = 0
                
                for row in reader:
                    try:
                        # Parsear fecha (formato: mm/dd/yyyy)
                        date_str = row[date_column]
                        
                        # Intentar varios formatos de fecha
                        date_obj = None
                        for fmt in ['%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d']:
                            try:
                                date_obj = datetime.strptime(date_str, fmt)
                                break
                            except ValueError:
                                continue
                        
                        if not date_obj:
                            continue
                        
                        # Filtrar por mes/año si se especificó
                        if filter_month and date_obj.month != filter_month:
                            skipped_filter += 1
                            continue
                        if filter_year and date_obj.year != filter_year:
                            skipped_filter += 1
                            continue
                        
                        # Obtener valor
                        value = float(row[value_column].replace(',', '.'))
                        
                        # Preparar respuesta simulada
                        mes_nombre = MESES_ES.get(date_obj.month, "")
                        date_formatted = f"{date_obj.day} de {mes_nombre} del {date_obj.year}"
                        
                        response = {
                            "answer": f"La {data_type} del {date_formatted} fue de {value:,.2f}",
                            "data": [{
                                "fecha": date_obj.strftime("%Y-%m-%d"),
                                "valor": value,
                                "tipo": data_type
                            }],
                            "_source": "csv_warmup"
                        }
                        
                        # Generar variantes de preguntas y cachear
                        questions = [
                            f"cual fue la {data_type.lower()} del {date_formatted}",
                            f"{data_type.lower()} del {date_formatted}",
                            f"dame la {data_type.lower()} del {date_formatted}",
                        ]
                        
                        for question in questions:
                            if self.cache_direct(endpoint, question, response, ttl):
                                cached_count += 1
                        
                        processed += 1
                        
                        # Mostrar progreso cada 50 registros
                        if processed % 50 == 0:
                            print(f"   📊 Procesados: {processed} registros...")
                            
                    except (ValueError, KeyError) as e:
                        continue
                
                # Resumen
                print(f"\n   ✅ Procesados: {processed} registros")
                if skipped_filter > 0:
                    print(f"   ⏭️  Filtrados (fuera del rango): {skipped_filter}")
                print(f"   💾 Cacheados: {cached_count} consultas")
                
        except Exception as e:
            print(f"❌ Error al procesar CSV: {e}")
            import traceback
            traceback.print_exc()
        
        return cached_count
    
    def warmup_trm_range(self, days: int = 30, endpoint: str = "runsql") -> int:
        """
        Pre-carga las consultas de TRM para un rango de días.
        
        Args:
            days: Número de días hacia atrás desde hoy
            endpoint: Endpoint a usar (runsql para datos crudos)
            
        Returns:
            Número de consultas exitosamente cacheadas
        """
        print(f"\n🔥 Iniciando warmup de TRM para los últimos {days} días...")
        
        today = datetime.now()
        cached_count = 0
        
        # Generar consultas para cada día
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%d de %B del %Y")
            date_str_alt = date.strftime("%Y-%m-%d")
            
            # Variantes de preguntas comunes
            questions = [
                f"cual fue la trm del {date_str}",
                f"trm del {date_str}",
                f"dame la trm del {date_str}",
            ]
            
            for question in questions:
                if self.warmup_query(endpoint, question):
                    cached_count += 1
                # Pequeña pausa para no sobrecargar la API
                time.sleep(0.5)
        
        return cached_count
    
    def warmup_uvr_range(self, days: int = 30, endpoint: str = "runsql") -> int:
        """
        Pre-carga las consultas de UVR para un rango de días.
        """
        print(f"\n🔥 Iniciando warmup de UVR para los últimos {days} días...")
        
        today = datetime.now()
        cached_count = 0
        
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%d de %B del %Y")
            
            questions = [
                f"cual fue la uvr del {date_str}",
                f"uvr del {date_str}",
            ]
            
            for question in questions:
                if self.warmup_query(endpoint, question):
                    cached_count += 1
                time.sleep(0.5)
        
        return cached_count
    
    def warmup_common_queries(self, endpoint: str = "runsql") -> int:
        """
        Pre-carga consultas comunes frecuentes.
        """
        print(f"\n🔥 Iniciando warmup de consultas comunes...")
        
        common_queries = [
            # TRM
            "cual es la trm de hoy",
            "trm actual",
            "valor del dolar hoy",
            "trm del dia de hoy",
            "dame la trm de hoy",
            
            # UVR
            "cual es la uvr de hoy",
            "uvr actual",
            "valor de la uvr hoy",
            
            # Comparativos
            "trm del mes pasado",
            "promedio trm del ultimo mes",
            "trm mas alta del año",
            "trm mas baja del año",
        ]
        
        cached_count = 0
        for question in common_queries:
            if self.warmup_query(endpoint, question):
                cached_count += 1
            time.sleep(0.5)
        
        return cached_count
    
    def warmup_yearly_comparisons(self, years: List[int] = None) -> int:
        """
        Pre-carga comparaciones anuales.
        """
        if years is None:
            current_year = datetime.now().year
            years = [current_year, current_year - 1]
        
        print(f"\n🔥 Iniciando warmup de comparaciones anuales ({years})...")
        
        cached_count = 0
        
        for year in years:
            questions = [
                f"trm promedio del {year}",
                f"cual fue la trm en enero del {year}",
                f"trm del 1 de enero del {year}",
                f"trm del 20 de enero del {year}",
            ]
            
            for question in questions:
                if self.warmup_query("runsql", question):
                    cached_count += 1
                time.sleep(0.5)
        
        return cached_count
    
    def warmup_month(self, month: int, year: int, endpoint: str = "runsql") -> int:
        """
        Pre-carga las consultas de TRM y UVR para un mes específico.
        
        Args:
            month: Número del mes (1-12)
            year: Año (ej: 2025)
            endpoint: Endpoint a usar
            
        Returns:
            Número de consultas exitosamente cacheadas
        """
        mes_nombre = MESES_ES.get(month, "")
        if not mes_nombre:
            print(f"❌ Mes inválido: {month}")
            return 0
        
        # Obtener el número de días en el mes
        dias_en_mes = calendar.monthrange(year, month)[1]
        
        print(f"\n🔥 Iniciando warmup de {mes_nombre.upper()} {year} ({dias_en_mes} días)...")
        print("=" * 60)
        
        cached_count = 0
        
        for dia in range(1, dias_en_mes + 1):
            # Formato: "20 de enero del 2025"
            date_str = f"{dia} de {mes_nombre} del {year}"
            
            # Variantes de preguntas para TRM
            trm_questions = [
                f"cual fue la trm del {date_str}",
                f"trm del {date_str}",
                f"dame la trm del {date_str}",
            ]
            
            # Variantes de preguntas para UVR
            uvr_questions = [
                f"cual fue la uvr del {date_str}",
                f"uvr del {date_str}",
            ]
            
            # Procesar TRM
            for question in trm_questions:
                if self.warmup_query(endpoint, question):
                    cached_count += 1
                time.sleep(0.3)
            
            # Procesar UVR
            for question in uvr_questions:
                if self.warmup_query(endpoint, question):
                    cached_count += 1
                time.sleep(0.3)
        
        # Agregar consultas comparativas del mes
        comparaciones = [
            f"trm promedio de {mes_nombre} del {year}",
            f"trm mas alta de {mes_nombre} del {year}",
            f"trm mas baja de {mes_nombre} del {year}",
            f"cual fue la trm en {mes_nombre} del {year}",
            f"uvr promedio de {mes_nombre} del {year}",
        ]
        
        print(f"\n   📊 Cargando consultas comparativas del mes...")
        for question in comparaciones:
            if self.warmup_query(endpoint, question):
                cached_count += 1
            time.sleep(0.3)
        
        return cached_count
    
    def run_full_warmup(self, days: int = 30) -> dict:
        """
        Ejecuta el warmup completo.
        """
        start_time = time.time()
        print("=" * 60)
        print("🚀 CACHE WARMUP - Banco República")
        print("=" * 60)
        
        # Verificar conexión a Redis
        if not cache.is_connected:
            print("❌ No se pudo conectar a Redis. Abortando warmup.")
            return self.stats
        
        # Ejecutar warmups
        self.warmup_common_queries()
        self.warmup_trm_range(days)
        self.warmup_uvr_range(min(days, 7))  # UVR solo últimos 7 días
        self.warmup_yearly_comparisons()
        
        elapsed = time.time() - start_time
        
        # Resumen
        print("\n" + "=" * 60)
        print("📊 RESUMEN DEL WARMUP")
        print("=" * 60)
        print(f"   Total consultas procesadas: {self.stats['total']}")
        print(f"   ✅ Exitosas (nuevas en caché): {self.stats['success']}")
        print(f"   ⏭️  Ya existían en caché: {self.stats['skipped']}")
        print(f"   ❌ Fallidas: {self.stats['failed']}")
        print(f"   ⏱️  Tiempo total: {elapsed:.2f} segundos")
        print("=" * 60)
        
        return self.stats
    
    def print_stats(self):
        """Imprime estadísticas del caché actual."""
        stats = cache.get_stats()
        print("\n📊 Estado actual del caché:")
        for key, value in stats.items():
            print(f"   {key}: {value}")


def main():
    parser = argparse.ArgumentParser(
        description="Cache Warmup - Pre-carga consultas comunes en Redis"
    )
    parser.add_argument(
        "--trm", action="store_true",
        help="Solo calentar consultas de TRM"
    )
    parser.add_argument(
        "--uvr", action="store_true", 
        help="Solo calentar consultas de UVR"
    )
    parser.add_argument(
        "--common", action="store_true",
        help="Solo calentar consultas comunes"
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Número de días para el rango (default: 30)"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Solo mostrar estadísticas del caché"
    )
    parser.add_argument(
        "--schedule", type=int, metavar="MINUTES",
        help="Ejecutar warmup cada N minutos"
    )
    parser.add_argument(
        "--month", type=int, choices=range(1, 13), metavar="1-12",
        help="Mes específico para warmup (1=enero, 12=diciembre)"
    )
    parser.add_argument(
        "--year", type=int, default=datetime.now().year,
        help=f"Año para el warmup (default: {datetime.now().year})"
    )
    parser.add_argument(
        "--csv", type=str, metavar="FILE",
        help="Ruta al archivo CSV con datos TRM/UVR para cargar directamente"
    )
    
    args = parser.parse_args()
    warmup = CacheWarmup()
    
    if args.stats:
        warmup.print_stats()
        return
    
    if args.schedule:
        print(f"🔄 Modo programado: ejecutando cada {args.schedule} minutos")
        print("   Presiona Ctrl+C para detener\n")
        
        while True:
            try:
                warmup.run_full_warmup(args.days)
                print(f"\n💤 Esperando {args.schedule} minutos para el próximo ciclo...")
                time.sleep(args.schedule * 60)
                # Reset stats para el siguiente ciclo
                warmup.stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0}
            except KeyboardInterrupt:
                print("\n\n👋 Warmup programado detenido.")
                break
        return
    
    # Si se especifica un archivo CSV
    if args.csv:
        filter_month = args.month if args.month else None
        filter_year = args.year if args.month else None  # Solo filtrar año si se especificó mes
        
        print("=" * 60)
        print("📂 CACHE WARMUP DESDE CSV")
        print("=" * 60)
        
        warmup.warmup_from_csv(
            csv_path=args.csv,
            filter_month=filter_month,
            filter_year=filter_year
        )
    # Si se especifica un mes específico (sin CSV)
    elif args.month:
        print(f"\n🗓️  Warmup para {MESES_ES[args.month].upper()} {args.year}")
        warmup.warmup_month(args.month, args.year)
    elif args.trm:
        warmup.warmup_trm_range(args.days)
    elif args.uvr:
        warmup.warmup_uvr_range(args.days)
    elif args.common:
        warmup.warmup_common_queries()
    else:
        # Warmup completo
        warmup.run_full_warmup(args.days)
    
    warmup.print_stats()


if __name__ == "__main__":
    main()
