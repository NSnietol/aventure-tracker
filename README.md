# Adventure Tracker

Sistema local para rastrear vuelos baratos en modo **round-trip** (ida+vuelta) entre Barranquilla y Medellín, cruzarlos con eventos de agencias de aventura, y enviar una notificación consolidada por email cuando hay un finde que vale la pena.

## ¿Cómo funciona?

Busca vuelos baratos BAQ↔MDE en modo round-trip real (no dos búsquedas one-way independientes). Cuando el precio combinado ida+vuelta está por debajo del umbral, cruza con los planes de aventura disponibles ese fin de semana y manda un solo email con todo: vuelo de ida, opciones de regreso, y actividades. Sin hacer nada manual.

```
inbox/brutal/        inbox/medellin-bungee/
  (imágenes JPG/PNG de calendarios de agencias)
          ↓
    Gemini Vision API
    "¿Qué eventos hay en esta imagen?"
          ↓
    extraction_cache.yaml
    { "Canyoning San Carlos": "23 Ago, $180K" }
          ↓                        ↓
  Google Flights (RT)         EventMatcher
  Playwright scrapa RT        cruza fechas baratas
  BAQ→MDE jue/vie             con eventos disponibles
  + 6 opciones de regreso     filtra blacklist
  MDE→BAQ lun/mar ✅
          ↓                        ↓
              Resend API
    Email HTML: vuelo ida + opciones vuelta + planes ese finde
```

## Stack

| Tecnología | Rol |
|-----------|-----|
| **Python 3.12** | Lenguaje base. `asyncio` para operaciones I/O-bound |
| **Playwright** | Controla Chromium headless para scrapear Google Flights en modo round-trip. Hace JS click en cada tarjeta de vuelo de ida para obtener las opciones de regreso |
| **Gemini Vision API** | Modelo multimodal que analiza imágenes de calendarios de agencias y extrae eventos estructurados (nombre, fecha, precio). Alternativa offline: Ollama + minicpm-v |
| **Resend** | API de email transaccional. Se eligió sobre Gmail SMTP para no exponer credenciales personales — solo un API key revocable |
| **Pydantic** | Validación de configuración y lectura de variables de entorno desde `.env` |
| **YAML** | Almacenamiento local: historial de precios, cache de extracción, configuración. Sin base de datos — todo versionable con git |
| **SHA256 hashing** | Cache de imágenes basado en contenido. Si mandas la misma imagen con distinto nombre, no se reprocesa |
| **pytest** | 693+ tests unitarios e integración. Scrapers mockeados con `AsyncMock` para no hacer requests reales |

### Decisiones de diseño

- **Round-trip real** — busca el precio combinado ida+vuelta en un solo search de Google Flights (no two one-way searches). Más preciso y refleja precios reales.
- **Sin base de datos** — YAML es suficiente. Todo es legible, versionable y sin setup.
- **Sin servidor** — corre como script local o en CI (GitHub Actions). No hay proceso siempre activo.
- **Blacklist en vez de whitelist** — ves todo lo que ofrecen las agencias *excepto* lo que ya visitaste o no te interesa. Más fácil de mantener.
- **Un solo email** — espera a tener el cuadro completo (vuelo ida + opciones vuelta + eventos) y manda uno. Menos ruido.
- **LATAM al final** — en la lista de vuelos de ida, LATAM aparece al final ("como caviar") para que las opciones más económicas sean visibles primero.

## Features

- **Round-Trip Flight Tracking**: Monitorea precios RT en Google Flights para viajes de fin de semana
  - Rutas: BAQ↔MDE (round-trip combinado)
  - Busca jueves/viernes (ida) con regreso lunes/martes
  - Hasta 10 semanas de anticipación
  - Alerta cuando precio total RT ≤ umbral configurado (`round_trip_threshold: 300000` en `config/routes.yaml`)
  - Por cada vuelo de ida barato, scrapa hasta 6 opciones de regreso disponibles

- **Event Extraction**: Extrae eventos de imágenes de calendarios de agencias
  - Procesa con Gemini API (~3s/imagen) u Ollama local (~9s/imagen)
  - Cache SHA256 para no reprocesar imágenes ya vistas
  - Agencias: `inbox/brutal/`, `inbox/medellin-bungee/`

- **Eventos manuales**: Eventos sin agencia digital se agregan en `data/manual_events.yaml`

