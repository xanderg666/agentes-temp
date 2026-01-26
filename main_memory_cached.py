"""
Main Memory Cached - Agente con memoria y caché Redis
Versión optimizada que cachea respuestas de ORDS para acelerar consultas repetidas.
"""
import requests
import json
import time
from typing import Literal, Any, Dict, List, Union
from pydantic import BaseModel, Field
from langchain_community.chat_models import ChatOCIGenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

import config
from memory_manager import get_session_history, clear_session
from cache_manager import cache

# 1. Configuración del LLM (Llama en OCI)
llm = ChatOCIGenAI(
    model_id=config.MODEL_ID,
    service_endpoint=config.SERVICE_ENDPOINT,
    compartment_id=config.COMPARTMENT_ID,
    provider="cohere",
    model_kwargs={
        "temperature": 0.1,
        "max_tokens": 4000,
    },
    auth_type="API_KEY",
    auth_profile=config.AUTH_PROFILE
)


# 2. Definición de la Estructura de Decisión (Router)
class RouteDecision(BaseModel):
    """Decide qué endpoint utilizar basado en la pregunta del usuario."""
    endpoint: Literal["runsql", "narrate", "agent", "genai"] = Field(
        ..., 
        description="El endpoint a utilizar: 'runsql' para datos crudos, 'narrate' para explicaciones, 'agent' para análisis complejos, 'genai' para respuestas con contexto existente."
    )
    needs_new_data: bool = Field(
        ...,
        description="True si la pregunta requiere consultar NUEVOS datos de la base. False si puede responder con el contexto/datos ya proporcionados en la conversación."
    )
    reasoning: str = Field(
        ..., 
        description="Breve justificación de por qué se eligió este endpoint."
    )


