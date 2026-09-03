"""CSS selectors and locators for Google Flights UI elements.

Each class maps to a distinct section of the Google Flights web interface.
Selectors use aria-labels and semantic attributes (not fragile CSS class names)
wherever possible for resilience against UI updates.
"""

# =============================================================================
# URLs
# =============================================================================

BASE_URL = "https://www.google.com/travel/flights"

EXPLORE_URL_TEMPLATE = (
    "https://www.google.com/travel/flights?"
    "q=Flights%20from%20{origin}%20to%20{destination}%20on%20{date}"
    "&curr=COP&hl=es-419"
)

# =============================================================================
# Timeout defaults (milliseconds)
# =============================================================================

# How long to wait for the results page to load
RESULTS_TIMEOUT_MS: int = 15_000

# How long to wait for individual UI interactions (consent, date picker, etc.)
INTERACTION_TIMEOUT_MS: int = 5_000

# Short pause after clicking to let animations settle
ANIMATION_PAUSE_MS: int = 500


# =============================================================================
# Search Form
# -- The hero section at the top of the page with origin/destination/date inputs
# =============================================================================


class SearchFormLocators:
    """The main search bar: origin, destination, dates, trip type."""

    SEARCH_CONTAINER = "[data-flt-ve='hero']"

    # Origin / Destination text fields
    ORIGIN_INPUT = "input[aria-label='¿Desde dónde?'], input[aria-label*='origen'], input[placeholder*='origen']"
    DESTINATION_INPUT = "input[aria-label='¿A dónde quieres ir? '], input[aria-label*='destino'], input[placeholder*='destino']"
    SWAP_BUTTON = "button[aria-label*='Intercambiar']"

    # Date inputs (one-way or round-trip)
    DEPARTURE_DATE_INPUT = "input[aria-label='Salida'], input[placeholder='Salida']"
    RETURN_DATE_INPUT = "input[aria-label='Regreso'], input[placeholder='Regreso'], input[aria-label*='Vuelta']"

    # Trip type toggle
    TRIP_TYPE_DROPDOWN = "button[aria-label*='tipo de viaje']"
    ONE_WAY_OPTION = "[data-value='2']"
    ROUND_TRIP_OPTION = "[data-value='1']"

    SEARCH_BUTTON = "button[aria-label='Buscar'], button[jsname='c6xFrd']"


# =============================================================================
# Date Picker / Calendar Grid
# -- Opens when clicking a date input. Shows min prices per day.
# -- Structure (from HTML inspection):
#      <div role="gridcell" data-iso="2026-09-08">
#        <div jsname="qCDwBb"
#             aria-label=", 166620 Colombian pesos, Cheapest price">
#          $167K
#        </div>
#      </div>
# =============================================================================


class CalendarLocators:
    """The date-picker calendar grid that shows one price per day."""

    # The container that opens after clicking the date input
    CALENDAR_DIALOG = "[role='dialog']"

    # A single day cell — has data-iso attribute with the date
    DAY_CELL = "[role='gridcell'][data-iso]"

    # A day cell that is selectable (not grayed out, not in the past)
    SELECTABLE_DAY = "[role='gridcell'][data-iso]:not([aria-hidden='true'])"

    # The price label inside a day cell.
    # aria-label format: ", 166620 Colombian pesos" or
    #                    ", 166620 Colombian pesos, Cheapest price"
    DAY_PRICE_LABEL = "[jsname='qCDwBb'][aria-label*='pesos']"

    # The cheapest day in the visible range (has extra CSS class)
    CHEAPEST_DAY_PRICE = "[jsname='qCDwBb'].RZ6mCd"

    # Close / Done button
    DONE_BUTTON = "button[aria-label='Listo'], button[aria-label='Done']"


# =============================================================================
# Results Page
# -- The list of flights shown after a search
# =============================================================================


class ResultsLocators:
    """The flight results list page after a search is submitted."""

    RESULTS_CONTAINER = "[role='main']"
    LOADING_INDICATOR = "[aria-busy='true']"

    # Flight cards in the list
    FLIGHT_CARD = "li.pIav2d, [data-ved] > div[jsname]"
    FLIGHT_LIST_ITEM = "ul[role='list'] > li"

    # Price on a card (data-gs contains encoded flight data)
    PRICE_ELEMENT = "[data-gs], .YMlIz"
    PRICE_TEXT = "span[data-gs], .YMlIz span"

    # Flight detail fields within a card
    AIRLINE_NAME = ".sSHqwe, [data-gs] ~ div"
    DEPARTURE_TIME = "span[aria-label*='Salida'], .zxVSec span"
    ARRIVAL_TIME = "span[aria-label*='llegada'], .zxVSec span:last-child"
    DURATION = ".gvkrdb, .Ak5kof"
    STOPS_INFO = ".EfT7Ae, .BbR8Ec"

    # Section headers
    BEST_FLIGHTS_HEADER = "h3:has-text('Mejores vuelos')"
    CHEAPEST_FLIGHTS_HEADER = "h3:has-text('Más baratos')"
    CHEAPEST_PRICE = ".YMlIz .FpEdX span"

    # No-results state
    NO_RESULTS = "[data-gs]:has-text('No se encontraron')"

    # Expandable card details
    EXPAND_BUTTON = "button[aria-expanded]"
    EXPANDED_DETAILS = "[aria-expanded='true'] ~ div"


# =============================================================================
# Filters Panel
# -- The sidebar/sheet with stops, airlines, times, price controls
# =============================================================================


class FiltersLocators:
    """Filter controls for stops, airlines, departure times, and price."""

    # Stops
    STOPS_DROPDOWN = "button[aria-label*='Escalas']"
    NONSTOP_OPTION = "[data-value='0']"
    ONE_STOP_OPTION = "[data-value='1']"

    # Airlines
    AIRLINES_DROPDOWN = "button[aria-label*='aerolíneas']"
    AIRLINE_CHECKBOX = "input[type='checkbox'][aria-label*='{airline}']"

    # Time range sliders
    DEPARTURE_TIME_SLIDER = "[aria-label*='hora de salida']"
    ARRIVAL_TIME_SLIDER = "[aria-label*='hora de llegada']"

    # Price slider
    PRICE_SLIDER = "[aria-label*='precio']"

    # Duration slider
    DURATION_SLIDER = "[aria-label*='duración']"

    APPLY_FILTERS = "button[aria-label*='Aplicar']"


# =============================================================================
# Consent / Cookie Dialog
# -- Shown on first visit or after cookie expiry
# =============================================================================


class ConsentLocators:
    """Google cookie consent dialog."""

    CONSENT_DIALOG = "[role='dialog']"
    ACCEPT_ALL_BUTTON = "button:has-text('Aceptar todo')"
    REJECT_ALL_BUTTON = "button:has-text('Rechazar todo')"
    CLOSE_BUTTON = "button[aria-label='Cerrar']"
