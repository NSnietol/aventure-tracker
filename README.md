# Adventure Tracker

Sistema local para rastrear vuelos baratos y cruzarlos con eventos de agencias de aventura, enviando una notificación consolidada por email cuando hay un finde que vale la pena.

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
git clone https://github.com/yourusername/aventure-tracker.git
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
```

## Comandos

### Rastrear vuelos (flujo completo)

```bash
# Busca vuelos baratos + cruza con eventos + envía email si hay alerta
aventure-tracker --mode flights

# Con más semanas de anticipación
aventure-tracker --mode flights --weeks 4

# Sin enviar notificaciones (solo ver resultados)
aventure-tracker --mode flights --dry-run

# Con logs detallados
aventure-tracker --mode flights --verbose
```

### Extraer eventos de agencias

```bash
# Procesa imágenes nuevas en inbox/ (Gemini si hay API key, sino Ollama)
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
# Ver solo actividades de Instagram (sin vuelos)
aventure-tracker --mode activities

# Mostrar calendario de vuelos
aventure-tracker --mode calendar

# Ejecutar todo (vuelos + actividades)
aventure-tracker
```

## Flujo completo

```
1. python scripts/extract_events.py
        ↓
   Lee inbox/brutal/ + inbox/medellin-bungee/
   Extrae eventos con Gemini → guarda en data/extraction_cache.yaml

2. aventure-tracker --mode flights
        ↓
   Busca vuelos baratos en Google Flights (próximos weekends)
        ↓
   Si encuentra precio ≤ threshold:
     Cruza fechas con eventos del cache
     Filtra blacklist (destinations.yaml)
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
