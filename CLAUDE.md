# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project provides utilities for extracting GPS coordinates from image EXIF data and performing comprehensive location analysis including reverse geocoding, weather data, nearby points of interest, and more.

**⚠️ IMPORTANT: This project has been refactored into a modular architecture in v2.0**

The project now includes:

### Current Implementation (v2.0) - **RECOMMENDED**
- `gps_toolkit/` - **Main modular implementation** with service-oriented architecture
  - Async processing capabilities for 2-3x performance improvements
  - Optimized face detection (<1s vs 3-5s previously)
  - Modular services for easy extension and maintenance
  - Comprehensive CLI with `gps-toolkit` command
  - Python API for programmatic usage

### Legacy Implementation
- `gps.sh` - Original shell script implementation (Zsh) - still available for reference

### Key Files
- `gps_toolkit/` - **Primary codebase** (modular v2.0 architecture)
- `setup.py` - Package installation and dependencies
- `requirements.txt` - Python package dependencies

## Dependencies

### GPS Toolkit v2.0 (Current - **RECOMMENDED**)

#### System Dependencies
```bash
# macOS
brew install tesseract zbar exiftool

# Ubuntu/Debian  
sudo apt-get install tesseract-ocr libzbar0 exiftool

# CentOS/RHEL
sudo yum install tesseract zbar exiftool
```

#### Python Dependencies
```bash
# Core installation
pip install .

# All features (recommended)
pip install .[all]

# Selective installation
pip install .[ocr]    # OCR support
pip install .[face]   # Face detection
pip install .[color]  # Advanced color analysis
pip install .[moon]   # Moon phase calculations
pip install .[web]    # Web content extraction
```

#### Core Dependencies (always required)
- Python 3.7+
- `exiftool` - EXIF metadata extraction
- `Pillow` - Image processing
- `numpy` - Numerical operations  
- `requests` - HTTP client for APIs

#### Optional Dependencies (install with extras)
- `pytesseract` + `langdetect` - OCR and language detection
- `face-recognition` OR `opencv-contrib-python` - Face detection
- `scikit-learn` + `webcolors` - Advanced color analysis
- `ephem` - Astronomical calculations (moon phases)
- `trafilatura` - Web content extraction

### Legacy Implementation (for reference only)

#### Shell Script (gps.sh)
- `exiftool`, `jq`, `curl`, `zsh`

## Running the Scripts

### GPS Toolkit v2.0 (Current - **RECOMMENDED**)

#### Installation
```bash
# Install the toolkit
pip install .[all]

# Or for development
pip install -e .[all]
```

#### Command Line Usage
```bash
# Basic GPS extraction (JSON output)
gps-toolkit photo.jpg

# Human-readable output with date
gps-toolkit --text --date photo.jpg

# All location features
gps-toolkit --all photo.jpg

# Enhanced features with async processing (RECOMMENDED)
gps-toolkit --async --all --ocr --faces --qr --colors photo.jpg

# Web content from detected URLs
gps-toolkit --ocr --qr --web-content photo.jpg

# Debug mode with performance timing
gps-toolkit --debug --all photo.jpg

# Different async strategies
gps-toolkit --async --strategy maximal --all photo.jpg
gps-toolkit --async --strategy conservative --all photo.jpg
```

#### Python API Usage
```python
from gps_toolkit import GPSLocationExtractor
import asyncio

# Synchronous usage
extractor = GPSLocationExtractor(debug=False)
result = extractor.process('photo.jpg', weather=True, ocr=True, faces=True)

# Async usage (RECOMMENDED for better performance)
async def process_image():
    extractor = GPSLocationExtractor(debug=True)
    result = await extractor.process_async(
        'photo.jpg',
        strategy='parallel',  # or 'maximal', 'conservative'
        weather=True,
        enhanced_weather=True,
        ocr=True,
        faces=True,
        qr=True,
        colors=True,
        web_content=True
    )
    return result

result = asyncio.run(process_image())
```

