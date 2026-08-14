# Adventure Tracker — Reglas de Negocio

> Documento vivo. Refleja el comportamiento real del sistema tal como está implementado.
> Actualizar siempre que se modifique lógica de dominio.

---

## 1. Propósito del sistema

Adventure Tracker es un sistema personal de monitoreo que:

1. Busca vuelos baratos en rutas configuradas (BAQ ↔ MDE) para fines de semana.
2. Monitorea cuentas de Instagram de agencias de aventura para detectar nuevos planes.
3. Extrae eventos de imágenes de calendarios usando visión IA (Gemini / Ollama).
4. Cruza vuelos baratos con eventos de agencias disponibles para ese fin de semana.
5. Envía notificaciones consolidadas por Telegram y/o email cuando se cumplen las condiciones.

---

## 2. Módulo de vuelos

### 2.1 Rutas monitoreadas

- Las rutas se definen en `config/routes.yaml`.
- Cada ruta tiene: `origin`, `destination` (códigos IATA), `price_threshold` (COP), `drop_percentage` y `search_days`.
- Rutas activas: **BAQ→MDE** (ida, jueves/viernes) y **MDE→BAQ** (vuelta, domingo/lunes).
- La ruta CTG-MDE/MDE-CTG está desactivada porque el tiempo de traslado desde Barranquilla no lo justifica.
- Los precios son **solo ida** (one-way) por tramo.

### 2.2 Días de búsqueda y ventanas horarias

> **Contexto crítico**: las aventuras parten y regresan a **Medellín (MDE)**. El usuario está en **Barranquilla (BAQ)**. Eso significa que hay un tramo aéreo extra en cada extremo del viaje que el grupo de aventura no tiene.

#### Vuelos de ida (BAQ → MDE)

El día y ventana válidos dependen de **cuándo empieza la aventura en MDE**:

| Inicio de la aventura | Vuelo de ida válido         | Ventana horaria        | Motivo                                                      |
|-----------------------|-----------------------------|------------------------|-------------------------------------------------------------|
| Jueves tarde          | Jueves                      | 18:00 – 23:59          | Llegar esa misma noche antes de que empiece el plan         |
| Viernes (cualquier hora) | Jueves o viernes         | Jue 18:00–23:59 / Vie 00:00–16:00 | Llegar el jueves noche o el viernes en la mañana/tarde |
| Sábado                | Viernes (**obligatorio**)   | 00:00 – 16:00          | Las aventuras empiezan a las 6AM en MDE; salir de BAQ a las 3AM no es viable |

- Si la aventura **empieza el viernes por la noche**: vuelo del viernes con llegada antes de las 4PM es **obligatorio**.
- Si la aventura **empieza el sábado**: vuelo del viernes ≤ 4PM es **obligatorio**. Las aventuras arrancan a las 6AM en MDE — salir de BAQ a las 3AM para conectar no es viable.
- Si la aventura **empieza el jueves tarde**: hay que buscar vuelo el jueves.
- El cutoff de las **16:00 del viernes** aplica en todos los casos donde la aventura empieza el viernes o el sábado.

#### Vuelos de vuelta (MDE → BAQ)

El día válido depende de **cuándo termina la aventura en MDE** y del tramo extra BAQ:

| Fin de la aventura en MDE | Vuelo de vuelta válido | Ventana horaria        | Motivo                                                          |
|---------------------------|------------------------|------------------------|----------------------------------------------------------------|
| Domingo (aventura solo sábado) | **Domingo** ≥ 11:00 | 11:00 – 23:59       | Solo aplica si no hay eventos el domingo; el grupo regresa a MDE desde la aventura del sábado |
| Domingo (aventura con eventos domingo) | **Lunes** | 00:00 – 10:00   | Aventura ocupa el domingo; el grupo llega a MDE ~8PM, imposible volar ese día |
| Lunes                     | **Martes**             | 00:00 – 10:00          | El grupo termina el lunes en MDE; el usuario vuela el martes temprano |

- **La regla del domingo** se determina en `_build_weekend_pairs()` revisando si algún evento del `WeekendPair` tiene fechas que solapen con un domingo del rango (`sunday_adventure` flag).
- Si `sunday_adventure = True` → vuelos del domingo se bloquean completamente.
- Si `sunday_adventure = False` → vuelos del domingo con salida ≥ 11:00 son válidos.
- `TIME_FILTERS` en el código **no incluye SUNDAY** — esa decisión es exclusiva de `_build_weekend_pairs()`.

