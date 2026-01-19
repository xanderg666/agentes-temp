"""
Cache Manager - Sistema de caché con Redis para acelerar consultas repetidas
"""
import redis
import json
import hashlib
from typing import Optional, Any
from datetime import timedelta

# Configuración de Redis
REDIS_HOST = "localhost"  # Usando Redis local (funciona correctamente)
#REDIS_HOST = "10.0.0.202"
#REDIS_HOST = "129.80.207.42"  # Public IP (old)
#REDIS_HOST = "10.0.0.163"  # New container instance private IP (Security Lists bloqueados)
REDIS_PORT = 6379
REDIS_DB = 0

# TTL por defecto para el caché (en segundos)
DEFAULT_TTL = 3600  # 1 hora
ORDS_CACHE_TTL = 1800  # 30 minutos para respuestas de ORDS

# Prefijos para las claves de caché
CACHE_PREFIX = "br_grok:"
ORDS_PREFIX = f"{CACHE_PREFIX}ords:"
SESSION_PREFIX = f"{CACHE_PREFIX}session:"


class CacheManager:
    """Gestor de caché con Redis."""
    
    def __init__(self, host: str = REDIS_HOST, port: int = REDIS_PORT, db: int = REDIS_DB):
        """
        Inicializa la conexión a Redis.
        
        Args:
            host: Host de Redis
            port: Puerto de Redis
            db: Número de base de datos
        """
        self._redis: Optional[redis.Redis] = None
        self._host = host
        self._port = port
        self._db = db
        self._connected = False
    
    def _connect(self) -> bool:
        """Intenta conectar a Redis."""
        if self._connected and self._redis:
            return True
        
        try:
            self._redis = redis.Redis(
                host=self._host,
                port=self._port,
                db=self._db,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            # Test connection
            self._redis.ping()
            self._connected = True
            print(f"✅ Conectado a Redis en {self._host}:{self._port}")
            return True
        except redis.ConnectionError as e:
            print(f"⚠️ No se pudo conectar a Redis: {e}")
            print("   El sistema funcionará sin caché.")
            self._connected = False
            return False
    
    @property
    def is_connected(self) -> bool:
        """Verifica si hay conexión activa a Redis."""
        return self._connected and self._redis is not None
    
    def _generate_key(self, prefix: str, data: str) -> str:
        """
        Genera una clave de caché única basada en el contenido.
        
        Args:
            prefix: Prefijo para la clave
            data: Datos para generar el hash
            
        Returns:
            Clave de caché única
        """
        hash_value = hashlib.md5(data.encode()).hexdigest()[:16]
        return f"{prefix}{hash_value}"
    
    def get_ords_cache(self, endpoint: str, question: str) -> Optional[dict]:
        """
        Obtiene una respuesta de ORDS del caché.
        
        Args:
            endpoint: Nombre del endpoint (runsql, narrate, agent, genai)
            question: Pregunta enviada
            
        Returns:
            Respuesta cacheada o None si no existe
        """
        if not self._connect():
            return None
        
        try:
            # Para genai, extraer la pregunta real del usuario del prompt
            cache_question = question.lower().strip()
            if endpoint == "genai" and "PREGUNTA DEL USUARIO:" in question:
                # Extraer solo la pregunta del usuario del prompt largo
                try:
                    start_idx = question.find("PREGUNTA DEL USUARIO:") + len("PREGUNTA DEL USUARIO:")
                    end_idx = question.find("Proporciona una respuesta", start_idx)
                    if end_idx == -1:
                        end_idx = len(question)
                    cache_question = question[start_idx:end_idx].strip().lower()
                except Exception:
                    # Si falla la extracción, usar la pregunta completa
                    pass
            
            key = self._generate_key(f"{ORDS_PREFIX}{endpoint}:", cache_question)
            cached = self._redis.get(key)
            
            if cached:
                print(f"🚀 CACHE HIT: {endpoint} - {cache_question[:50]}...")
                return json.loads(cached)
            
            print(f"💨 CACHE MISS: {endpoint} - {cache_question[:50]}...")
            return None
            
        except Exception as e:
            print(f"⚠️ Error al leer caché: {e}")
            return None
    
    def set_ords_cache(self, endpoint: str, question: str, response: dict, ttl: int = ORDS_CACHE_TTL) -> bool:
        """
        Guarda una respuesta de ORDS en el caché.
        
        Args:
            endpoint: Nombre del endpoint
            question: Pregunta enviada
            response: Respuesta a cachear
            ttl: Tiempo de vida en segundos
            
        Returns:
            True si se guardó correctamente
        """
        if not self._connect():
            return False
        
        try:
            # Para genai, extraer la pregunta real del usuario del prompt
            cache_question = question.lower().strip()
            if endpoint == "genai" and "PREGUNTA DEL USUARIO:" in question:
                # Extraer solo la pregunta del usuario del prompt largo
                try:
                    start_idx = question.find("PREGUNTA DEL USUARIO:") + len("PREGUNTA DEL USUARIO:")
                    end_idx = question.find("Proporciona una respuesta", start_idx)
                    if end_idx == -1:
                        end_idx = len(question)
                    cache_question = question[start_idx:end_idx].strip().lower()
                except Exception:
                    # Si falla la extracción, usar la pregunta completa
                    pass
            
            key = self._generate_key(f"{ORDS_PREFIX}{endpoint}:", cache_question)
            self._redis.setex(key, ttl, json.dumps(response, ensure_ascii=False))
            print(f"💾 CACHED: {endpoint} - TTL: {ttl}s")
            return True
            
        except Exception as e:
            print(f"⚠️ Error al guardar en caché: {e}")
            return False
    
    def get_session_history(self, session_id: str) -> Optional[list]:
        """
        Obtiene el historial de una sesión del caché.
        
        Args:
            session_id: ID de la sesión
            
        Returns:
            Lista de mensajes o None
        """
        if not self._connect():
            return None
        
        try:
            key = f"{SESSION_PREFIX}{session_id}"
            cached = self._redis.get(key)
            return json.loads(cached) if cached else None
            
        except Exception as e:
            print(f"⚠️ Error al leer sesión: {e}")
            return None
    
    def set_session_history(self, session_id: str, messages: list, ttl: int = DEFAULT_TTL) -> bool:
        """
        Guarda el historial de una sesión en el caché.
        
        Args:
            session_id: ID de la sesión
            messages: Lista de mensajes
            ttl: Tiempo de vida
            
        Returns:
            True si se guardó correctamente
        """
        if not self._connect():
            return False
        
        try:
            key = f"{SESSION_PREFIX}{session_id}"
            self._redis.setex(key, ttl, json.dumps(messages, ensure_ascii=False))
            return True
            
        except Exception as e:
            print(f"⚠️ Error al guardar sesión: {e}")
            return False
    
    def clear_ords_cache(self) -> int:
        """
        Limpia todo el caché de ORDS.
        
        Returns:
            Número de claves eliminadas
        """
        if not self._connect():
            return 0
        
        try:
            keys = self._redis.keys(f"{ORDS_PREFIX}*")
            if keys:
                return self._redis.delete(*keys)
            return 0
            
        except Exception as e:
            print(f"⚠️ Error al limpiar caché: {e}")
            return 0
    
    def clear_session(self, session_id: str) -> bool:
        """
        Limpia una sesión específica.
        
        Args:
            session_id: ID de la sesión
            
        Returns:
            True si se eliminó
        """
        if not self._connect():
            return False
        
        try:
            key = f"{SESSION_PREFIX}{session_id}"
            return bool(self._redis.delete(key))
            
        except Exception as e:
            print(f"⚠️ Error al limpiar sesión: {e}")
            return False
    
    def get_stats(self) -> dict:
        """
        Obtiene estadísticas del caché.
        
        Returns:
            Diccionario con estadísticas
        """
        if not self._connect():
            return {"connected": False}
        
        try:
            info = self._redis.info("memory")
            ords_keys = len(self._redis.keys(f"{ORDS_PREFIX}*"))
            session_keys = len(self._redis.keys(f"{SESSION_PREFIX}*"))
            
            return {
                "connected": True,
                "used_memory": info.get("used_memory_human", "N/A"),
                "ords_cached_queries": ords_keys,
                "active_sessions": session_keys,
                "total_keys": ords_keys + session_keys
            }
            
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def get_cached_entries(self, limit: int = 50) -> list[dict]:
        """
        Obtiene una lista de entradas cacheadas.
        
        Args:
            limit: Número máximo de entradas a retornar
            
        Returns:
            Lista de diccionarios con detalles de cada entrada
        """
        if not self._connect():
            return []
        
        entries = []
        try:
            # Buscar claves de ORDS
            keys = self._redis.keys(f"{ORDS_PREFIX}*")
            
            # Limitar cantidad
            keys = keys[:limit]
            
            for key in keys:
                try:
                    ttl = self._redis.ttl(key)
                    value_json = self._redis.get(key)
                    
                    if not value_json:
                        continue
                        
                    data = json.loads(value_json)
                    
                    # Intentar extraer la pregunta original si está en los datos
                    # O inferirla del key si es posible (aunque es hash)
                    question = "Desconocida"
                    
                    # Extraer endpoint del key
                    # Key format: br_grok:ords:ENDPOINT:HASH
                    parts = key.split(':')
                    endpoint = "unknown"
                    if len(parts) >= 3:
                        endpoint = parts[2]
                    
                    # Crear preview de la respuesta
                    preview = ""
                    if isinstance(data, dict):
                        if "answer" in data:
                            preview = str(data["answer"])[:100]
                        elif "data" in data and isinstance(data["data"], list) and data["data"]:
                            preview = str(data["data"][0])[:100]
                        else:
                            preview = str(data)[:100]
                    
                    entries.append({
                        "key": key,
                        "endpoint": endpoint,
                        "preview": preview,
                        "ttl": ttl,
                        "ttl_human": str(timedelta(seconds=ttl))
                    })
                    
                except Exception:
                    continue
            
            return entries
            
        except Exception as e:
            print(f"⚠️ Error al listar caché: {e}")
            return []


# Instancia global del cache manager
cache = CacheManager()
