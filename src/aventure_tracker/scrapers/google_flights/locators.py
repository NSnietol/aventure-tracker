"""CSS selectors and XPath locators for Google Flights page elements."""

# =============================================================================
# Google Flights URL Templates
# =============================================================================

# Base URL for Google Flights
BASE_URL = "https://www.google.com/travel/flights"

# Direct search URL template
# Format: origin, destination, date (YYYY-MM-DD), passengers
SEARCH_URL_TEMPLATE = (
    "https://www.google.com/travel/flights/search"
    "?tfs=CBwQAhoeEgoyMDI1LTAzLTE1agcIARIDezB9cgcIARIDezF9&curr=COP&hl=es"
)

# Simplified URL that works with the explore view
EXPLORE_URL_TEMPLATE = (
    "https://www.google.com/travel/flights?"
    "q=Flights%20from%20{origin}%20to%20{destination}%20on%20{date}"
    "&curr=COP&hl=es-419"
)


# =============================================================================
# Search Form Locators
# =============================================================================


class SearchFormLocators:
    """Locators for the flight search form."""

    # Main search container
    SEARCH_CONTAINER = "[data-flt-ve='hero']"

    # Origin/Destination inputs
    ORIGIN_INPUT = "input[aria-label*='origen'], input[placeholder*='origen']"
    DESTINATION_INPUT = "input[aria-label*='destino'], input[placeholder*='destino']"

    # Swap button
    SWAP_BUTTON = "button[aria-label*='Intercambiar']"

    # Date inputs
    DEPARTURE_DATE_INPUT = "input[aria-label*='Salida'], input[placeholder*='Salida']"
    RETURN_DATE_INPUT = "input[aria-label*='Vuelta'], input[placeholder*='Vuelta']"

    # Trip type selector (one-way, round-trip)
    TRIP_TYPE_DROPDOWN = "button[aria-label*='tipo de viaje']"
    ONE_WAY_OPTION = "[data-value='2']"
    ROUND_TRIP_OPTION = "[data-value='1']"

    # Search button
    SEARCH_BUTTON = "button[aria-label*='Buscar'], button[aria-label*='Explorar']"

    # Calendar
    CALENDAR_CONTAINER = "[role='dialog']"
    CALENDAR_DAY = "[role='button'][data-iso]"
    CALENDAR_DONE_BUTTON = "button[aria-label='Listo']"


# =============================================================================
# Results Page Locators
# =============================================================================


class ResultsLocators:
    """Locators for the flight search results page."""

    # Results container
    RESULTS_CONTAINER = "[role='main']"

    # Loading indicator
    LOADING_INDICATOR = "[aria-busy='true']"

    # Flight result items - multiple possible selectors
    FLIGHT_CARD = "li.pIav2d, [data-ved] > div[jsname]"
    FLIGHT_LIST_ITEM = "ul[role='list'] > li"

    # Price elements
    PRICE_ELEMENT = "[data-gs], .YMlIz"
    PRICE_TEXT = "span[data-gs], .YMlIz span"

    # Flight details within a card
    AIRLINE_NAME = ".sSHqwe, [data-gs] ~ div"
    DEPARTURE_TIME = "span[aria-label*='Salida'], .zxVSec span"
    ARRIVAL_TIME = "span[aria-label*='llegada'], .zxVSec span:last-child"
    DURATION = ".gvkrdb, .Ak5kof"
    STOPS_INFO = ".EfT7Ae, .BbR8Ec"

    # Best flights section
    BEST_FLIGHTS_HEADER = "h3:has-text('Mejores vuelos')"
    BEST_FLIGHTS_LIST = "[aria-label*='Mejores vuelos'] ul"

    # Cheapest flights section
    CHEAPEST_FLIGHTS_HEADER = "h3:has-text('Más baratos')"
    CHEAPEST_PRICE = ".YMlIz .FpEdX span"

    # No results message
    NO_RESULTS = "[data-gs]:has-text('No se encontraron')"

    # Expandable card
    EXPAND_BUTTON = "button[aria-expanded]"
    EXPANDED_DETAILS = "[aria-expanded='true'] ~ div"


# =============================================================================
# Filters Locators
# =============================================================================


class FiltersLocators:
    """Locators for flight filters."""

    # Stops filter
    STOPS_DROPDOWN = "button[aria-label*='Escalas']"
    NONSTOP_OPTION = "[data-value='0']"
    ONE_STOP_OPTION = "[data-value='1']"

    # Airlines filter
    AIRLINES_DROPDOWN = "button[aria-label*='aerolíneas']"
    AIRLINE_CHECKBOX = "input[type='checkbox'][aria-label*='{airline}']"

    # Time filters
    DEPARTURE_TIME_SLIDER = "[aria-label*='hora de salida']"
    ARRIVAL_TIME_SLIDER = "[aria-label*='hora de llegada']"

    # Price filter
    PRICE_SLIDER = "[aria-label*='precio']"

    # Duration filter
    DURATION_SLIDER = "[aria-label*='duración']"

    # Apply filters button
    APPLY_FILTERS = "button[aria-label*='Aplicar']"


# =============================================================================
# Cookie/Consent Locators
# =============================================================================


class ConsentLocators:
    """Locators for cookie consent and other dialogs."""

    # Google consent dialog
    CONSENT_DIALOG = "[role='dialog']"
    ACCEPT_ALL_BUTTON = "button:has-text('Aceptar todo')"
    REJECT_ALL_BUTTON = "button:has-text('Rechazar todo')"

    # Generic close button
    CLOSE_BUTTON = "button[aria-label='Cerrar']"
