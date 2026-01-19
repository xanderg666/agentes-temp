"""
API Memory Cached - Flask API con soporte de memoria y caché Redis
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import time
import os

import main_memory_cached as main_cached

app = Flask(__name__)
CORS(app)


@app.route('/')
def index():
    """Sirve la interfaz web HTML."""
    return send_from_directory('.', 'index_cached.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Endpoint principal para chat con memoria y caché.
    
    Body JSON:
        - question (requerido): Pregunta del usuario
        - session_id (opcional): ID de sesión (default: "default")
    """
    try:
        data = request.get_json()
        if not data or 'question' not in data:
            return jsonify({"error": "Falta el campo 'question' en el body"}), 400
        
        question = data['question']
        session_id = data.get('session_id', 'default')
        
        start_time = time.time()
        
        response = main_cached.process_question_with_cache(question, session_id)
        
        elapsed_time = time.time() - start_time
        
        # Imprimir en consola
        cache_status = "🚀 CACHE HIT" if response.get("from_cache") else "💨 CACHE MISS"
        print(f"\n{cache_status}")
        print(f"⏱️  Tiempo total: {round(elapsed_time, 2)}s")
        
        # Limpiar campos internos de la respuesta
        response.pop('processing_time_ms', None)
        response.pop('processing_time_seconds', None)
        
        return jsonify(response)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/reset', methods=['POST'])
def reset():
    """Endpoint para limpiar la memoria de una sesión."""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id', 'default')
        
        result = main_cached.reset_memory(session_id)
        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/cache/stats', methods=['GET'])
def cache_stats():
    """Obtiene estadísticas del caché Redis."""
    try:
        stats = main_cached.get_cache_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/cache/clear', methods=['POST'])
def cache_clear():
    """Limpia todo el caché de ORDS."""
    try:
        result = main_cached.clear_all_cache()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/cache/entries', methods=['GET'])
def cache_entries():
    """Obtiene lista de entradas en el caché."""
    try:
        limit = int(request.args.get('limit', 50))
        entries = main_cached.cache.get_cached_entries(limit)
        return jsonify(entries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    stats = main_cached.get_cache_stats()
    return jsonify({
        "status": "ok",
        "service": "LangChain Llama Agent API (with Memory + Redis Cache)",
        "features": ["conversation_memory", "session_management", "redis_cache"],
        "cache": stats
    })


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 Iniciando servidor Flask con Memoria + Caché Redis")
    print("="*60)
    
    # Verificar conexión a Redis
    stats = main_cached.get_cache_stats()
    if stats.get("connected"):
        print(f"✅ Redis conectado")
        print(f"   - Memoria usada: {stats.get('used_memory', 'N/A')}")
        print(f"   - Queries cacheadas: {stats.get('ords_cached_queries', 0)}")
    else:
        print("⚠️  Redis NO disponible - Funcionando sin caché")
        print("   Para activar caché, ejecuta: docker-compose up -d")
    
    print("\n📡 Endpoints disponibles:")
    print("   POST /api/chat        - Chat con memoria y caché")
    print("   POST /api/reset       - Limpiar memoria de sesión")
    print("   GET  /api/cache/stats - Estadísticas del caché")
    print("   POST /api/cache/clear - Limpiar todo el caché")
    print("   GET  /health          - Health check")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5001, debug=True)
