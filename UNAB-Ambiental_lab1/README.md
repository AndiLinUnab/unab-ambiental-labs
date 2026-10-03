# UNAB-Ambiental — Laboratorio 1: Azure IoT Central

Sistema de Monitoreo Ambiental de Espacios Académicos, modelado en Azure IoT Central como parte del curso IoT + Cloud + Sistemas Distribuidos, UAB, 2026.

**Integrantes:**
- Andi Lin – U00180153
- Juan Sebastián Buitrago Caballero – U00179631
- Miguel Ángel Solano Díaz – U00177983

No se entrega código: este repositorio documenta las decisiones de modelado tomadas en la plataforma gestionada Azure IoT Central y contiene la evidencia visual del laboratorio.

## Escenario

La universidad no tiene visibilidad en tiempo real de las condiciones ambientales (temperatura, humedad, iluminación) en aulas y laboratorios, lo que impide detectar a tiempo sobrecalentamiento de equipos, humedad excesiva o iluminación inadecuada, y obliga a un mantenimiento reactivo. El detalle completo de la problemática, la arquitectura de referencia y la justificación de rangos operativos está en el documento del Taller Teórico 1 (`Taller1_UNAB-Ambiental.docx`, entregado aparte).

## Decisiones de modelado

**Aplicación**
- Custom application, región Canada Central, plan Standard.
- Se eligió Custom (no un industry template) porque el escenario es propio del curso y no calza con ningún template vertical del marketplace.

**Device Template — `Nodo-Ambiental-ESP32`**

| Capability | Tipo | Detalle |
|---|---|---|
| `temperature` | Telemetry | °C, semantic type Temperature |
| `humidity` | Telemetry | % RH, semantic type Humidity |
| `illuminance` | Telemetry | lux, semantic type Illuminance |
| `modoAlerta` | Property (writable) | Boolean |
| `reiniciar` | Command | Disparador simple, sin request/response |
| `lecturaForzada` | Command | Disparador simple, sin request/response |

Se dejaron los comandos como disparadores simples (sin payload) porque el enunciado solo pide "aceptar comandos remotos básicos", sin exigir parámetros de entrada ni respuesta estructurada del dispositivo.

**Views**
- Vista generada con gráficas de línea para las 3 telemetrías, pensada para que un operador sin conocimientos técnicos entienda el estado del salón de un vistazo.

**Rule — `Alerta_Sobrecalentamiento_Aula`**
- Condición: `temperature > 30 °C`, agregación *Average*, ventana de 5 minutos (evita falsas alarmas por picos instantáneos).
- Acción: notificación por Email al operador.
- Nota de modelado: IoT Central no permite que una Rule cambie directamente una Property del gemelo digital; las únicas acciones nativas son Email, Webhook, Azure Monitor Action Groups, Power Automate y Azure Logic Apps. Por eso `modoAlerta` se maneja como un cambio manual del operador tras recibir la alerta, y no como efecto automático de la Rule.

**Dispositivo**
- Dispositivo simulado (`Simulated`), usado para validar el flujo completo sin depender del hardware ESP32 real.

## Limitaciones detectadas de IoT Central

1. **Sin historial nativo de disparo de Rules.** No existe una pestaña "History" para las reglas; la evidencia de que se disparó hay que obtenerla indirectamente (el correo recibido, o revisando `Raw data` del dispositivo).
2. **Acciones de Rule limitadas a integraciones externas.** No hay una acción nativa para modificar una property del propio dispositivo; para lograrlo hace falta salir del servicio gestionado (Power Automate o Logic Apps llamando a la API REST).
3. **La acción Email depende de la gestión de usuarios de la app.** El destinatario debe existir como usuario registrado de la aplicación; si no, la regla se dispara pero la notificación se pierde silenciosamente, sin ningún mensaje de error visible.

## Preguntas de reflexión

**1. ¿Qué parte fue más difícil de modelar y por qué?**
La Rule de alerta: no fue evidente que el correo destinatario de la acción Email debe ser primero un usuario registrado en la aplicación. Sin ese paso previo, la regla se guarda y aparenta funcionar, pero la notificación nunca llega.

**2. ¿Qué partes no tuvimos que configurar que en un sistema propio sí serían necesarias?**
El broker de mensajería MQTT sobre TLS, el almacenamiento de series de tiempo, el escalado del ingestor de telemetría, la autenticación/autorización de dispositivos y el aprovisionamiento (Device Provisioning Service), además de toda la infraestructura para el envío de notificaciones.

**3. Si el escenario creciera a cientos de dispositivos, ¿qué preocuparía primero?**
El costo por dispositivo del plan Standard, la organización y agrupación de dispositivos por edificio o piso, y el ajuste fino de umbrales para evitar fatiga de alertas si muchos nodos disparan la misma Rule casi al mismo tiempo.

**4. ¿En qué momento saldríamos de un servicio 100% gestionado hacia algo más flexible?**
Cuando se necesite lógica de reglas más compleja (correlación entre varios dispositivos, ventanas de tiempo dinámicas), integración con sistemas legados propios de la universidad, o control total sobre el histórico de datos para analítica avanzada — cosas que el motor de Rules de IoT Central no soporta de forma nativa.

## Estructura del repositorio

```
.
├── README.md
└── evidencias/
    ├── 1_template.png     # Device Template publicado
    ├── 2_view.png         # Vista/dashboard con datos en tiempo real
    ├── 3_rule.png         # Rule configurada
    ├── 4_email.png        # Evidencia de la Rule disparada (correo)
    ├── 5_history.png      # Historial de ejecución de comandos
    └── 6_commands.png     # Comandos ejecutados sobre el dispositivo
```
