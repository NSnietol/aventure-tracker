# Adventure Tracker

Sistema local y offline para rastrear vuelos baratos y extraer eventos de calendarios de agencias de viajes, sin dependencias de APIs externas de pago.

## Features

- **Flight Tracking**: Monitoreo de precios en Google Flights para viajes de fin de semana
  - Rutas: BAQ↔MDE, CTG↔MDE (ida y vuelta)
  - Busca jueves/viernes (ida) y domingo/lunes (vuelta)
  - 10 semanas de anticipación (hasta ~2.5 meses)
  - Alertas cuando precio ≤ umbral ($150,000 COP por trayecto)

- **Calendar Event Extraction**: Extracción de eventos de imágenes de calendarios
  - Procesamiento con Ollama + minicpm-v (100% local, offline)
  - Soporte para múltiples agencias de viajes
  - Detección de fechas, precios y destinos

- **Local Storage**: Todo se guarda localmente
  - Precios de vuelos: `data/flight_prices.yaml`
  - Eventos extraídos: `data/events.yaml`
  - Sin necesidad de GitHub Gist ni APIs externas

- **Colombian Holidays**: Soporte para puentes (fines de semana largos)

## Quick Start

### Prerequisites

- Python 3.12+
- [Ollama](https://ollama.ai/) con modelo `minicpm-v`
- Playwright browsers

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/aventure-tracker.git
cd aventure-tracker

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Install Ollama (macOS)
brew install ollama

# Pull the vision model
ollama pull minicpm-v
```

### Running

```bash
# Track flight prices (10 weeks, all routes)
python src/aventure_tracker/main.py --mode flights --dry-run

# Extract events from agency calendars
python scripts/extract_events.py --source agent-calendars/brutal

# Run with fewer weeks
python src/aventure_tracker/main.py --mode flights --weeks 4 --dry-run
```

## Configuration

### Flight Routes (`config/routes.yaml`)

```yaml
routes:
  # Outbound (Thursday/Friday)
  - origin: BAQ
    destination: MDE
    price_threshold: 150000  # COP per leg
    drop_percentage: 15
  
  - origin: CTG
    destination: MDE
    price_threshold: 150000
    drop_percentage: 15

  # Return (Sunday/Monday)
  - origin: MDE
    destination: BAQ
    price_threshold: 150000
    drop_percentage: 15

  - origin: MDE
    destination: CTG
    price_threshold: 150000
    drop_percentage: 15
```

### Holidays (`config/holidays.yaml`)

```yaml
holidays:
  2026:
    - date: "2026-01-06"
      name: "Reyes Magos"
    - date: "2026-03-23"
      name: "San José"
    # ... más festivos
```

## Flight Data

Los precios se guardan en `data/flight_prices.yaml`:

```yaml
# All prices are ONE-WAY (solo ida)
# Currency: COP (Colombian Pesos)

updated_at: '2026-08-12T10:56:08'
routes:
  BAQ-MDE_2026-08-27:
    route: BAQ-MDE
    travel_date: '2026-08-27'
    records:
    - price: 175691
      checked_at: '2026-08-12T10:38:41'
```

### Search Pattern

| Día | Dirección | Propósito |
|-----|-----------|-----------|
| Jueves | →MDE | Salida tarde (6pm+) |
| Viernes | →MDE | Salida temprano |
| Domingo | MDE→ | Regreso tarde (2pm+) |
| Lunes | MDE→ | Regreso temprano (antes 10am) |

## Calendar Event Extraction

### Setup Agency Images

```
agent-calendars/
└── brutal/           # Agencia "Brutal Adventures"
    ├── agosto.png
    ├── septiembre.png
    └── octubre.png
```

### Run Extraction

```bash
# Verifica Ollama, inicia servidor si necesario, extrae eventos
python scripts/extract_events.py --source agent-calendars/brutal
```

El script:
1. Verifica que Ollama esté instalado
2. Verifica que el modelo `minicpm-v` esté disponible
3. Inicia el servidor Ollama si no está corriendo
4. Procesa cada imagen y extrae eventos
5. Guarda resultados en `data/events.yaml`

## Architecture

```
aventure-tracker/
├── src/aventure_tracker/
│   ├── main.py                 # CLI principal
│   ├── models/
│   │   ├── flight.py           # RouteConfig, WeekendTrip, FlightResult
│   │   └── event.py            # ExtractedEvent
│   ├── services/
│   │   ├── flight_tracker.py   # Orquestador de vuelos
│   │   ├── flight_dates.py     # Cálculo de fechas
│   │   ├── flight_price_store.py # Persistencia YAML
│   │   ├── holidays.py         # Festivos colombianos
│   │   └── image_event_extractor.py # Ollama vision
│   └── scrapers/
│       └── google_flights/     # Scraper de Google Flights
├── scripts/
│   └── extract_events.py       # Script de extracción
├── config/
│   ├── routes.yaml             # Rutas de vuelos
│   └── holidays.yaml           # Festivos
├── data/
│   ├── flight_prices.yaml      # Historial de precios (tracked)
│   └── agencies/               # Eventos extraídos (tracked)
└── agent-calendars/            # Imágenes de calendarios
```

## Development

### Running Tests

```bash
# Activate venv
source .venv/bin/activate

# All tests
pytest tests/ -v --tb=short

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### Code Quality

```bash
# Linting
ruff check src/ tests/

# Formatting  
ruff format src/ tests/
```

## How It Works

### Flight Tracking Flow

1. `FlightDateCalculator` genera los próximos 10 weekends
2. `HolidayService` identifica puentes
3. Para cada ruta (4 rutas: ida/vuelta × BAQ/CTG):
   - Rutas →MDE: busca jueves + viernes
   - Rutas MDE→: busca domingo + lunes
4. `GoogleFlightsScraper` obtiene precios de Google Flights
5. `FlightPriceStore` guarda historial en YAML local
6. Genera alertas si precio ≤ umbral

### Event Extraction Flow

1. `extract_events.py` valida Ollama y modelo
2. Para cada imagen en el directorio:
   - Envía imagen a Ollama (minicpm-v)
   - Modelo extrae eventos (fecha, destino, precio, descripción)
   - Calcula confidence score
3. Guarda eventos en `data/events.yaml`

## Offline Capabilities

El sistema está diseñado para funcionar sin APIs externas de pago:

| Componente | Solución Offline |
|------------|------------------|
| Vision/OCR | Ollama + minicpm-v (local) |
| Persistencia | YAML files (git tracked) |
| Web scraping | Playwright (headless) |

Solo requiere conexión a internet para:
- Scraping de Google Flights
- (Opcional) Telegram notifications

## License

MIT License