#### Resumen operativo

| Día de vuelo  | Ventana válida     | Cuándo aplica                                                                |
|---------------|--------------------|---------------------------------------------------------------------------  |
| Jueves        | 18:00 – 23:59      | Aventura empieza el jueves tarde o el viernes                                |
| Viernes       | 00:00 – 16:00      | Aventura empieza el viernes **o el sábado** (obligatorio en ambos casos)     |
| Domingo       | ≥ 11:00            | Solo si aventura es exclusivamente de sábado (`sunday_adventure = False`)    |
| Lunes         | 00:00 – 10:00      | Aventura termina el domingo en MDE (~8PM, no es posible volar ese día)       |
| Martes        | 00:00 – 10:00      | Aventura termina el lunes en MDE                                             |

- Los vuelos fuera de la ventana horaria de su día se **descartan silenciosamente**.
- `TIME_FILTERS` en el código cubre Jueves, Viernes y Lunes. El domingo es gestionado por `_build_weekend_pairs()`.
- Si no se puede parsear la hora de salida, el vuelo se acepta por defecto.

### 2.3 Política de aerolíneas

La decisión de rastrear un vuelo sigue este orden (primera regla que aplica gana):

1. **Aerolínea prioritaria** (LATAM): se incluye si `precio ≤ price_threshold` de la ruta.
2. **Precio ganga**: cualquier aerolínea se incluye si `precio ≤ bargain_threshold` (110,000 COP por defecto).
3. **Reglas extra** (`extra_airlines`): por aerolínea, se incluye si `precio ≤ max_price` configurado.
   - Wingo: ≤ 150,000 COP
   - JetSMART: ≤ 150,000 COP
   - Avianca: ≤ 150,000 COP
4. En cualquier otro caso: **se descarta**.

- LATAM tiene prioridad porque genera puntos/beneficios de programa de lealtad.
- Se puede agregar una aerolínea extra en tiempo de ejecución sin reiniciar (`add_airline()`).
- El `★` en los logs y emails identifica vuelos de aerolínea prioritaria.

### 2.4 Umbral de precio y alerta

- Un vuelo genera alerta si:
  - `precio ≤ price_threshold` de la ruta (`is_below_threshold = True`), **O**
  - la caída de precio desde el registro anterior es `≥ drop_percentage` de la ruta (`is_significant_drop = True`).
- El umbral actual es **300,000 COP** por tramo para BAQ↔MDE.
- La caída mínima para alerta es **15 %** para ambas rutas.
- Las alertas individuales **no se envían** en tiempo real. Se acumulan y el orquestador envía un reporte consolidado al final.

### 2.5 Horizonte temporal

- Por defecto se buscan **10 semanas hacia adelante** (`DEFAULT_WEEKS_AHEAD = 10`).
- El horizonte configurable es de ~2.5 meses de planeación.
- El histórico de precios guarda los últimos **10 precios** por vuelo específico.

### 2.6 Persistencia de precios

- Los precios se guardan localmente en `data/flight_prices.yaml` (`FlightPriceStore`).
- En CI (GitHub Actions), el estado también se sincroniza con un GitHub Gist.
- El `flight_id` que identifica un vuelo es: `{ORIG}-{DEST}_{fecha}_{hora}_{aerolínea}`.

---

## 3. Reporte consolidado de fin de semana

### 3.1 Estructura del reporte

Cuando se encuentran vuelos baratos, el orquestador construye un `WeekendPair` por cada vuelo de ida barato:

- **Ventana de fin de semana**: `window_start` (día del vuelo de ida) + 4 días → `window_end`.
- **Vuelo de ida** (`outbound`): el vuelo barato que disparó la alerta.
- **Opciones de vuelta** (`return_options`): hasta 3 opciones, ordenadas por precio.
- **Eventos** (`events`): planes de agencias disponibles en esa ventana.
- **`sunday_adventure`**: flag que indica si hay eventos el domingo (fuerza regreso el lunes).

### 3.2 Regla del domingo

> **Si hay eventos de agencia que caen en domingo → el vuelo de regreso DEBE ser el lunes.**

- Se revisa si algún evento del `WeekendPair` tiene fechas que solapan con un domingo del rango.
- Si `sunday_adventure = True`, los vuelos de regreso del domingo se filtran y no aparecen como opciones.
- Los vuelos del domingo se aceptan si `sunday_adventure = False` y la hora de salida es `≥ 11:00`.

