"""Configuration settings and constants for GPS Toolkit"""

import os

# API URLs
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_ELEVATION_URL = "https://api.open-elevation.com/api/v1/lookup"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
NAGER_DATE_API_URL = "https://date.nager.at/api/v3/PublicHolidays"

# Request settings
REQUEST_TIMEOUT_S = int(os.getenv("GPS_TOOLKIT_REQUEST_TIMEOUT_S", "15"))
USER_AGENT = os.getenv("GPS_TOOLKIT_USER_AGENT", "EnhancedLocationFinder/3.0")

# URL validation settings
URL_VALIDATION_TIMEOUT = 2.0  # Timeout for DNS resolution per URL
MAX_CONCURRENT_URL_VALIDATIONS = 10  # Max concurrent DNS validations
WEB_CONTENT_PING_TIMEOUT = 5.0  # Timeout for connectivity testing
WEB_CONTENT_EXTRACTION_TIMEOUT = 10.0  # Timeout for content extraction per URL
MAX_CONCURRENT_WEB_EXTRACTIONS = 5  # Max concurrent web content extractions
ENABLE_URL_CONNECTIVITY_CHECK = True  # Pre-check URL connectivity before extraction
WEB_CONTENT_MAX_LENGTH = 5000  # Maximum content length before truncation
WEB_CONTENT_RATE_LIMIT_DELAY = 0.5  # Delay between web requests in seconds
MAX_URLS_TO_PROCESS = 20  # Maximum URLs to process from OCR/QR codes

# File processing limits
MAX_IMAGE_SIZE_BYTES = int(os.getenv("GPS_TOOLKIT_MAX_IMAGE_SIZE_MB", "20")) * 1024 * 1024  # Default 20 MB

# Search radius settings
VENUE_SEARCH_RADIUS_M = 500
POI_SEARCH_RADIUS_M = 500

# Result limits
MAX_VENUES_PER_TYPE = 5
MAX_POIS = 5
MAX_FACES = 10
MAX_QR_CODES = 10
MAX_DOMINANT_COLORS = 5

# Google Calendar API scopes
GOOGLE_CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

# Feature availability flags (set during import)
HAS_OCR = False
HAS_FACE_RECOGNITION = False
HAS_OPENCV = False
HAS_QR_DETECTOR = False
HAS_SKLEARN = False
HAS_EPHEM = False
HAS_WEBCOLORS = False
HAS_GOOGLE_CALENDAR = False
HAS_TRAFILATURA = False