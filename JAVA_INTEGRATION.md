# Guía de Integración Java para API Llama + Redis

Esta guía explica cómo integrar su aplicación Java con la API de Python existente.

## Requisitos Previos

- **Java Development Kit (JDK)**: Versión 11 o superior.
- **Dependencias**: Se recomienda usar `Gson` para manejar JSON.

### Dependencia (Maven)
Agregue esto a su archivo `pom.xml`:
```xml
<dependency>
    <groupId>com.google.code.gson</groupId>
    <artifactId>gson</artifactId>
    <version>2.10.1</version>
</dependency>
```

### Dependencia (Gradle)
Agregue esto a su `build.gradle`:
```gradle
implementation 'com.google.code.gson:gson:2.10.1'
```

## Uso del Cliente (`ApiClient.java`)

Se ha proporcionado una clase `ApiClient.java` lista para usar en `/home/opc/agentes/llama-memoria_redis_ok/java_client/ApiClient.java`.

### 1. Inicialización
```java
// Apuntar a la URL donde corre el backend Flask (ej. localhost:5001 o la IP de OCI)
ApiClient client = new ApiClient("http://localhost:5001");
```

### 2. Chat con Memoria
```java
try {
    String pregunta = "¿Cuál es el precio del dólar hoy?";
    String sessionId = "usuario_123"; // ID único por usuario
    
    // Llamada síncrona
    JsonObject respuesta = client.chat(pregunta, sessionId);
    
    // Procesar respuesta
    System.out.println("Respuesta: " + respuesta.get("result").getAsString());
    
    // Verificar si vino del caché
    if (respuesta.get("from_cache").getAsBoolean()) {
        System.out.println("¡Respuesta obtenida del caché!");
    }
} catch (Exception e) {
    e.printStackTrace();
}
```

### 3. Gestión de Sesión y Caché

**Limpiar memoria de conversación:**
```java
client.resetSession("usuario_123");
```

**Obtener estadísticas:**
```java
JsonObject stats = client.getCacheStats();
System.out.println("Memoria usada: " + stats.get("used_memory").getAsString());
```

**Limpiar todo el caché (Admin):**
```java
client.clearCache();
```

## Mapeo de Endpoints

| Método API (Python) | Método Java (`ApiClient`) | Endpoint | Descripción |
|---------------------|---------------------------|----------|-------------|
| `POST /api/chat` | `chat(question, sessionId)` | Interacción principal | Envía preguntas, recibe respuestas con contexto. |
| `POST /api/reset` | `resetSession(sessionId)` | Limpia historial | Borra la memoria de corto plazo de un usuario. |
| `GET /api/cache/stats` | `getCacheStats()` | Monitoreo | Ver uso de memoria y estado de Redis. |
| `POST /api/cache/clear` | `clearCache()` | Mantenimiento | Purga todo el caché de respuestas SQL. |

## Notas Importantes
1. **Tipos de Respuesta**: El campo `result` en la respuesta del chat puede ser un string directo o un objeto JSON dependiendo de cómo responda el agente. El código de ejemplo maneja ambos casos.
2. **Timeouts**: El cliente está configurado con un timeout de 30 segundos (`Duration.ofSeconds(30)`), ya que las consultas a LLM pueden tardes. Ajuste esto si es necesario en `ApiClient.java`.

## Ejecución y Pruebas

Para probar la integración rápidamente sin configurar un proyecto Maven/Gradle completo, puede seguir estos pasos manuales:

### 1. Preparar el Entorno
Asegúrese de tener descargado el JAR de Gson.
```bash
wget https://repo1.maven.org/maven2/com/google/code/gson/gson/2.10.1/gson-2.10.1.jar
```

### 2. Estructura de Directorios
Su directorio debería lucir así:
```
/
├── gson-2.10.1.jar
└── com
    └── bancorepublica
        └── client
            └── ApiClient.java
```

### 3. Compilar
Compile el código Java incluyendo la librería Gson en el classpath (`-cp`):

**En Linux/Mac:**
```bash
javac -cp .:gson-2.10.1.jar com/bancorepublica/client/ApiClient.java
```

**En Windows:**
```cmd
javac -cp .;gson-2.10.1.jar com/bancorepublica/client/ApiClient.java
```

### 4. Ejecutar
Ejecute la clase `ApiClient` (que contiene el método `main` de prueba):

**En Linux/Mac:**
```bash
java -cp .:gson-2.10.1.jar com.bancorepublica.client.ApiClient
```

**En Windows:**
```cmd
java -cp .;gson-2.10.1.jar com.bancorepublica.client.ApiClient
```

### Resultado Esperado
Debería ver una salida similar a esta en su consola:
```text
--- 1. Health Check (Stats) ---
{"connected":true, "ords_cached_queries": 5, ...}

--- 2. Chat Query ---
Preguntando: Cual es la TRM actual?
Respuesta: La TRM actual es...
Origen: REDIS CACHE

--- 3. Reset Memory ---
{"status":"success", "message":"Memoria borrada para session_id: ..."}
```