# 3. Prompt para reformular la pregunta considerando el historial
contextualize_prompt = ChatPromptTemplate.from_messages([
    ("system", """Eres un asistente del Banco República. Tu tarea es reformular la pregunta del usuario 
considerando el historial de la conversación para que sea una pregunta independiente y clara.

Si la pregunta hace referencia a algo mencionado antes (como "eso", "lo anterior", "comparalo con", etc.),
debes reformularla incluyendo el contexto necesario.

Si la pregunta ya es clara y no depende del contexto, devuélvela tal cual.

Solo responde con la pregunta reformulada, sin explicaciones adicionales."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{question}"),
])

# 4. Prompt del Router
router_prompt = ChatPromptTemplate.from_messages([
    ("system", """Eres un sistema de enrutamiento inteligente para un asistente del Banco República (Colombia).
    
Tienes acceso a 4 endpoints. DEBES elegir el más apropiado según estas reglas:

1. **runsql**: Para obtener datos crudos o realizar consultas específicas sobre indicadores.
   - REGLA CRÍTICA: Siempre que se pida un indicador económico (TRM, Inflación, UVR, etc.), usa este endpoint para obtener la integridad de los datos.
   - Para INFLACIÓN: Pide siempre que se incluyan los conceptos o divisiones de gasto para evitar ambigüedad.
   - Ejemplos: "¿Cuál es la TRM hoy?", "¿Inflación de enero 2025?", "Valores de la UVR"
   - needs_new_data: SIEMPRE True

2. **narrate**: Para explicaciones detalladas que requieren nuevos datos de la base.
   - Úsalo cuando el usuario pida "explicar", "narrar" o "contar la historia" de un dato.
   - Ejemplo: "Nárrate la evolución de la inflación este año"
   - needs_new_data: True

3. **agent**: Para comparaciones o análisis complejos entre múltiples indicadores.
   - Ejemplo: "Compara la TRM contra la inflación de los últimos 6 meses"
   - needs_new_data: True

4. **genai**: Para responder basándose ÚNICAMENTE en la información que ya aparece en el historial.
   - Ejemplo: "Resume los datos anteriores", "¿Qué opinas de esos números?", "Explícame ese resultado"
   - needs_new_data: False

NOTAS IMPORTANTES:
- Si el usuario pide un valor de "Enero", asume que quiere el detalle diario/mensual disponible.
- No omitas información descriptiva. Los datos deben ser íntegros (incluyendo conceptos, series y metadatos).
- Si hay datos en contexto → genai. Si faltan datos → runsql/narrate/agent."""),
    ("human", "{question}"),
])

# Crear LLM estructurado para routing
router_llm = llm.with_structured_output(RouteDecision)


def standardize_response(response_data: Any) -> dict:
    """
    Normaliza la respuesta de la API para garantizar una estructura consistente.
    Objetivo: { "datos": [ { "fecha": "...", "serie": "...", "valor": ..., "metadatos...": "..." } ] }
    Preserva todas las columnas originales para no perder integridad (como Conceptos).
    """
    if not isinstance(response_data, (dict, list)):
        return {"response": str(response_data)}
    
    content = response_data
    
    # 1. Desempaquetar wrappers (RESULTADO, JSONRESPONSE, etc.)
    wrappers = ["RESULTADO", "JSONRESPONSE", "RESPUESTA", "resultado", "jsonresponse", "respuesta"]
    
    for _ in range(3):
        if isinstance(content, dict):
            found = False
            # Intentar encontrar cualquier clave que sea uno de los wrappers
            current_keys = {k.upper(): k for k in content.keys()}
            for w in wrappers:
                if w.upper() in current_keys:
                    content = content[current_keys[w.upper()]]
                    found = True
                    break
            if not found:
                break
        else:
            break
            
    # 2. Estructurar como "datos" o "narrative"
    final_result = {}
    
    if isinstance(content, list):
        final_result["datos"] = content
    elif isinstance(content, dict):
        # Buscar narrativa
        for k in content.keys():
            if "narrative" in k.lower() or "narrativa" in k.lower():
                final_result["narrative"] = content[k]
        
        # Buscar datos
        if "datos" in content:
            final_result["datos"] = content["datos"]
        elif "data" in content:
            final_result["datos"] = content["data"]
        elif "items" in content:
             final_result["datos"] = content["items"]
        
        # Si no se encontró estructura, pero es un dict con claves tipo datos
        if "datos" not in final_result and "narrative" not in final_result:
             keys_str = str(content.keys()).lower()
             if any(x in keys_str for x in ["fecha", "valor", "serie", "trm", "uvr", "ipc"]):
                 final_result["datos"] = [content]
             else:
                 final_result.update(content)
    
    # 3. Normalizar campos internos de 'datos' SIN ELIMINAR columnas originales
    if "datos" in final_result and isinstance(final_result["datos"], list):
        normalized_rows = []
        for row in final_result["datos"]:
            if not isinstance(row, dict):
                normalized_rows.append(row)
                continue
            
            # Copiamos todo el registro original para no perder columnas (ej: Conceptos)
            new_row = row.copy()
            
            # Agregamos alias estandarizados si no existen
            for k, v in row.items():
                k_clean = k.lower().strip()
                if k_clean in ["fecha", "date", "periodo", "time"] and "fecha" not in new_row:
                    new_row["fecha"] = v
                elif k_clean in ["valor", "value", "amount", "precio"] and "valor" not in new_row:
                    new_row["valor"] = v
                elif k_clean in ["serie", "series", "concepto", "concept", "name"] and "serie" not in new_row:
                    new_row["serie"] = v
            
            normalized_rows.append(new_row)
        final_result["datos"] = normalized_rows
        
    return final_result


# 5. Función para llamar a las APIs con CACHÉ
def call_ords_api_cached(endpoint: str, question: str) -> dict:
    """
    Llama al endpoint ORDS con soporte de caché Redis.
    Primero busca en caché, si no existe, consulta la API y guarda en caché.
    """
    
    # Intentar obtener del caché primero
    cached_response = cache.get_ords_cache(endpoint, question)
    if cached_response is not None:
        # Asegurar que sea un diccionario para poder agregar metadatos
        if isinstance(cached_response, list):
            cached_response = {"datos": cached_response}
        cached_response["_from_cache"] = True
        return cached_response
    
    # No está en caché, llamar a la API
    url = f"{config.ORDS_BASE_URL}/{endpoint}"
    headers = {"Content-Type": "application/json"}
    payload = {"question": question}
    
    print(f"\n--- Llamando al endpoint: {endpoint.upper()} ---")
    print(f"URL: {url}")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        # Manejar errores de buffer o de base de datos que vienen en el body
        if response.status_code != 200:
            error_data = {"error": f"HTTP {response.status_code}", "details": response.text}
            # Intentar buscar JSON embebido en el texto de error (común en errores de buffer de Oracle)
            if "{" in response.text:
                try:
                    start_idx = response.text.find("{")
                    end_idx = response.text.rfind("}") + 1
                    embedded_data = json.loads(response.text[start_idx:end_idx])
                    return standardize_response(embedded_data)
                except:
                    pass
            return error_data

        try:
            result = response.json()
        except json.JSONDecodeError:
            # Si no es JSON, podría ser un texto largo que necesitamos
            return {"answer": response.text}
        
        # --- ESTANDARIZACIÓN DE RESPUESTA ---
        result = standardize_response(result)
        # ------------------------------------
        
        # Manejar respuestas con errores pero datos embebidos (ej: ORA-06502)
        if isinstance(result, dict) and ("error" in result or "details" in result):
            details = str(result.get("details", "") or result.get("error", ""))
            if "{" in details:
                try:
                    start_idx = details.find("{")
                    end_idx = details.rfind("}") + 1
                    embedded_json = details[start_idx:end_idx]
                    embedded_data = json.loads(embedded_json)
                    result = standardize_response(embedded_data)
                    result["_warning"] = "Datos extraídos de un mensaje de error/buffer"
                except:
                    pass
        
        # Guardar en caché
        if isinstance(result, dict) and "error" not in result:
            cache.set_ords_cache(endpoint, question, result)
        
        result["_from_cache"] = False
        return result
        
    except requests.exceptions.RequestException as e:
        return {"error": str(e), "details": "Error de conexión con la API ORDS", "_from_cache": False}


# 6. Lógica Principal del Agente con Memoria y Caché
def process_question_with_cache(question: str, session_id: str = "default") -> dict:
    """
    Procesa una pregunta manteniendo el historial de la conversación.
    Utiliza caché Redis para acelerar consultas repetidas.
    
    Args:
        question: Pregunta del usuario
        session_id: ID de la sesión para mantener el historial separado
        
    Returns:
        Respuesta estructurada con decisión y resultado
    """
    start_time = time.time()
    
    print(f"\n>>> Procesando pregunta (sesión: {session_id}): {question}")
    
    # Obtener historial de la sesión
    history = get_session_history(session_id)
    has_history = len(history.messages) > 0
    
    # Paso 1: Reformular la pregunta considerando el historial
    print("... Contextualizando pregunta ...")
    
    context_summary = ""
    if has_history:
        recent_messages = history.messages[-4:]
        context_summary = "\n".join([f"- {msg.content[:200]}..." if len(msg.content) > 200 else f"- {msg.content}" for msg in recent_messages])
        
        contextualize_chain = contextualize_prompt | llm
        standalone_response = contextualize_chain.invoke({
            "chat_history": history.messages,
            "question": question
        })
        standalone_question = standalone_response.content.strip()
        print(f"Pregunta reformulada: {standalone_question}")
    else:
        standalone_question = question
    
    # Paso 2: Decidir ruta incluyendo información del contexto disponible
    print("... Pensando ruta ...")
    chain = router_prompt | router_llm
    
    if has_history:
        routing_question = f"{question}\n\n[CONTEXTO DISPONIBLE EN MEMORIA]:\n{context_summary}"
    else:
        routing_question = f"{question}\n\n[SIN CONTEXTO PREVIO - Primera pregunta de la sesión]"
    
    decision = chain.invoke({"question": routing_question})
    
    print(f"Decisión: {decision.endpoint}")
    print(f"Necesita datos nuevos: {decision.needs_new_data}")
    print(f"Razonamiento: {decision.reasoning}")
    
    # Paso 3: Ejecutar según la decisión (con caché)
    from_cache = False
    
    if not decision.needs_new_data and has_history:
        print("\n--- Usando GENAI con contexto existente ---")
        context_for_genai = "\n".join([msg.content for msg in history.messages[-6:]])
        genai_question = f"""Basándote en el siguiente contexto de la conversación, responde la pregunta del usuario.

        CONTEXTO DE LA CONVERSACIÓN:
        {context_for_genai}

        PREGUNTA DEL USUARIO: {question}

        Proporciona una respuesta clara y útil basándote ÚNICAMENTE en el contexto proporcionado."""
        
        result = call_ords_api_cached("genai", genai_question)
    else:
        result = call_ords_api_cached(decision.endpoint, standalone_question)
    
    # Verificar si vino del caché
    from_cache = result.pop("_from_cache", False)
    
    # Paso 4: Guardar en historial
    history.add_user_message(question)
    
    if isinstance(result, dict):
        answer_text = result.get("answer", result.get("response", json.dumps(result, ensure_ascii=False)))
    else:
        answer_text = str(result)
    history.add_ai_message(answer_text)
    
    # Calcular tiempo
    elapsed_time = time.time() - start_time
    
    return {
        "question": question,
        "standalone_question": standalone_question,
        "decision": {
            "endpoint": decision.endpoint if decision.needs_new_data else "genai",
            "needs_new_data": decision.needs_new_data,
            "reasoning": decision.reasoning
        },
        "result": result,
        "from_cache": from_cache,
        "session_id": session_id,
        "processing_time_ms": round(elapsed_time * 1000, 2),
        "processing_time_seconds": round(elapsed_time, 2)
    }


def reset_memory(session_id: str = "default") -> dict:
    """Limpia la memoria de una sesión."""
    success = clear_session(session_id)
    cache.clear_session(session_id)
    return {
        "session_id": session_id,
        "cleared": success,
        "message": "Memoria limpiada exitosamente" if success else "Sesión no encontrada"
    }


def get_cache_stats() -> dict:
    """Obtiene estadísticas del caché."""
    return cache.get_stats()


def clear_all_cache() -> dict:
    """Limpia todo el caché de ORDS."""
    count = cache.clear_ords_cache()
    return {"cleared_keys": count, "message": f"Se eliminaron {count} entradas del caché"}


# --- Ejecución de Ejemplo (CLI) ---
if __name__ == "__main__":
    print("=== Agente Banco República con Memoria y Caché Redis (CLI) ===")
    print("\nComandos especiales:")
    print("  'salir' - Terminar")
    print("  'limpiar' - Limpiar memoria de la sesión")
    print("  'limpiar cache' - Limpiar todo el caché")
    print("  'stats' - Ver estadísticas del caché")
    print("  'nueva sesion <id>' - Cambiar a una nueva sesión")
    print()
    
    # Mostrar estado del caché
    stats = get_cache_stats()
    if stats.get("connected"):
        print(f"✅ Redis conectado - Caché activo")
    else:
        print(f"⚠️ Redis no disponible - Funcionando sin caché")
    
    current_session = "cli_cached"
    
    while True:
        try:
            user_input = input(f"\n[{current_session}] Tu pregunta: ").strip()
            
            if user_input.lower() in ['salir', 'exit', 'quit']:
                break
            
            if user_input.lower() == 'limpiar':
                result = reset_memory(current_session)
                print(f"✓ {result['message']}")
                continue
            
            if user_input.lower() == 'limpiar cache':
                result = clear_all_cache()
                print(f"✓ {result['message']}")
                continue
            
            if user_input.lower() == 'stats':
                stats = get_cache_stats()
                print("\n📊 Estadísticas del Caché:")
                for key, value in stats.items():
                    print(f"   {key}: {value}")
                for key, value in stats.items():
                    print(f"   {key}: {value}")
                continue
            
            if user_input.lower() == 'ver cache':
                entries = cache.get_cached_entries(20)
                print(f"\n📋 Últimas {len(entries)} entradas en caché:")
                print(f"{'ENDPOINT':<10} | {'TTL':<10} | {'PREVIEW'}")
                print("-" * 60)
                for entry in entries:
                    print(f"{entry['endpoint']:<10} | {entry['ttl_human']:<10} | {entry['preview']}")
                continue
            
            if user_input.lower().startswith('nueva sesion '):
                new_session = user_input[13:].strip()
                if new_session:
                    current_session = new_session
                    print(f"✓ Cambiado a sesión: {current_session}")
                continue
            
            if not user_input:
                continue
            
            response = process_question_with_cache(user_input, current_session)
            
            print("\n>>> Resultado:")
            print(json.dumps(response["result"], indent=2, ensure_ascii=False))
            
            cache_indicator = "🚀 FROM CACHE" if response["from_cache"] else "💨 FROM API"
            print(f"\n{cache_indicator}")
            print(f"⏱️  Tiempo: {response['processing_time_seconds']}s ({response['processing_time_ms']}ms)")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
