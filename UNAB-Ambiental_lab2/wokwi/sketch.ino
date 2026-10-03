/*
 * UNAB-Ambiental — Laboratorio 2, Nodo ESP32 (Wokwi)
 * Lee temperature/humidity (DHT22) e illuminance (potenciómetro simulando BH1750),
 * publica hacia Azure IoT Central vía DPS + MQTT sobre TLS, y enciende un LED
 * cuando recibe el comando remoto 'setAlertLed'.
 *
 * Librerías requeridas (Library Manager de Wokwi):
 *   - DHT sensor library (Adafruit)
 *   - Adafruit Unified Sensor
 *   - PubSubClient
 *   - ArduinoJson
 *
 * IMPORTANTE: reemplaza ID_SCOPE, DEVICE_ID y PRIMARY_KEY con tus propios valores
 * ANTES de correr. NUNCA subas este archivo con tus credenciales reales a un
 * repositorio público — usa placeholders al hacer commit.
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <mbedtls/md.h>
#include <mbedtls/base64.h>
#include <time.h>

// ---------- Wi-Fi (Wokwi) ----------
const char *WIFI_SSID = "Wokwi-GUEST";
const char *WIFI_PASSWORD = "";

// ---------- Credenciales del dispositivo (reemplazar) ----------
const char *ID_SCOPE = "0ne0109B679";
const char *DEVICE_ID = "ESP32-Wokwi";
const char *PRIMARY_KEY = "wfxRiiJIgzFxuxtI/9GgGosI4xNSD/Ah+xFO81QoQ6o=";

// ---------- Pines ----------
#define DHTPIN 15
#define DHTTYPE DHT22
#define LDR_PIN 34
#define LED_PIN 2

DHT dht(DHTPIN, DHTTYPE);

// ---------- Estado global de aprovisionamiento ----------
String assignedHub = "";
String mqttUsername = "";

WiFiClientSecure wifiClient;
PubSubClient mqttClient(wifiClient);

const unsigned long SEND_INTERVAL_MS = 10000;
unsigned long lastSendMs = 0;

// ---------------- Utilidades cripto (SAS token) ----------------

String urlEncode(const String &s) {
  String out;
  const char *hex = "0123456789ABCDEF";
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
      out += c;
    } else {
      out += '%';
      out += hex[(c >> 4) & 0xF];
      out += hex[c & 0xF];
    }
  }
  return out;
}

String base64Decode(const String &input) {
  size_t outLen = 0;
  unsigned char outBuf[256];
  mbedtls_base64_decode(outBuf, sizeof(outBuf), &outLen,
                         (const unsigned char *)input.c_str(), input.length());
  return String((char *)outBuf, outLen);
}

String base64EncodeBytes(const unsigned char *data, size_t len) {
  size_t outLen = 0;
  unsigned char outBuf[256];
  mbedtls_base64_encode(outBuf, sizeof(outBuf), &outLen, data, len);
  return String((char *)outBuf, outLen);
}

// Genera un SAS token: SharedAccessSignature sr=<resourceUri>&sig=<sig>&se=<expiry>[&skn=registration]
String generateSasToken(const String &resourceUri, const String &key, unsigned long ttlSeconds, bool isDps) {
  time_t now;
  time(&now);
  unsigned long expiry = (unsigned long)now + ttlSeconds;

  String stringToSign = urlEncode(resourceUri) + "\n" + String(expiry);

  // Decodificar la key (viene en Base64) a bytes crudos
  size_t keyLen = 0;
  unsigned char keyBytes[128];
  mbedtls_base64_decode(keyBytes, sizeof(keyBytes), &keyLen,
                         (const unsigned char *)key.c_str(), key.length());

  unsigned char hmacResult[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, keyBytes, keyLen);
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)stringToSign.c_str(), stringToSign.length());
  mbedtls_md_hmac_finish(&ctx, hmacResult);
  mbedtls_md_free(&ctx);

  String signature = base64EncodeBytes(hmacResult, 32);

  String token = "SharedAccessSignature sr=" + urlEncode(resourceUri) +
                 "&sig=" + urlEncode(signature) +
                 "&se=" + String(expiry);
  if (isDps) {
    token += "&skn=registration";
  }
  return token;
}

// ---------------- Wi-Fi ----------------

void connectWiFi() {
  Serial.print("Conectando a WiFi ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println("\nWiFi conectado. IP: " + WiFi.localIP().toString());

  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.print("Sincronizando hora");
  time_t now = time(nullptr);
  while (now < 100000) {
    delay(300);
    Serial.print(".");
    now = time(nullptr);
  }
  Serial.println("\nHora sincronizada.");
}

// ---------------- Provisioning (DPS) ----------------
// Registro simplificado vía HTTPS PUT + polling, usando WiFiClientSecure.

// Hace una petición HTTPS simple sobre DPS y devuelve el cuerpo completo de la respuesta.
String dpsHttpsRequest(const String &method, const String &path, const String &sasToken,
                        const String &body) {
  WiFiClientSecure dpsClient;
  dpsClient.setInsecure(); // Simulación educativa: en producción usar CA cert de DigiCert Global Root

  String host = "global.azure-devices-provisioning.net";
  if (!dpsClient.connect(host.c_str(), 443)) {
    Serial.println("ERROR: no se pudo conectar a DPS");
    return "";
  }

  String request = method + " " + path + " HTTP/1.1\r\n";
  request += "Host: " + host + "\r\n";
  request += "Authorization: " + sasToken + "\r\n";
  request += "Content-Type: application/json\r\n";
  request += "Content-Length: " + String(body.length()) + "\r\n";
  request += "Connection: close\r\n\r\n";
  request += body;

  dpsClient.print(request);

  String response = "";
  unsigned long start = millis();
  while (dpsClient.connected() && millis() - start < 10000) {
    while (dpsClient.available()) {
      response += (char)dpsClient.read();
    }
  }
  dpsClient.stop();
  return response;
}

// Extrae el valor de un campo string "clave":"valor" de un JSON en texto plano.
String extractJsonString(const String &json, const String &key) {
  String pattern = "\"" + key + "\":\"";
  int idx = json.indexOf(pattern);
  if (idx == -1) return "";
  int start = idx + pattern.length();
  int end = json.indexOf("\"", start);
  return json.substring(start, end);
}

bool provisionDevice() {
  String resourceUri = String(ID_SCOPE) + "/registrations/" + String(DEVICE_ID);
  String sasToken = generateSasToken(resourceUri, PRIMARY_KEY, 3600, true);

  // 1) PUT inicial de registro
  String putPath = "/" + String(ID_SCOPE) + "/registrations/" + String(DEVICE_ID) +
                    "/register?api-version=2019-03-31";
  String putBody = "{\"registrationId\":\"" + String(DEVICE_ID) + "\"}";
  String response = dpsHttpsRequest("PUT", putPath, sasToken, putBody);

  String status = extractJsonString(response, "status");
  String operationId = extractJsonString(response, "operationId");

  if (operationId.length() == 0) {
    Serial.println("ERROR: no se recibió operationId. Respuesta:");
    Serial.println(response);
    return false;
  }

  // 2) Poll GET al mismo operationId hasta que status == "assigned"
  String getPath = "/" + String(ID_SCOPE) + "/registrations/" + String(DEVICE_ID) +
                    "/operations/" + operationId + "?api-version=2019-03-31";

  int attempts = 0;
  while (status == "assigning" && attempts < 10) {
    attempts++;
    delay(3000); // respeta el Retry-After sugerido por Azure (~3s)
    response = dpsHttpsRequest("GET", getPath, sasToken, "");
    status = extractJsonString(response, "status");
    Serial.println("Poll #" + String(attempts) + " -> status: " + status);
  }

  if (status != "assigned") {
    Serial.println("ERROR: el aprovisionamiento no llegó a 'assigned'. Última respuesta:");
    Serial.println(response);
    return false;
  }

  assignedHub = extractJsonString(response, "assignedHub");
  Serial.println("Hub asignado: " + assignedHub);
  return true;
}

// ---------------- MQTT ----------------

void mqttCallback(char *topic, byte *payload, unsigned int length) {
  String topicStr = String(topic);
  String payloadStr;
  for (unsigned int i = 0; i < length; i++) payloadStr += (char)payload[i];

  Serial.println("[MQTT IN] " + topicStr + " -> " + payloadStr);

  // Comandos (direct methods): $iothub/methods/POST/{methodName}/?$rid={rid}
  if (topicStr.startsWith("$iothub/methods/POST/")) {
    int nameStart = strlen("$iothub/methods/POST/");
    int nameEnd = topicStr.indexOf('/', nameStart);
    String methodName = topicStr.substring(nameStart, nameEnd);

    int ridIdx = topicStr.indexOf("$rid=");
    String rid = topicStr.substring(ridIdx + 5);

    Serial.println("Comando recibido: " + methodName);

    int status = 200;
    if (methodName == "setAlertLed") {
      StaticJsonDocument<128> doc;
      deserializeJson(doc, payloadStr);
      bool ledOn = doc["on"] | true; // si no viene payload, por defecto enciende
      digitalWrite(LED_PIN, ledOn ? HIGH : LOW);
      Serial.println(ledOn ? "LED encendido" : "LED apagado");
    } else {
      status = 404;
    }

    String responseTopic = "$iothub/methods/res/" + String(status) + "/?$rid=" + rid;
    mqttClient.publish(responseTopic.c_str(), "{}");
  }
}

bool connectMqtt() {
  String resourceUri = assignedHub + "/devices/" + String(DEVICE_ID);
  String sasToken = generateSasToken(resourceUri, PRIMARY_KEY, 3600, false);

  mqttUsername = assignedHub + "/" + String(DEVICE_ID) + "/?api-version=2021-04-12";

  wifiClient.setInsecure(); // Simulación educativa
  mqttClient.setServer(assignedHub.c_str(), 8883);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setBufferSize(512);
  mqttClient.setKeepAlive(60); // más margen que el default (15s), evita falsos timeouts
  mqttClient.setSocketTimeout(10);

  Serial.println("Conectando a MQTT: " + assignedHub);
  bool ok = mqttClient.connect(DEVICE_ID, mqttUsername.c_str(), sasToken.c_str());
  if (ok) {
    Serial.println("Conectado a IoT Central por MQTT.");
    String methodTopic = "$iothub/methods/POST/#";
    mqttClient.subscribe(methodTopic.c_str());
  } else {
    Serial.print("Fallo de conexión MQTT, rc=");
    Serial.println(mqttClient.state());
  }
  return ok;
}

void publishTelemetry(float temperature, float humidity, float illuminance) {
  StaticJsonDocument<256> doc;
  doc["temperature"] = temperature;
  doc["humidity"] = humidity;
  doc["illuminance"] = illuminance;

  char buffer[256];
  size_t n = serializeJson(doc, buffer);

  String topic = "devices/" + String(DEVICE_ID) + "/messages/events/";
  mqttClient.publish(topic.c_str(), (uint8_t *)buffer, n);

  Serial.print("[Telemetría enviada] ");
  Serial.println(buffer);
}

// ---------------- Lógica de sensores ----------------

float readIlluminance() {
  int raw = analogRead(LDR_PIN);        // 0-4095
  return map(raw, 0, 4095, 100, 800);   // escala al rango operativo 100-800 lux
}

// ---------------- Setup / Loop ----------------

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  dht.begin();

  connectWiFi();

  Serial.println("Iniciando aprovisionamiento DPS...");
  int attempts = 0;
  while (!provisionDevice() && attempts < 5) {
    attempts++;
    delay(3000);
  }

  if (assignedHub.length() == 0) {
    Serial.println("ERROR: no se pudo aprovisionar el dispositivo. Revisa ID_SCOPE/PRIMARY_KEY.");
    return;
  }

  connectMqtt();
}

void loop() {
  if (!mqttClient.connected()) {
    Serial.println("MQTT desconectado, reintentando conexión...");
    connectMqtt();
    delay(2000);
    return;
  }
  mqttClient.loop();

  if (millis() - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = millis();

    float h = dht.readHumidity();
    float t = dht.readTemperature();
    float lux = readIlluminance();

    if (isnan(h) || isnan(t)) {
      Serial.println("Error leyendo el DHT22, reintentando...");
      return;
    }

    publishTelemetry(t, h, lux);
  }
}
