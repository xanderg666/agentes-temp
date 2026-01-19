package com.bancorepublica.client;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

/**
 * Cliente Java para interactuar con la API REST de Llama + Redis.
 * Requiere: Java 11+
 * Dependencias: com.google.code.gson:gson:2.10.1 (o superior)
 */
public class ApiClient {

    private final String baseUrl;
    private final HttpClient httpClient;
    private final Gson gson;

    public ApiClient(String baseUrl) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        this.gson = new Gson();
    }

    // ==========================================
    // Public Methods
    // ==========================================

    /**
     * Envía una pregunta al chat.
     *
     * @param question  La pregunta del usuario.
     * @param sessionId El ID de la sesión (puede ser "default" o cualquier identificador único).
     * @return Respuesta en formato JsonObject.
     * @throws Exception Si ocurre un error de comunicación.
     */
    public JsonObject chat(String question, String sessionId) throws Exception {
        JsonObject payload = new JsonObject();
        payload.addProperty("question", question);
        payload.addProperty("session_id", sessionId);

        String responseBody = sendFiles("POST", "/api/chat", payload.toString());
        return JsonParser.parseString(responseBody).getAsJsonObject();
    }

    /**
     * Limpia la memoria de una sesión específica.
     *
     * @param sessionId El ID de la sesión a limpiar.
     * @return Respuesta de la API.
     * @throws Exception Si ocurre un error.
     */
    public JsonObject resetSession(String sessionId) throws Exception {
        JsonObject payload = new JsonObject();
        payload.addProperty("session_id", sessionId);

        String responseBody = sendFiles("POST", "/api/reset", payload.toString());
        return JsonParser.parseString(responseBody).getAsJsonObject();
    }

    /**
     * Obtiene las estadísticas del caché de Redis.
     *
     * @return JsonObject con las estadísticas.
     * @throws Exception Si ocurre un error.
     */
    public JsonObject getCacheStats() throws Exception {
        String responseBody = sendFiles("GET", "/api/cache/stats", null);
        return JsonParser.parseString(responseBody).getAsJsonObject();
    }

    /**
     * Limpia todo el caché de Redis.
     *
     * @return Respuesta de confirmación.
     * @throws Exception Si ocurre un error.
     */
    public JsonObject clearCache() throws Exception {
        String responseBody = sendFiles("POST", "/api/cache/clear", null);
        return JsonParser.parseString(responseBody).getAsJsonObject();
    }

    // ==========================================
    // Internal Helper Methods
    // ==========================================

    private String sendFiles(String method, String endpoint, String jsonBody) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + endpoint))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(30));

        if ("POST".equalsIgnoreCase(method)) {
            builder.POST(HttpRequest.BodyPublishers.ofString(jsonBody == null ? "{}" : jsonBody));
        } else if ("GET".equalsIgnoreCase(method)) {
            builder.GET();
        }

        HttpResponse<String> response = httpClient.send(builder.build(), HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() >= 400) {
            throw new Exception("Error API (" + response.statusCode() + "): " + response.body());
        }

        return response.body();
    }

    // ==========================================
    // Main Method Example
    // ==========================================
    public static void main(String[] args) {
        try {
            // URL de tu API (Asegúrate de cambiarla si es necesario)
            String apiUrl = "http://localhost:5001"; 
            ApiClient client = new ApiClient(apiUrl);

            System.out.println("--- 1. Health Check (Stats) ---");
            System.out.println(client.getCacheStats());

            System.out.println("\n--- 2. Chat Query ---");
            String question = "Cual es la TRM del 10 de enero del 2025?";
            String sessionId = "java_client_user_1";
            System.out.println("Preguntando: " + question);
            
            JsonObject response = client.chat(question, sessionId);
            // Extraer respuesta
            String answer = "Sin respuesta";
            if (response.has("result")) {
                if (response.get("result").isJsonObject()) {
                    JsonObject resultObj = response.getAsJsonObject("result");
                    if (resultObj.has("answer")) {
                        answer = resultObj.get("answer").getAsString();
                    } else if (resultObj.has("response")) {
                        answer = resultObj.get("response").getAsString();
                    } else {
                        answer = resultObj.toString();
                    }
                } else if (response.get("result").isJsonPrimitive()) {
                   answer = response.get("result").getAsString(); 
                }
            }
            
            boolean fromCache = response.has("from_cache") && response.get("from_cache").getAsBoolean();
            System.out.println("Respuesta: " + answer);
            System.out.println("Origen: " + (fromCache ? "CACHE" : "API REMOTA"));

            System.out.println("\n--- 3. Reset Memory ---");
            System.out.println(client.resetSession(sessionId));

        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