### 3.3 Regla de preferencia de aerolínea prioritaria en vuelta

> **Si el vuelo de ida es de aerolínea prioritaria → preferir la misma en la vuelta, SALVO que haya otra aerolínea ≥ 100,000 COP más barata.**

- El ahorro significativo (`significant_saving`) está fijado en **100,000 COP**.
- Si hay un vuelo no-prioritario ≥ 100K más barato que el mejor prioritario → se pone primero en la lista de opciones.
- Si no hay ahorro significativo → el vuelo prioritario es `is_recommended = True`.

### 3.4 Deduplicación y límite de opciones

- Se muestran **máximo 3 opciones de vuelta** por fin de semana.
- La deduplicación es por `flight_id` (mismo vuelo no aparece dos veces).
- La primera opción es siempre `is_recommended = True`.

### 3.5 Eventos del reporte

- Se muestran **máximo 6 eventos** por fin de semana en el email HTML.
- Máximo **8 eventos** en el mensaje de Telegram.
- Los eventos están ordenados por precio ascendente.
- Los eventos `sold_out = True` se excluyen del reporte.
- Los eventos en el blacklist de destinos se excluyen del reporte.

---

## 4. Módulo de actividades (Instagram)

> ⚠️ **Estado actual**: el scraper de Instagram (`ActivityTrackerService`) está **inoperativo** para el caso de uso principal. Instagram no expone de forma accesible las imágenes de calendarios que publican las agencias (las que contienen los eventos con fechas y precios). Por tanto, el flujo de detección de eventos **no pasa por Instagram** en la práctica.

El módulo existe en el código y puede ejecutarse, pero su utilidad real es nula para este propósito hasta que se resuelva cómo obtener esas imágenes programáticamente.

### 4.1 Flujo real de eventos (manual)

El único flujo que funciona hoy es completamente manual:

1. El usuario descarga manualmente las imágenes del calendario de la agencia (desde Instagram, WhatsApp, o cualquier fuente).
2. Las coloca en `inbox/<agencia>/` (ej: `inbox/brutal/`, `inbox/medellin-bungee/`).
3. El orquestador detecta las imágenes nuevas, las procesa con Gemini y actualiza `data/extraction_cache.yaml`.
4. Los eventos extraídos quedan disponibles para cruzarse con los vuelos baratos.

### 4.2 Cuentas configuradas (referencia)

Aunque el scraper no funciona, las cuentas siguen definidas en `config/accounts.yaml` como referencia:
- `brutaltravel.co` (Brutal Travel)
- `medellinbungee` (Medellín Bungee)

### 4.3 Reglas del módulo Instagram (si en algún momento se reactiva)

- Solo cuentas con `enabled: true`.
- Máximo **3 revisiones** por post (`MAX_CHECK_COUNT = 3`).
- Sistema **blacklist-only**: se notifica todo excepto destinos en `config/destinations.yaml`.
- En CI: solo posts de las últimas **24 horas**.

---

## 5. Extracción de eventos de imágenes (calendario de agencias)

### 5.1 Flujo de extracción

1. Las imágenes de calendarios de agencias llegan a `inbox/<agencia>/`.
2. El sistema detecta el tipo de archivo por **magic bytes** (no por extensión).
3. Las imágenes ya procesadas se saltan (deduplicación por hash de contenido en `data/extraction_cache.yaml`).
4. Las imágenes nuevas se envían al modelo de visión configurado.

### 5.2 Proveedores de modelo

- **Gemini** (por defecto, cloud): requiere `GEMINI_API_KEY`. Modelo: `gemini-3.5-flash-lite`. Temperatura: 0.1.
- **Ollama** (fallback local): requiere servidor `ollama serve` corriendo en `localhost:11434`. Modelo: `minicpm-v`.
- La selección automática en el orquestador: usa Gemini si `GEMINI_API_KEY` está presente, sino Ollama.

### 5.3 Validación de eventos extraídos

Un evento extraído es válido si:
- `name` tiene al menos 2 caracteres.
- `date_start` está entre 1 y 31.
- `price` está entre 10,000 y 10,000,000 COP. Si está fuera de rango → se guarda como `0`.
- `sold_out` se respeta tal como lo reporta el modelo.
- El año por defecto es **2026** (configurable en `ExtractionConfig`).

### 5.4 Cache de extracción

