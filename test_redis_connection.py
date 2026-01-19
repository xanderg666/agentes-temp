#!/usr/bin/env python3
"""
Script de diagnóstico para probar la conexión a Redis
"""
import socket
import sys

def test_tcp_connection(host, port, timeout=5):
    """Prueba si un puerto TCP está abierto"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except socket.error as e:
        print(f"❌ Error de socket: {e}")
        return False

def test_redis_ping(host, port):
    """Intenta hacer un PING a Redis"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        # Enviar comando PING en protocolo Redis
        sock.sendall(b"*1\r\n$4\r\nPING\r\n")
        response = sock.recv(1024)
        sock.close()
        
        # Respuesta esperada: +PONG\r\n
        if b"PONG" in response:
            return True, response.decode('utf-8', errors='ignore')
        else:
            return False, response.decode('utf-8', errors='ignore')
    except Exception as e:
        return False, str(e)

def main():
    redis_hosts = [
        ("10.0.0.163", "Nueva instancia (privada)"),
        ("localhost", "Local"),
    ]
    
    print("=" * 60)
    print("🔍 Diagnóstico de Conectividad Redis")
    print("=" * 60)
    
    for host, description in redis_hosts:
        print(f"\n📍 Probando: {host} ({description})")
        print("-" * 60)
        
        # Test 1: Puerto TCP abierto
        print(f"   [1/2] Probando conexión TCP al puerto 6379...")
        if test_tcp_connection(host, 6379):
            print(f"   ✅ Puerto 6379 está ABIERTO en {host}")
            
            # Test 2: Redis PING
            print(f"   [2/2] Enviando comando PING a Redis...")
            success, response = test_redis_ping(host, 6379)
            if success:
                print(f"   ✅ Redis responde correctamente: {response.strip()}")
            else:
                print(f"   ⚠️  Redis no responde correctamente: {response}")
        else:
            print(f"   ❌ Puerto 6379 está CERRADO en {host}")
            print(f"   💡 Posibles causas:")
            print(f"      - Security Lists en OCI no permiten tráfico al puerto 6379")
            print(f"      - Redis no está corriendo en el container")
            print(f"      - Redis está escuchando solo en localhost (127.0.0.1)")
    
    print("\n" + "=" * 60)
    print("📋 Resumen de Acciones Necesarias")
    print("=" * 60)
    print("""
1. Verifica los Security Lists en OCI Console:
   - Ve a: Container Instances → Tu instancia → Subnet → Security Lists
   - Busca regla de ingress para puerto 6379
   - Si no existe, agrégala:
     * Source CIDR: 10.0.0.0/16
     * Protocol: TCP
     * Destination Port: 6379

2. Verifica que Redis esté corriendo con la configuración correcta:
   - Conéctate al container instance
   - Ejecuta: docker logs <container-id>
   - Verifica que Redis esté escuchando en 0.0.0.0:6379

3. Consulta la guía completa en: redis_diagnostico.md
""")

if __name__ == "__main__":
    main()