- **Reporte Consolidado**: Cuando hay vuelo barato, cruza con eventos disponibles ese finde y envía **un solo email** con todo
  - Template HTML estilo revista de aventuras
  - Muestra vuelo de ida + hasta 3 opciones de regreso (con recomendación)
  - Regla del domingo: si hay planes el domingo, solo muestra regresos el lunes
  - LATAM siempre al final de los vuelos de ida (opciones económicas primero)
  - Filtra destinos ya visitados (`config/destinations.yaml`)
  - Enviado vía Resend (gratis, sin exponer credenciales personales)

## Quick Start

### Requisitos

- Python 3.12+
- Playwright (browser headless)
- Resend API key (gratis en [resend.com](https://resend.com))
- Gemini API key (opcional, gratis en [aistudio.google.com](https://aistudio.google.com/apikey))

### Instalación

```bash
git clone https://github.com/NSnietol/aventure-tracker.git
cd aventure-tracker

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
playwright install chromium
```

### Configuración

Copia `.env.example` a `.env` y completa:

```bash
# Notificaciones por email (Resend)
RESEND_API_KEY=re_tu_api_key
EMAIL_TO=tu@email.com

# Extracción de imágenes (opcional, más rápido que Ollama)
GEMINI_API_KEY=tu_gemini_key

# Threshold overrides (opcional — si no se definen, se usan los valores de config/routes.yaml)
# FLIGHT_PRICE_THRESHOLD=300000     # Precio máximo por tramo one-way en COP
# FLIGHT_BARGAIN_THRESHOLD=110000   # Cualquier aerolínea se incluye si precio ≤ este valor
# FLIGHT_EXTRA_MAX_PRICE=150000     # Precio máximo para aerolíneas extra (Wingo, JetSMART, Avianca)
```

## Comandos

### Flujo completo (recomendado)

```bash
# Flujo completo con 10 semanas de anticipación (default)
python -m aventure_tracker.main --mode flights

# Empezar desde una fecha específica (útil para buscar eventos conocidos)
python -m aventure_tracker.main --mode flights --from-date 2026-10-18

# Con logs detallados (muestra cada vuelo descartado y la regla aplicada)
python -m aventure_tracker.main --mode flights --verbose

# Sin enviar notificaciones (ver resultados en consola)
python -m aventure_tracker.main --mode flights --dry-run
```

### Agregar evento manual

Editar `data/manual_events.yaml`:

```yaml
events:
  - name: "Reencuentro Grupo Peru"
    agency: "personal"
    date_start: "2026-10-24"
    date_end: "2026-10-25"
    price: 0
    notes: "Reencuentro grupo Peru - fin de semana 24-25 oct"
```

### Otros modos

```bash
# Mostrar calendario de vuelos
python -m aventure_tracker.main --mode calendar

# Ejecutar todo (vuelos + actividades)
python -m aventure_tracker.main --mode all
```

## Flujo completo

```
python -m aventure_tracker.main --mode flights --from-date 2026-10-18
        ↓
1. Lee inbox/brutal/ + inbox/medellin-bungee/
   Procesa solo imágenes nuevas (SHA256 → skip si ya en cache)
   Extrae eventos con Gemini/Ollama → guarda en data/extraction_cache.yaml
        ↓
2. Busca vuelos RT baratos en Google Flights (próximos weekends)
   Para cada outbound barato → scrapa opciones de regreso (lun/mar)
   Filtra por ventana horaria del día (jue 18-24h, vie 00-19:30h, lun/mar 00-10h)
        ↓
3. Si precio RT ≤ round_trip_threshold (300,000 COP):
   Construye WeekendPairs (outbound + hasta 3 opciones vuelta)
   Aplica regla del domingo (sunday_adventure → solo lunes)
   Cruza fechas con eventos del cache y manual_events.yaml
   Filtra blacklist (config/destinations.yaml)
   Envía UN email consolidado con vuelos + eventos
```

## Configuración

### Rutas de vuelos (`config/routes.yaml`)

```yaml
routes:
  - origin: BAQ
    destination: MDE
    price_threshold: 300000        # COP (one-way fallback)
    round_trip_threshold: 300000   # COP total ida+vuelta
    drop_percentage: 15
    search_days: [thursday, friday]
    return_days: [monday, tuesday]
    search_mode: round_trip

  - origin: MDE
    destination: BAQ
    price_threshold: 300000
    round_trip_threshold: 300000
    drop_percentage: 15
    search_days: [monday]
    search_mode: round_trip

time_windows:
  thursday:
    from: "18:00"
    to:   "23:59"
    note: "Salida después del trabajo"
  friday:
    from: "00:00"
    to:   "19:30"
    note: "Vuelo viernes — hasta 7:30 PM si evento es el sábado"
  monday:
    from: "00:00"
    to:   "10:00"
    note: "Regreso temprano el lunes"
  tuesday:
    from: "00:00"
    to:   "10:00"
    note: "Regreso temprano el martes"
```

### Filtros de tiempo por día

| Día | Ventana | Propósito |
|-----|---------|-----------|
| Jueves | 18:00 – 23:59 | Salida después del trabajo |
| Viernes | 00:00 – 19:30 | Hasta 7:30 PM (cubre eventos del sábado) |
| Lunes | 00:00 – 10:00 | Regreso temprano |
| Martes | 00:00 – 10:00 | Regreso temprano (si aventura termina el lunes) |

### Blacklist de destinos (`config/destinations.yaml`)

```yaml
blacklist:
  ya_fue:
    - Tatacoa
    - Cerro Tusa
  playa:
    - Rincón del Mar
  no_interesa:
    - avistamiento de ballenas
```

### Eventos manuales (`data/manual_events.yaml`)

Para eventos que no vienen de imágenes de agencias:

```yaml
events:
  - name: "Nombre del evento"
    agency: "personal"
    date_start: "2026-10-24"
    date_end:   "2026-10-25"
    price: 0
```

## Arquitectura

```
aventure-tracker/
├── src/aventure_tracker/
│   ├── main.py                           # CLI + orquestador principal
│   ├── config.py                         # Settings (env vars)
│   ├── infrastructure/
│   │   ├── email_notifier.py             # Resend — email HTML
│   │   └── state_manager.py             # Gist state (CI)
│   ├── services/
│   │   ├── flights/
│   │   │   ├── tracker.py               # Lógica RT: FlightFound, WeekendPair, PriceAlert
│   │   │   ├── weekend_pairs.py         # build_weekend_pairs — empareja ida+vuelta
│   │   │   ├── matcher.py              # Cruza vuelos baratos con eventos
│   │   │   ├── price_store.py          # Historial de precios YAML
│   │   │   ├── dates.py                # Cálculo de weekends
│   │   │   └── calendar.py             # Display de calendario
│   │   ├── extraction/
│   │   │   └── inbox_processor.py      # Procesa inbox/ con Gemini/Ollama
│   │   └── shared/
│   │       └── holidays.py             # Festivos colombianos
│   └── scrapers/
│       └── google_flights/             # Playwright RT scraper
│           ├── scraper.py              # scrape_round_trip()
│           └── page_objects.py         # ResultsPage, ConsentHandler
├── config/
│   ├── routes.yaml                     # Rutas, thresholds, ventanas horarias
│   ├── destinations.yaml               # Blacklist de destinos
│   └── holidays.yaml                   # Festivos colombianos
├── data/
│   ├── flight_prices.yaml              # Historial de precios
│   ├── extraction_cache.yaml           # Cache de eventos extraídos
│   └── manual_events.yaml              # Eventos manuales (sin agencia digital)
└── inbox/                              # Imágenes de calendarios de agencias
    ├── brutal/
    └── medellin-bungee/
```

## Development

```bash
# Tests
source .venv/bin/activate
python -m pytest tests/ -v --tb=short

# Con coverage
python -m pytest tests/ --cov=src --cov-report=html

# Linting / formatting
ruff check src/ tests/
ruff format src/ tests/
```

## Notificaciones

| Canal | Estado | Configuración |
|-------|--------|---------------|
| Email (Resend) | ✅ Activo | `RESEND_API_KEY` + `EMAIL_TO` en `.env` |
| Telegram | ⛔ Desactivado | No usar — código existe pero no se activa |

## License

MIT License


## ¿Cómo funciona?

Monitorea vuelos baratos entre Barranquilla y Medellín. Cuando encuentra uno por debajo del precio que defines, busca qué planes de aventura hay disponibles ese fin de semana (según las agencias que sigues) y manda un solo email con todo: vuelo + actividades. Sin hacer nada manual.

```
inbox/brutal/        inbox/medellin-bungee/
  (imágenes JPG/PNG de calendarios de agencias)
          ↓
    Gemini Vision API
    "¿Qué eventos hay en esta imagen?"
          ↓
    extraction_cache.yaml
    { "Canyoning San Carlos": "23 Ago, $180K" }
          ↓                        ↓
  Google Flights              EventMatcher
  (Playwright scraping)       cruza fechas baratas
  BAQ→MDE $358K               con eventos disponibles
  MDE→BAQ $291K ✅            filtra blacklist
          ↓                        ↓
              Resend API
         Email HTML con vuelo + planes ese finde
```

## Stack

| Tecnología | Rol |
|-----------|-----|
| **Python 3.12** | Lenguaje base. `asyncio` para operaciones I/O-bound |
| **Playwright** | Controla Chromium headless para scrapear Google Flights. Google Flights es una SPA sin API pública — la única forma de leer precios es renderizar la página completa |
| **Gemini Vision API** | Modelo multimodal que analiza imágenes de calendarios de agencias y extrae eventos estructurados (nombre, fecha, precio). Alternativa offline: Ollama + minicpm-v |
| **Resend** | API de email transaccional. Se eligió sobre Gmail SMTP para no exponer credenciales personales — solo un API key revocable |
| **Pydantic** | Validación de configuración y lectura de variables de entorno desde `.env` |
| **YAML** | Almacenamiento local: historial de precios, cache de extracción, configuración. Sin base de datos — todo versionable con git |
| **SHA256 hashing** | Cache de imágenes basado en contenido. Si mandas la misma imagen con distinto nombre, no se reprocesa |
| **pytest** | 720 tests unitarios e integración. Scrapers mockeados con `AsyncMock` para no hacer requests reales |

### Decisiones de diseño

- **Sin base de datos** — YAML es suficiente. Todo es legible, versionable y sin setup.
- **Sin servidor** — corre como script local o en CI (GitHub Actions). No hay proceso siempre activo.
- **Blacklist en vez de whitelist** — ves todo lo que ofrecen las agencias *excepto* lo que ya visitaste o no te interesa. Más fácil de mantener.
- **Un solo email** — espera a tener el cuadro completo (vuelo ida + vuelta + eventos) y manda uno. Menos ruido.

## Features

- **Flight Tracking**: Monitorea precios en Google Flights para viajes de fin de semana
  - Rutas: BAQ↔MDE (ida y vuelta)
  - Busca jueves/viernes (ida) y domingo/lunes (vuelta)
  - Hasta 10 semanas de anticipación
  - Alerta cuando precio ≤ umbral configurado en `config/routes.yaml`

- **Event Extraction**: Extrae eventos de imágenes de calendarios de agencias
  - Procesa con Gemini API (~3s/imagen) u Ollama local (~9s/imagen)
  - Cache SHA256 para no reprocesar imágenes ya vistas
  - Agencias: `inbox/brutal/`, `inbox/medellin-bungee/`

- **Reporte Consolidado**: Cuando hay vuelo barato, cruza con eventos disponibles ese finde y envía **un solo email** con todo
  - Template HTML estilo revista de aventuras
  - Filtra destinos ya visitados (`config/destinations.yaml`)
  - Enviado vía Resend (gratis, sin exponer credenciales personales)

## Quick Start

### Requisitos

- Python 3.12+
- Playwright (browser headless)
- Resend API key (gratis en [resend.com](https://resend.com))
- Gemini API key (opcional, gratis en [aistudio.google.com](https://aistudio.google.com/apikey))

### Instalación

```bash
git clone https://github.com/NSnietol/aventure-tracker.git
cd aventure-tracker

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
playwright install chromium
```

### Configuración

Copia `.env.example` a `.env` y completa:

```bash
# Notificaciones por email (Resend)
RESEND_API_KEY=re_tu_api_key
EMAIL_TO=tu@email.com

# Extracción de imágenes (opcional, más rápido que Ollama)
GEMINI_API_KEY=tu_gemini_key

# Threshold overrides (opcional — si no se definen, se usan los valores de config/routes.yaml)
# FLIGHT_PRICE_THRESHOLD=300000     # Precio máximo por tramo en COP (aplica a todas las rutas)
# FLIGHT_BARGAIN_THRESHOLD=110000   # Cualquier aerolínea se incluye si precio ≤ este valor
# FLIGHT_EXTRA_MAX_PRICE=150000     # Precio máximo para aerolíneas extra (Wingo, JetSMART, Avianca)
```

Las variables de threshold también se pueden configurar como **GitHub Secrets** para controlar el comportamiento en CI sin tocar el código.

## Comandos

### Flujo completo (recomendado)

Un solo comando hace todo:
1. Procesa imágenes nuevas del `inbox/` (SHA256 — skip si ya está en cache)
2. Busca vuelos baratos en Google Flights
3. Cruza fechas con eventos de agencias
4. Envía email si hay vuelo bajo el threshold

```bash
# Flujo completo con 2 semanas de anticipación
python -m aventure_tracker.main --mode flights --weeks 2

# Con logs detallados
python -m aventure_tracker.main --mode flights --weeks 2 --verbose

# Sin enviar notificaciones (ver resultados en consola)
python -m aventure_tracker.main --mode flights --weeks 2 --dry-run
```

### Extraer eventos manualmente

```bash
# Procesa imágenes nuevas en inbox/ (standalone)
python scripts/extract_events.py

# Solo una agencia
python scripts/extract_events.py --agency brutal

# Forzar reprocesamiento (ignora cache)
python scripts/extract_events.py --force

# Ver estadísticas del cache
python scripts/extract_events.py --cache-stats
```

### Otros modos

```bash
# Mostrar calendario de vuelos
python -m aventure_tracker.main --mode calendar

# Ejecutar todo (vuelos + actividades Instagram)
python -m aventure_tracker.main --mode all
```

## Flujo completo

```
python -m aventure_tracker.main --mode flights --weeks 2
        ↓
1. Lee inbox/brutal/ + inbox/medellin-bungee/
   Procesa solo imágenes nuevas (SHA256 → skip si ya en cache)
   Extrae eventos con Gemini/Ollama → guarda en data/extraction_cache.yaml
        ↓
2. Busca vuelos baratos en Google Flights (próximos weekends)
        ↓
3. Si precio ≤ threshold (config/routes.yaml):
   Cruza fechas con eventos del cache
   Filtra blacklist (config/destinations.yaml)
   Envía UN email consolidado con vuelos + eventos
```

## Configuración

### Rutas de vuelos (`config/routes.yaml`)

```yaml
routes:
  - origin: BAQ
    destination: MDE
    price_threshold: 300000  # COP ida sencilla
    drop_percentage: 15
    search_days: [thursday, friday]

  - origin: MDE
    destination: BAQ
    price_threshold: 300000
    drop_percentage: 15
    search_days: [sunday, monday]
```

### Filtros de tiempo por día

| Día | Ventana | Propósito |
|-----|---------|-----------|
| Jueves | 18:00 – 23:59 | Salida después del trabajo |
| Viernes | 00:00 – 16:00 | Salida temprano |
| Domingo | 14:00 – 23:59 | Regreso tarde |
| Lunes | 00:00 – 10:00 | Regreso muy temprano |

### Blacklist de destinos (`config/destinations.yaml`)

```yaml
blacklist:
  ya_fue:
    - Tatacoa
    - Cerro Tusa
  playa:
    - Rincón del Mar
  no_interesa:
    - avistamiento de ballenas
```

### Imágenes de agencias (`inbox/`)

```
inbox/
├── brutal/              # Brutal Travel
│   ├── agosto.jpg
│   └── septiembre.png
└── medellin-bungee/     # Medellín Bungee
    └── agosto.jpg
```

## Arquitectura

```
aventure-tracker/
├── src/aventure_tracker/
│   ├── main.py                      # CLI + orquestador principal
│   ├── config.py                    # Settings (env vars)
│   ├── infrastructure/
│   │   ├── email_notifier.py        # Resend — email HTML
│   │   ├── notifier.py              # Telegram (opcional)
│   │   └── state_manager.py         # Gist state (CI)
│   ├── services/
│   │   ├── flight_tracker.py        # Lógica de rastreo de vuelos
│   │   ├── event_matcher.py         # Cruza vuelos baratos con eventos
│   │   ├── flight_price_store.py    # Historial de precios YAML
│   │   ├── flight_dates.py          # Cálculo de weekends
│   │   ├── holidays.py              # Festivos colombianos
│   │   ├── image_event_extractor.py # Gemini / Ollama vision
│   │   └── extraction_cache.py      # Cache SHA256 de imágenes
│   └── scrapers/
│       └── google_flights/          # Playwright scraper
├── scripts/
│   └── extract_events.py            # CLI de extracción de eventos
├── config/
│   ├── routes.yaml                  # Rutas y thresholds
│   ├── destinations.yaml            # Blacklist de destinos
│   └── holidays.yaml                # Festivos colombianos
├── data/
│   ├── flight_prices.yaml           # Historial de precios
│   └── extraction_cache.yaml        # Cache de eventos extraídos
├── inbox/                           # Imágenes de calendarios de agencias
└── email-mockups/                   # Maquetas HTML del email
```

## Development

```bash
# Tests
source .venv/bin/activate
pytest tests/ -v --tb=short

# Con coverage
pytest tests/ --cov=src --cov-report=html

# Linting / formatting
ruff check src/ tests/
ruff format src/ tests/
```

## Notificaciones

| Canal | Estado | Configuración |
|-------|--------|---------------|
| Email (Resend) | ✅ Activo | `RESEND_API_KEY` + `EMAIL_TO` en `.env` |
| Telegram | Opcional | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` en `.env` |

Si ambos están configurados, se envían los dos.

## License

MIT License