- Las imágenes procesadas se registran en `data/extraction_cache.yaml`.
- La cache permite re-procesar con `--force` para ignorarla.
- La cache puede limpiarse por agencia o completamente con `--clear-cache`.
- El procesamiento paralelo usa **3 workers** por defecto.

---

## 6. Módulo de feriados y puentes

### 6.1 Fuente de datos

- Los feriados colombianos se cargan desde `config/holidays.yaml` (generado por `scripts/update_holidays.py`).
- La fuente es la librería Python `holidays` con soporte de Ley Emiliani (feriados movibles a lunes).
- Si el año no está en el YAML, se consulta la API `Nager.Date` como fallback (timeout: 10 s).

### 6.2 Detección de fin de semana puente

Un viernes es **puente** (`is_bridge = True`) si:
- El lunes siguiente es feriado, **O**
- El propio viernes es feriado, **O**
- El jueves anterior es feriado (el viernes actúa como puente).

---

## 7. Notificaciones

### 7.1 Canales disponibles

| Canal    | Estado       | Condición de activación                                         |
|----------|--------------|-----------------------------------------------------------------|
| Email    | ✅ **Activo** | `RESEND_API_KEY` y `EMAIL_TO` configurados y no son placeholders |
| Telegram | ⛔ **No usar** | Descartado por ahora. El código existe pero no se debe activar  |

- Si el canal de email no está configurado → el reporte se imprime en log (modo consola).
- Las notificaciones de **fallos del sistema** también van por email, no por Telegram.

### 7.2 Telegram (desactivado)

- El código de `TelegramNotifier` existe pero **Telegram no es el canal de notificaciones activo**.
- No configurar `TELEGRAM_BOT_TOKEN` ni `TELEGRAM_CHAT_ID` en producción.
- La notificación de fallo en `tracker.yaml` (workflow de GitHub Actions) que usaba `curl` directo a Telegram fue reemplazada por email.

### 7.3 Procedimiento de notificación de errores

Existen **dos niveles** de detección de fallos, cada uno con su propio mecanismo:

#### Nivel 1 — Errores dentro de una ejecución exitosa del proceso

El orquestador completa su ciclo pero acumula errores en la lista `errors`. Al finalizar `run()`:

1. Si `errors` es no vacío **y** `EmailNotifier` está configurado → se llama `send_error_report()`.
2. El email incluye cada error clasificado automáticamente como `CRÍTICO` o `WARN`:
   - El primer error siempre es `CRÍTICO`.
   - Errores que contengan keywords (`warning`, `warn`, `failed to sync`, `no response`, `skipping`) → `WARN`.
   - El resto → `CRÍTICO`.
3. El email incluye el resumen de la corrida (modo, duración, rutas revisadas, alertas generadas).
4. Si hay `GITHUB_RUN_ID` en el entorno → el email incluye un enlace directo al run de GitHub Actions.

#### Nivel 2 — Crash total del job de CI (el proceso no llega a terminar)

El workflow `tracker.yaml` tiene un job `notify-failure` que se activa con `if: failure()`:

1. Instala el paquete con `pip install -e .`.
2. Ejecuta un script Python inline que llama `send_error_report()` con un mensaje genérico de crash.
3. Construye el `run_url` desde las variables de entorno de GitHub Actions (`GITHUB_SERVER_URL`, `GITHUB_REPOSITORY`, `GITHUB_RUN_ID`).

#### Secrets requeridos en GitHub Actions

| Secret         | Propósito                          |
|----------------|------------------------------------|
| `RESEND_API_KEY` | Autenticación con la API de Resend |
| `EMAIL_TO`       | Destinatario de los emails         |
| `GIST_ID`        | Persistencia de estado en Gist     |
| `GIST_TOKEN`     | PAT con scope `gist`               |

Los secrets `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` ya no se usan y pueden eliminarse de la configuración del repositorio.

### 7.3 Formato del email

- El email usa el diseño "Tropical/Adventure" (fondo `#fafaf8`, header `#1b4332`, gradiente verde).
- Se estructura por `WeekendPair`: una sección por cada fin de semana encontrado.
- El vuelo de vuelta recomendado va en verde (`#f1f8e9`), las alternativas en gris.
- Si `sunday_adventure = True`, aparece una advertencia en amarillo.
- El total (ida + vuelta recomendada) se muestra en cada sección.
- El remitente fijo es: `Adventure Tracker <onboarding@resend.dev>`.

---

## 8. Estado y persistencia

### 8.1 Entornos