#### Performance Testing
```bash
# Run comprehensive benchmark
python benchmark_toolkit.py

# Test specific features  
python -m gps_toolkit.cli --debug --faces photo.jpg
python -m gps_toolkit.cli --debug --ocr photo.jpg
```

### Legacy Implementation (for reference only)

#### Shell Script (gps.sh)
```bash
chmod +x gps.sh
./gps.sh --all <image_file>
```

## Architecture

### GPS Toolkit v2.0 - Modular Service-Oriented Architecture (**CURRENT**)

The v2.0 architecture is completely refactored with a modular, service-oriented design:

#### Core Architecture
```
gps_toolkit/
├── main.py                     # Main orchestrator (GPSLocationExtractor)
├── cli.py                      # Command-line interface  
├── core/                       # Core utilities and models
│   ├── extractors.py           # EXIF data extraction
│   ├── validators.py           # Input validation
│   └── utils.py                # Utility functions
├── services/                   # Independent service modules
│   ├── location.py             # Geocoding and location data
│   ├── weather.py              # Weather and environmental data
│   ├── image_analysis.py       # Face, QR, color analysis
│   ├── text_extraction.py      # OCR and text processing
│   └── web_content.py          # Web content extraction
└── processors/                 # Processing coordination
    ├── async_coordinator.py    # Async task coordination
    ├── json_formatter.py       # Output formatting
    └── timing.py               # Performance timing
```

#### Key Architectural Benefits
- **Modular Design**: Each service is independent and self-contained
- **Async Processing**: 2-3x performance improvement through parallel execution
- **Fail-Safe Operation**: Individual service failures don't crash the entire process
- **Extensibility**: New services can be added without modifying existing code
- **Performance Monitoring**: Built-in timing and debug capabilities

#### Processing Flow
1. **EXIF Extraction** (core/extractors.py): GPS coordinates, datetime, camera info
2. **Parallel Service Execution**:
   - **Location Services** (services/location.py): Geocoding, elevation, POIs, venues
   - **Weather Services** (services/weather.py): Weather, air quality, moon phase
   - **Image Analysis** (services/image_analysis.py): Faces, QR codes, colors
   - **Text Processing** (services/text_extraction.py): OCR, language detection
3. **Web Content** (services/web_content.py): Extract content from found URLs
4. **Output Formatting** (processors/json_formatter.py): JSON or human-readable

#### Async Coordination
The `AsyncCoordinator` groups independent operations for parallel execution:
- **Group 1**: Core location data (geocoding, weather, elevation)
- **Group 2**: Image analysis (faces, OCR, QR codes, colors)  
- **Group 3**: Location enrichment (venues, POIs, holidays, events)

### Legacy Architecture (for reference)

#### Shell Script (gps.sh) - **LEGACY**
Simple sequential processing:
1. EXIF extraction → 2. Geocoding → 3. Weather → 4. Output

### Migration Benefits

Moving from legacy to v2.0 provides:
- **3-5x faster face detection** (optimized DNN models)
- **2-4x faster OCR processing** (improved preprocessing)
- **1.5-3x overall speedup** (async processing)
- **50% memory reduction** (lazy loading, efficient resource management)
- **Better maintainability** (modular services)
- **Enhanced extensibility** (easy to add new features)

## Documentation

### Comprehensive Documentation (v2.0)

For detailed information about the new GPS Toolkit architecture:

- **[gps_toolkit/README.md](gps_toolkit/README.md)** - Complete user guide with installation, usage examples, and API reference
- **[gps_toolkit/ARCHITECTURE.md](gps_toolkit/ARCHITECTURE.md)** - Detailed architectural overview, design principles, and extension points
- **[gps_toolkit/PERFORMANCE.md](gps_toolkit/PERFORMANCE.md)** - Performance improvements, optimization techniques, and benchmarking results

### Quick Reference

#### Basic Usage
```bash
# Install and run
pip install .[all]
gps-toolkit --async --all --ocr --faces --qr --colors photo.jpg
```

