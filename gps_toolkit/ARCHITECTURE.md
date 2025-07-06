# GPS Toolkit Architecture

This document provides a comprehensive overview of the GPS Toolkit's modular architecture, design principles, and implementation details.

## Table of Contents

1. [Design Principles](#design-principles)
2. [Architectural Overview](#architectural-overview)
3. [Core Components](#core-components)
4. [Service Layer](#service-layer)
5. [Async Processing](#async-processing)
6. [Data Flow](#data-flow)
7. [Extension Points](#extension-points)
8. [Dependencies](#dependencies)

## Design Principles

### 1. Modularity
Each service is independent and self-contained, handling its own dependencies and gracefully degrading when optional libraries are unavailable.

### 2. Separation of Concerns
- **Core**: Basic functionality (validation, extraction, utilities)
- **Services**: Specialized processing (location, weather, image analysis)
- **Processors**: Orchestration (async coordination, formatting, timing)
- **Config**: Configuration management

### 3. Fail-Safe Operation
Individual service failures don't crash the entire process. Each service returns appropriate error indicators while allowing other services to continue.

### 4. Performance-Aware
- Lazy loading of optional dependencies
- Async processing for I/O-bound operations
- Efficient memory usage through streaming and chunking
- Timing context for performance monitoring

### 5. Extensibility
New services can be added without modifying existing code. Clear interfaces and dependency injection patterns enable easy extension.

## Architectural Overview

```
gps_toolkit/
├── main.py                     # Main orchestrator class
├── cli.py                      # Command-line interface
├── __init__.py                 # Package exports
├── config/                     # Configuration management
│   ├── __init__.py
│   └── settings.py
├── core/                       # Core utilities and models
│   ├── __init__.py
│   ├── extractors.py           # EXIF data extraction
│   ├── models.py               # Data models and types
│   ├── utils.py                # Utility functions
│   └── validators.py           # Input validation
├── processors/                 # Processing coordination
│   ├── __init__.py
│   ├── async_coordinator.py    # Async task coordination
│   ├── json_formatter.py       # Output formatting
│   └── timing.py               # Performance timing
└── services/                   # Independent service modules
    ├── __init__.py
    ├── image_analysis.py       # Face, QR, color analysis
    ├── location.py             # Geocoding and location data
    ├── models/                 # Pre-trained models
    ├── text_extraction.py      # OCR and text processing
    ├── weather.py              # Weather and environmental data
    └── web_content.py          # Web content extraction
```

## Core Components

### Main Orchestrator (`main.py`)

The `GPSLocationExtractor` class serves as the central coordinator:

```python
class GPSLocationExtractor:
    """
    Main orchestrator that coordinates all services to extract comprehensive
    information from images including location, weather, text, faces, and more.
    """
    
    def __init__(self, debug: bool = False):
        # Initialize all services lazily
        self.location_service = LocationService(self.user_agent)
        self.weather_service = WeatherService()
        self.image_analysis_service = ImageAnalysisService()
        self.text_extraction_service = TextExtractionService()
        self.web_content_service = WebContentService()
        self.async_coordinator = AsyncCoordinator(debug=debug)
```

**Key Responsibilities:**
- Service initialization and coordination
- Request routing to appropriate services
- Result aggregation and formatting
- Error handling and recovery
- Debug information collection

### Command-Line Interface (`cli.py`)

Provides a comprehensive CLI with:
- Intuitive argument parsing
- Feature toggles for all services
- Output format options (JSON, text, debug)
- Async processing controls
- Strategy selection for performance tuning

### Configuration System (`config/`)

Centralized configuration management:

```python
# config/settings.py
class Settings:
    USER_AGENT = "GPS-Toolkit/2.0"
    MAX_DOMINANT_COLORS = 5
    FACE_DETECTION_MODEL_PATH = "services/models/"
    DEFAULT_TIMEOUT = 30
    
    # Feature toggles
    ENABLE_FACE_DETECTION = True
    ENABLE_OCR = True
    ENABLE_WEB_CONTENT = True
```

## Service Layer

Each service is designed as an independent module with clear interfaces:

### 1. Location Service (`services/location.py`)

**Purpose**: Geocoding and location-related data enrichment

**Capabilities:**
- Reverse geocoding (coordinates → address)
- Elevation data retrieval
- Points of interest discovery
- Nearby venue information
- Holiday and historical event data

**Key Methods:**
```python
class LocationService:
    def reverse_geocode(self, lat: float, lon: float) -> Dict[str, Any]
    def get_elevation(self, lat: float, lon: float) -> Optional[float]
    def get_nearby_pois(self, lat: float, lon: float) -> List[Dict[str, Any]]
    def get_enhanced_nearby_venues(self, lat: float, lon: float) -> List[Dict[str, Any]]
    def get_holiday_info(self, lat: float, lon: float, date: str) -> Optional[Dict[str, Any]]
```

**APIs Used:**
- OpenStreetMap Nominatim (geocoding)
- Open Elevation API
- Overpass API (POIs and venues)
- Nager.Date API (holidays)
- Wikipedia API (historical events)

### 2. Weather Service (`services/weather.py`)

**Purpose**: Weather and environmental data

**Capabilities:**
- Historical weather data
- Air quality information (AQI, PM2.5, PM10, ozone)
- UV index with safety categories
- Moon phase calculations
- Astronomical data (sunrise, sunset)

**Key Methods:**
```python
class WeatherService:
    def get_enhanced_weather_data(self, lat: float, lon: float, 
                                 datetime_obj: Optional[datetime]) -> Optional[Dict[str, Any]]
    def calculate_moon_phase(self, lat: float, lon: float, 
                           datetime_obj: datetime) -> Optional[Dict[str, Any]]
```

**APIs Used:**
- Open-Meteo API (weather and air quality)
- PyEphem library (astronomical calculations)

### 3. Image Analysis Service (`services/image_analysis.py`)

**Purpose**: Computer vision and image processing

**Capabilities:**
- Optimized face detection using DNN models
- QR code and barcode scanning
- Dominant color extraction with clustering
- Image preprocessing and enhancement

**Key Methods:**
```python
class ImageAnalysisService:
    def detect_faces(self, image_path: str) -> Optional[Dict[str, Any]]
    def detect_qr_codes(self, image_path: str) -> Optional[Dict[str, Any]]
    def extract_dominant_colors(self, image_path: str, 
                              max_colors: int = 5) -> Optional[Dict[str, Any]]
```

**Libraries Used:**
- OpenCV (face detection, image processing)
- face_recognition (alternative face detection)
- pyzbar (QR code detection)
- scikit-learn (color clustering)
- webcolors (color naming)

### 4. Text Extraction Service (`services/text_extraction.py`)

**Purpose**: OCR and text processing

**Capabilities:**
- OCR text extraction with preprocessing
- Language detection
- URL extraction and validation
- Text cleaning and normalization

**Key Methods:**
```python
class TextExtractionService:
    def extract_text_from_image(self, image_path: str) -> Optional[Dict[str, Any]]
    def _preprocess_image_for_ocr(self, image) -> Any
    def _extract_text_with_fallbacks(self, image) -> str
```

**Libraries Used:**
- pytesseract (OCR engine)
- langdetect (language identification)
- Pillow (image preprocessing)

### 5. Web Content Service (`services/web_content.py`)

**Purpose**: Web content extraction and analysis

**Capabilities:**
- Web page content extraction
- URL validation and normalization
- Content summarization
- Metadata extraction

**Key Methods:**
```python
class WebContentService:
    def extract_web_content(self, urls: List[str]) -> Optional[Dict[str, Any]]
    def _extract_single_url_content(self, url: str) -> Optional[Dict[str, Any]]
```

**Libraries Used:**
- trafilatura (content extraction)
- requests (HTTP client)

## Async Processing

The async processing system enables concurrent execution of independent operations for significant performance improvements.

### AsyncCoordinator (`processors/async_coordinator.py`)

**Purpose**: Orchestrate parallel execution of independent tasks

**Key Components:**

#### 1. TaskGroup
Represents a group of independent tasks that can run concurrently:

```python
class TaskGroup:
    def __init__(self, name: str, debug: bool = False)
    def add_task(self, name: str, func: Callable, *args, **kwargs)
    async def execute(self) -> Dict[str, Any]
```

#### 2. AsyncCoordinator
Manages multiple task groups and their execution:

```python
class AsyncCoordinator:
    def create_group(self, name: str) -> TaskGroup
    async def execute_groups_concurrently(self) -> Dict[str, Any]
    async def execute_all_groups(self) -> Dict[str, Any]
```

#### 3. Processing Strategies

Different strategies for grouping operations:

- **Parallel** (default): Balanced grouping for optimal performance
  ```
  Group 1: Location data (geocoding, weather, elevation)
  Group 2: Image analysis (faces, QR, OCR, colors)
  Group 3: Location enrichment (venues, POIs, holidays)
  ```

- **Maximal**: Maximum parallelism (one operation per group)
  ```
  Group 1: Geocoding
  Group 2: Weather
  Group 3: Faces
  Group 4: OCR
  Group 5: QR codes
  Group 6: Colors
  ```

- **Conservative**: Conservative grouping for limited resources
  ```
  Group 1: Core data (geocoding, weather)
  Group 2: All analysis (faces, OCR, QR, colors, venues)
  ```

- **Sequential**: No parallelism (compatibility mode)

### Async Timing Context

Provides timing information for async operations:

```python
async with AsyncTimingContext("Operation Name", debug=True):
    result = await some_async_operation()
```

## Data Flow

### 1. Image Input and Validation
```
Image File → validate_image_file() → Path validation → EXIF extraction
```

### 2. Core Data Extraction
```
EXIF Data → ExifExtractor.extract_exif_data() → {
    coordinates: {lat, lon},
    datetime_info: {...},
    camera_info: {...},
    exposure_settings: {...}
}
```

### 3. Service Processing (Async)
```
Phase 1: Core Location Data
├── Reverse Geocoding (location_service)
├── Weather Data (weather_service)
└── Elevation (location_service)

Phase 2: Image Analysis (Parallel)
├── Face Detection (image_analysis_service)
├── QR Code Detection (image_analysis_service)
├── OCR Text Extraction (text_extraction_service)
└── Color Analysis (image_analysis_service)

Phase 3: Location Enrichment (Parallel)
├── Nearby Venues (location_service)
├── Points of Interest (location_service)
├── Holiday Information (location_service)
└── Historical Events (location_service)

Phase 4: Web Content (Sequential, depends on URLs from Phase 2)
└── Web Content Extraction (web_content_service)
```

### 4. Result Aggregation and Formatting
```
Service Results → _merge_task_results() → Format Selection → {
    JSON (default),
    Debug JSON (with timing),
    Human-readable text
}
```

## Extension Points

### Adding New Services

1. **Create Service Module**:
```python
# services/new_service.py
class NewService:
    def __init__(self):
        # Initialize service
        pass
    
    def process_data(self, *args) -> Optional[Dict[str, Any]]:
        # Implement processing logic
        try:
            # Process data
            return {"result": "data"}
        except Exception as e:
            return {"error": str(e), "available": False}
```

2. **Add to Main Orchestrator**:
```python
# main.py
class GPSLocationExtractor:
    def __init__(self, debug: bool = False):
        # ... existing services ...
        self.new_service = NewService()
    
    def process(self, image_path: str, **options) -> Dict[str, Any]:
        # ... existing processing ...
        
        if options.get('new_feature'):
            with TimingContext("New Feature Processing", self.debug):
                new_data = self.new_service.process_data(image_path)
                if new_data and new_data.get('available'):
                    result['new_feature'] = new_data
```

3. **Add CLI Options**:
```python
# cli.py
parser.add_argument('--new-feature', action='store_true',
                    help='Enable new feature processing')
```

### Adding Processing Strategies

Create custom task grouping strategies:

```python
# processors/async_coordinator.py
class AsyncProcessingStrategy:
    @staticmethod
    def get_custom_strategy() -> List[List[str]]:
        return [
            ['operation1', 'operation2'],  # Group 1
            ['operation3', 'operation4'],  # Group 2
            ['operation5']                 # Group 3
        ]
```

### Adding Output Formats

Extend the JSON formatter:

```python
# processors/json_formatter.py
def build_custom_format(data: Dict[str, Any]) -> Dict[str, Any]:
    # Custom formatting logic
    return formatted_data
```

## Dependencies

### Core Dependencies (Required)
- **Python 3.7+**: Runtime environment
- **Pillow**: Image processing
- **numpy**: Numerical operations
- **requests**: HTTP client for API calls

### System Dependencies
- **exiftool**: EXIF metadata extraction
- **tesseract**: OCR engine (optional)
- **zbar**: QR code library (optional)

### Optional Dependencies

#### OCR Features (`pip install .[ocr]`)
- **pytesseract**: Python wrapper for Tesseract
- **langdetect**: Language detection

#### Face Detection (`pip install .[face]`)
- **face-recognition**: Face detection library
- **opencv-contrib-python**: Computer vision (alternative/fallback)

#### Color Analysis (`pip install .[color]`)
- **scikit-learn**: Color clustering algorithms
- **webcolors**: Color name mapping

#### Astronomical Features (`pip install .[moon]`)
- **ephem**: Astronomical calculations

#### Web Content (`pip install .[web]`)
- **trafilatura**: Web content extraction

### Dependency Management

Services handle missing dependencies gracefully:

```python
class ImageAnalysisService:
    def __init__(self):
        self.face_detection_available = False
        try:
            import face_recognition
            self.face_detection_available = True
        except ImportError:
            try:
                import cv2
                self.face_detection_available = True
                self.use_opencv = True
            except ImportError:
                pass
    
    def detect_faces(self, image_path: str) -> Optional[Dict[str, Any]]:
        if not self.face_detection_available:
            return {"available": False, "error": "Face detection libraries not installed"}
        
        # Proceed with detection
```

## Performance Considerations

### Memory Management
- Lazy loading of models and heavy dependencies
- Streaming processing for large images
- Cleanup of temporary resources

### CPU Optimization
- Thread pool execution for CPU-bound operations
- Optimized image preprocessing
- Efficient algorithms for color clustering

### I/O Optimization
- Concurrent API requests
- Connection pooling for HTTP requests
- Caching of frequently accessed data

### Error Handling
- Graceful degradation when services fail
- Retry logic for transient failures
- Comprehensive error reporting in debug mode

This architecture provides a solid foundation for the GPS Toolkit while maintaining flexibility for future enhancements and optimizations.