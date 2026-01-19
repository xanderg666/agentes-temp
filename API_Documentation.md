# Documentación de la API de Memoria y Caché

Este documento describe los endpoints de la API Flask definida en `api_memory_cached.py` y los componentes de gestión de memoria de `memory_manager.py`.

La API está diseñada para interactuar con un agente conversacional que tiene capacidad de memoria a corto plazo (por sesión) y un sistema de caché persistente (usando Redis) para optimizar las respuestas.

---

## 1. API Endpoints (`api_memory_cached.py`)

Estos son los endpoints HTTP que puedes consumir para interactuar con el servicio.

### 1.1. Chatear con el Agente

Este es el endpoint principal para enviar preguntas al agente conversacional. Gestiona la memoria de la conversación y utiliza el caché para acelerar las respuestas.

- **Endpoint**: `/api/chat`
- **Método**: `POST`
- **Descripción**: Envía una pregunta y un ID de sesión. El sistema recupera el historial de la conversación (si existe), procesa la pregunta y devuelve una respuesta. Si la pregunta ha sido respondida antes, la respuesta se sirve desde el caché.
- **Headers**:
  - `Content-Type`: `application/json`

- **Body (JSON)**:
  ```json
  {
    "question": "¿Cuál es la TRM histórica de los últimos 5 días?",
    "session_id": "user123_conversation_456"
  }
  ```
  - `question` (string, requerido): La pregunta del usuario.
  - `session_id` (string, opcional): Un identificador único para la conversación. Si no se proporciona, se usará `"default"`.

- **Ejemplo de consumo (Postman)**:
  1.  **Método**: `POST`
  2.  **URL**: `http://localhost:5001/api/chat`
  3.  **Pestaña "Body"**: selecciona `raw` y `JSON`.
  4.  **Contenido**: Pega el JSON de ejemplo.

### 1.2. Limpiar Memoria de Sesión

Permite eliminar el historial de una conversación específica, forzando al agente a "olvidar" las interacciones pasadas para esa sesión.

- **Endpoint**: `/api/reset`
- **Método**: `POST`
- **Descripción**: Limpia el historial de mensajes de la sesión especificada en el body.
- **Headers**:
  - `Content-Type`: `application/json`

- **Body (JSON)**:
  ```json
  {
    "session_id": "user123_conversation_456"
  }
  ```
  - `session_id` (string, opcional): El ID de la sesión que se desea limpiar. Si no se especifica, se limpiará la sesión `"default"`.

- **Ejemplo de consumo (Postman)**:
  1.  **Método**: `POST`
  2.  **URL**: `http://localhost:5001/api/reset`
  3.  **Pestaña "Body"**: selecciona `raw` y `JSON`.
  4.  **Contenido**: Pega el JSON con el `session_id` a limpiar.

### 1.3. Limpiar Todo el Caché

Elimina todas las entradas almacenadas en el caché de Redis. Útil para forzar la reevaluación de todas las consultas.

- **Endpoint**: `/api/cache/clear`
- **Método**: `POST`
- **Descripción**: Borra completamente el caché de Redis. No requiere parámetros.
- **Ejemplo de consumo (Postman)**:
  1.  **Método**: `POST`
  2.  **URL**: `http://localhost:5001/api/cache/clear`

### 1.4. Obtener Estadísticas del Caché

Proporciona métricas sobre el estado actual del caché de Redis.

- **Endpoint**: `/api/cache/stats`
- **Método**: `GET`
- **Descripción**: Devuelve un objeto JSON con estadísticas como la memoria utilizada, el número de llaves y el estado de la conexión.
- **Ejemplo de consumo (Postman)**:
  1.  **Método**: `GET`
  2.  **URL**: `http://localhost:5001/api/cache/stats`

### 1.5. Listar Entradas del Caché

Obtiene una lista de las claves (preguntas cacheadas) almacenadas en Redis.

- **Endpoint**: `/api/cache/entries`
- **Método**: `GET`
- **Descripción**: Devuelve una lista de las entradas que están actualmente en el caché.
- **Query Params**:
  - `limit` (int, opcional): Limita el número de entradas a devolver. Ejemplo: `?limit=100`. Por defecto es `50`.
- **Ejemplo de consumo (Postman)**:
  1.  **Método**: `GET`
  2.  **URL**: `http://localhost:5001/api/cache/entries?limit=20`

### 1.6. Health Check

Endpoint estándar para verificar que el servicio está en funcionamiento.

- **Endpoint**: `/health`
- **Método**: `GET`
- **Descripción**: Devuelve el estado del servicio, las características habilitadas y el estado del caché. Es ideal para sistemas de monitoreo.
- **Ejemplo de consumo (Postman)**:
  1.  **Método**: `GET`
  2.  **URL**: `http://localhost:5001/health`

---

## 2. Gestor de Memoria (`memory_manager.py`)

Este módulo no expone una API REST directamente, pero es un componente interno crucial que es consumido por la lógica de la API principal (`api_memory_cached.py` y `main_memory_cached.py`). Su función es gestionar el historial de las conversaciones en la memoria de la aplicación.

### Funciones Principales:

- **`get_session_history(session_id: str)`**:
  - **Propósito**: Es la función más importante. Dado un `session_id`, busca en un diccionario global (`_session_store`) si ya existe un historial para esa conversación.
  - **Funcionamiento**:
    1.  Si encuentra el historial, lo devuelve.
    2.  Si no lo encuentra, crea un nuevo objeto `ChatMessageHistory` vacío, lo guarda en el diccionario con el `session_id` como clave y lo devuelve.
  - **Uso**: El endpoint `/api/chat` llama a esta función para obtener el contexto de la conversación antes de invocar al modelo de lenguaje.

- **`clear_session(session_id: str)`**:
  - **Propósito**: Elimina el historial de una sesión del diccionario en memoria.
  - **Uso**: Es invocado por el endpoint `/api/reset` para cumplir con la solicitud de limpieza.

- **`list_sessions() -> list[str]`**:
  - **Propósito**: Devuelve una lista con los `session_id` de todas las conversaciones activas que se guardan en memoria.
  - **Uso**: Podría ser utilizado para un endpoint de administración que liste las sesiones activas (actualmente no implementado en la API).

En resumen, `memory_manager.py` actúa como una capa de abstracción simple para manejar la memoria conversacional de múltiples usuarios o sesiones de forma aislada, utilizando un simple diccionario como almacenamiento en tiempo de ejecución.
