# como activar el ambiente backend

activar el anviente virtual

```bash
conda activate agentes
```

ejecutar el backend

```bash
python api_memory_cached.py
```

dejar corriendo la aplicacion en segundo plano

```bash
nohup python api_memory_cached.py > api_memory_cached.log 2>&1 &
```

terminar el proceso

```bash
ps aux | grep api_memory_cached.py
ps aux | grep api_memory_cached.py <PID>
```
```bash
sudo lsof -i :5001
```

```bash
kill -9 <PID>
```



## para java

`cd java_client`

```bash
javac -cp .:gson-2.10.1.jar com/bancorepublica/client/ApiClient.java
java -cp .:gson-2.10.1.jar com.bancorepublica.client.ApiClient
```



# Documentación de API: Endpoints ORDS para Banco República

Este documento describe los endpoints de la API REST creados con Oracle REST Data Services (ORDS) para interactuar con el modelo de lenguaje Llama y los datos del Banco República directamente desde la base de datos Oracle.

## Información General

-   **URL Base**: La URL base para todos los endpoints sigue el patrón: `https://<hostname-de-tu-adb>/ords/br_llama/`
-   **Módulo**: `br_llama_api`
-   **Path del Módulo**: `llama_api/`
-   **Autenticación**: Los endpoints están configurados sin autenticación (`p_auto_rest_auth => FALSE`).
-   **Formato de Petición**: Todos los endpoints esperan una petición `POST` con un cuerpo en formato JSON.

---

## Endpoints Disponibles

A continuación se detallan los 4 endpoints publicados en el módulo `br_llama_api`.

### 1. Endpoint: `runsql`

Este endpoint está diseñado para ejecutar una consulta SQL en la base de datos, obtener los resultados y luego usar el modelo de lenguaje para generar una respuesta basada en esos datos.

-   **URL Completa**: `https://<hostname>/ords/br_llama/llama_api/runsql`
-   **Método**: `POST`
-   **Descripción**: Recibe una pregunta, la pasa a la función `CONSULTAR_BR_LLAMA` de la base de datos, la cual internamente ejecuta `DBMS_CLOUD_AI.GENERATE` con `action => 'runsql'`. Este action es ideal para convertir la pregunta en una consulta SQL, ejecutarla y obtener un JSON con los datos.
-   **Uso principal**: Para preguntas que requieren una respuesta estructurada y directa desde las tablas de la base de datos.
-   **Body (JSON)**:
    ```json
    {
      "question": "¿Cuál fue la TRM para el 2 de enero de 2024?"
    }
    ```
-   **Ejemplo de `curl`**:
    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -d '{"question": "¿Cuál fue la TRM para el 2 de enero de 2024?"}' \
      "https://<hostname>/ords/br_llama/llama_api/runsql"
    ```

### 2. Endpoint: `narrate`

Este endpoint genera una respuesta en lenguaje natural (una narración) basada en la información encontrada en la base de datos.

-   **URL Completa**: `https://<hostname>/ords/br_llama/llama_api/narrate`
-   **Método**: `POST`
-   **Descripción**: Recibe una pregunta y construye un "prompt" específico que instruye al modelo para que analice los datos y narre la respuesta de forma clara y concisa. Utiliza la acción `narrate` de `DBMS_CLOUD_AI.GENERATE`. La respuesta de texto se empaqueta en un objeto JSON.
-   **Uso principal**: Cuando se prefiere una explicación en texto en lugar de una tabla de datos JSON.
-   **Formato de Respuesta**: `{"narrative": "La respuesta generada..."}`
-   **Body (JSON)**:
    ```json
    {
      "question": "Narra la evolución de la UVR en la última semana."
    }
    ```
-   **Ejemplo de `curl`**:
    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -d '{"question": "Narra la evolución de la UVR en la última semana."}' \
      "https://<hostname>/ords/br_llama/llama_api/narrate"
    ```

### 3. Endpoint: `agent`

Este es el endpoint más avanzado, ya que invoca a un "equipo de agentes" de IA (`TEAM_BR_LLAMA2`) que puede realizar tareas más complejas.

-   **URL Completa**: `https://<hostname>/ords/br_llama/llama_api/agent`
-   **Método**: `POST`
-   **Descripción**: Recibe una pregunta y la pasa al equipo de agentes `TEAM_BR_LLAMA2` usando `DBMS_CLOUD_AI_AGENT.RUN_TEAM`. Este equipo está preconfigurado con herramientas y capacidades para resolver preguntas que pueden requerir varios pasos o consultas.
-   **Uso principal**: Para preguntas complejas o ambiguas que se benefician de un razonamiento multi-paso.
-   **Body (JSON)**:
    ```json
    {
      "question": "Compara la deuda externa con los ingresos por remesas del último año."
    }
    ```
-   **Ejemplo de `curl`**:
    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -d '{"question": "Compara la deuda externa con los ingresos por remesas del último año."}' \
      "https://<hostname>/ords/br_llama/llama_api/agent"
    ```

### 4. Endpoint: `genai`

Este endpoint proporciona una respuesta directa del modelo de lenguaje, sin consultar la base de datos. Es un endpoint de propósito general.

-   **URL Completa**: `https://<hostname>/ords/br_llama/llama_api/genai`
-   **Método**: `POST`
-   **Descripción**: Recibe una pregunta, la envuelve en un prompt simple y llama a `DBMS_CLOUD_AI.GENERATE` con `action => 'chat'`. La respuesta es el texto generado por el modelo, empaquetado en un objeto JSON.
-   **Uso principal**: Para preguntas de conocimiento general que no dependen de los datos específicos del Banco República.
-   **Formato de Respuesta**: `{"response": "La respuesta generada..."}`
-   **Body (JSON)**:
    ```json
    {
      "question": "¿Cuál es la capital de Colombia?"
    }
    ```
-   **Ejemplo de `curl`**:
    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -d '{"question": "¿Cuál es la capital de Colombia?"}' \
      "https://<hostname>/ords/br_llama/llama_api/genai"
    ```