| Entorno | Detección                            | Persistencia de estado              |
|---------|--------------------------------------|-------------------------------------|
| Local   | `GITHUB_ACTIONS` no presente         | Solo archivos YAML locales          |
| CI      | `GITHUB_ACTIONS=true`                | YAML locales + GitHub Gist remoto   |

- El Gist solo se activa si `GITHUB_ACTIONS=true` Y `GIST_ID` Y `GIST_TOKEN` están presentes.
- En local, el Gist se ignora completamente aunque las variables estén en `.env`.

### 8.2 Archivos de estado local

| Archivo                         | Contenido                               |
|---------------------------------|-----------------------------------------|
| `data/flight_prices.yaml`       | Historial de precios por vuelo          |
| `data/extraction_cache.yaml`    | Resultados de extracción de imágenes    |
| `data/activity_history.yaml`    | Historial de posts de Instagram         |

### 8.3 Límites de memoria

- Instagram state: se guardan máximo **100 post IDs** por cuenta (FIFO).
- Price history: se guardan máximo **10 precios** por vuelo (FIFO).

---

## 9. Modos de ejecución

| Modo          | Qué hace                                                         |
|---------------|------------------------------------------------------------------|
| `all`         | Extracción de inbox → búsqueda de vuelos → tracking de Instagram |
| `flights`     | Solo búsqueda de vuelos (sin Instagram)                          |
| `activities`  | Solo tracking de Instagram (sin vuelos)                          |
| `calendar`    | Solo muestra el calendario de vuelos (sin búsqueda real)         |

- En modo `all` y `flights`, el flujo es:
  1. Procesar imágenes nuevas del `inbox/` (Step 1).
  2. Buscar vuelos baratos (Step 2).
  3. Si hay vuelos baratos → cruzar con eventos y enviar reporte (Step 3).
  4. Si no hay vuelos baratos → no se envía nada.

---

## 10. Automatización (GitHub Actions)

### 10.1 Workflows activos

| Workflow         | Trigger                          | Modo       | Frecuencia                    |
|------------------|----------------------------------|------------|-------------------------------|
| `tracker.yaml`   | Cron + manual dispatch           | `all`      | Diario a las 8 AM Colombia (13:00 UTC) |
| `flights-only.yaml` | Cron + manual dispatch        | `flights`  | 2x/día: 7 AM y 7 PM Colombia  |
| `ci.yaml`        | Push/PR a `main`                 | Tests      | Cada commit                   |

### 10.2 Timeout de jobs

- `tracker.yaml`: 30 minutos máximo.
- `flights-only.yaml`: 20 minutos máximo.

### 10.3 Fallos

- Si el job de CI falla → el job `notify-failure` en `tracker.yaml` envía un email de error vía `send_error_report()`.
- Si el proceso completa pero con errores internos → el orquestador mismo envía el email de error al final de `run()`.
- Los logs y playwright-reports se guardan como artefactos por **7 días** en caso de fallo.

---

## 11. Matching de eventos con fechas de vuelos

### 11.1 Agrupación en ventanas

- Las fechas de vuelos baratos se agrupan en ventanas de **5 días** (`window_start` → `window_start + 4`).
- Las ventanas se dedupelan: si dos fechas caen en la misma ventana, se crea una sola.

### 11.2 Criterios de match

Un evento matchea una ventana si:
- `event.date_start ≤ window_end` **Y** `event.date_end ≥ window_start` (solapamiento).
- El evento no está `sold_out`.
- El nombre del evento no matchea el blacklist de destinos.

---

## 12. Reglas de configuración que NO se deben romper

1. **Nunca agregar CTG como ruta activa** sin evaluar primero que el traslado BAQ→CTG lo justifique económicamente.
2. **No incluir destinos de playa** en notificaciones (categoría `playa` en blacklist).
3. **El umbral de ganga** (`bargain_threshold = 110,000 COP`) aplica a cualquier aerolínea. Bajar este valor reduce ruido; subirlo lo aumenta.
4. **El máximo de revisiones** por post es 3. No aumentar sin evaluar el impacto en costos de OCR/Gemini.
5. **Los feriados** deben actualizarse anualmente en `config/holidays.yaml` con `scripts/update_holidays.py`.
6. **El directorio `inbox/`** debe tener subdirectorios por agencia. Las imágenes sueltas en la raíz de `inbox/` son ignoradas.
7. **En CI siempre se filtran posts** de más de 24 horas para no reprocesar publicaciones antiguas.