#### Key Features  
- **Async Processing**: Use `--async` for 1.5-3x performance improvement
- **Multiple Strategies**: `--strategy maximal|parallel|conservative`
- **Debug Mode**: `--debug` for performance timing information
- **Human Output**: `--text` for readable format instead of JSON

#### Performance Targets (v2.0)
- Face Detection: <1s (vs 3-5s in legacy)
- OCR Processing: <1s (vs 2-4s in legacy)  
- Overall Processing: 2-3x faster than legacy
- Memory Usage: 50% reduction

## API Usage

All implementations use these free APIs (no API keys required):

1. **OpenStreetMap Nominatim** - Reverse geocoding
2. **Open-Meteo** - Weather data and air quality  
3. **Open Elevation** - Elevation data
4. **Overpass API** - Points of interest and venues
5. **Nager.Date** - Holiday information
6. **Wikipedia** - Historical events

All requests include proper User-Agent headers and respect rate limits.

## JSON Output Structure

The GPS Toolkit v2.0 produces enhanced JSON output with comprehensive metadata:

```json
{
  "location": {
    "coordinates": {"lat": 62.09, "lon": 7.22},
    "address": {
      "street": "Geirangervegen", 
      "postal_code": "6216",
      "city": "Geiranger",
      "country": "Norge"
    }
  },
  "datetime": {
    "date": "July 15, 2023",
    "time": "14:30:00",
    "weekday": "Saturday",
    "season": "Summer"
  },
  "weather": {
    "temperature_celsius": 17.9,
    "apparent_temperature_celsius": 16.5,
    "description": "overcast",
    "wind_speed_kmh": 12,
    "wind_direction": "NW",
    "relative_humidity_percent": 75,
    "pressure_hpa": 1012,
    "visibility_km": 10.0,
    "air_quality": {"aqi": 34, "category": "Good"},
    "uv_index": 6,
    "uv_category": "High"
  },
  "faces_in_image": {"count": 2},
  "text_in_image": {
    "raw_text": "Welcome to Norway",
    "language": "en",
    "urls": ["https://example.com"]
  },
  "qr_codes": {
    "count": 1,
    "codes": [{"data": "https://example.com", "type": "QRCODE"}]
  },
  "dominant_colours": {
    "color_1": {"hex": "#80857d", "name": "gray"},
    "color_2": {"hex": "#6c6e4e", "name": "green"}
  },
  "web_content": [
    {
      "url": "https://example.com",
      "title": "Example Site",
      "content": "Page content..."
    }
  ]
}
```

### Debug Output

With `--debug` flag, includes comprehensive timing information:

```json
{
  "debug_info": {
    "total_processing_time": 2.45,
    "timing_breakdown": {
      "exif_extraction": 0.12,
      "reverse_geocoding": 0.45,
      "face_detection": 0.85,
      "ocr_extraction": 0.75
    },
    "async_strategy": "parallel",
    "service_availability": {
      "face_detection": true,
      "ocr": true,
      "web_content": true
    }
  },
  // ... regular output
}
```

## Error Handling

### v2.0 GPS Toolkit (Robust Error Handling)
- Individual service failures don't crash the entire process
- Missing optional dependencies are handled gracefully
- Services report availability status in debug output
- Comprehensive error reporting with debug mode

### Legacy Implementations
- Exit silently with code 1 if no GPS coordinates found
- Limited error reporting and recovery

## Platform Compatibility

- **GPS Toolkit v2.0**: Cross-platform (Windows, macOS, Linux)
- **Shell Script**: macOS-specific (uses `-j` flag with `date` command)
- **Python Scripts**: Cross-platform with appropriate dependencies

## Performance and Testing

Use the included benchmark tool to validate performance:

```bash
# Run comprehensive benchmark
python benchmark_toolkit.py

# Test individual features
python -m gps_toolkit.cli --debug --faces photo.jpg
python -m gps_toolkit.cli --debug --ocr photo.jpg
```

For development and testing:
```bash
# Install in development mode
pip install -e .[all]

# Run tests
python -m pytest  # If test suite is available
```