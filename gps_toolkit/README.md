# GPS Toolkit v2.0

A high-performance, modular GPS location extractor with advanced image analysis capabilities.

## Overview

The GPS Toolkit is a comprehensive solution for extracting GPS coordinates from image EXIF data and enriching that data with advanced features including reverse geocoding, weather information, image analysis, text extraction, and web content analysis. Version 2.0 introduces a completely refactored modular architecture with async processing capabilities for dramatically improved performance.

### Key Features

- **EXIF GPS Extraction**: Extract GPS coordinates, datetime, camera info, and exposure settings
- **Reverse Geocoding**: Convert coordinates to human-readable addresses using OpenStreetMap
- **Weather Data**: Historical weather, air quality, UV index, and moon phase calculations
- **Image Analysis**: Face detection, QR code scanning, dominant color extraction
- **Text Extraction**: OCR text extraction with language detection
- **Web Content**: Extract and analyze content from URLs found in images
- **Async Processing**: Concurrent execution for up to 2-3x performance improvement
- **Modular Architecture**: Independent services for easy extension and maintenance

### Performance Improvements

Version 2.0 delivers significant performance improvements over previous versions:

- **Face Detection**: Optimized to complete in <1s (previously 3-5s)
- **OCR Processing**: Streamlined to <1s for typical images
- **Async Processing**: 1.5-3x speedup through parallel execution
- **Memory Efficiency**: Reduced memory footprint through lazy loading
- **Error Resilience**: Individual service failures don't crash the entire process

## Installation

### Prerequisites

1. **System Dependencies**:
```bash
# macOS
brew install tesseract zbar exiftool

# Ubuntu/Debian
sudo apt-get install tesseract-ocr libzbar0 exiftool

# CentOS/RHEL
sudo yum install tesseract zbar exiftool
```

2. **Python 3.7+** is required

### Installation Options

#### Option 1: Basic Installation
```bash
pip install .
```

#### Option 2: With All Features
```bash
pip install .[all]
```

#### Option 3: Selective Features
```bash
# OCR support
pip install .[ocr]

# Face detection
pip install .[face]

# Advanced color analysis
pip install .[color]

# Moon phase calculations
pip install .[moon]

# Web content extraction
pip install .[web]
```

#### Option 4: Development Installation
```bash
pip install -e .[all]
```

## Quick Start

### Command Line Usage

```bash
# Basic GPS extraction
gps-toolkit photo.jpg

# Human-readable output
gps-toolkit --text --date photo.jpg

# All features with async processing
gps-toolkit --async --all --ocr --faces --qr --colors photo.jpg

# Enhanced weather and web content
gps-toolkit --enhanced-weather --web-content --ocr photo.jpg

# Debug mode with timing information
gps-toolkit --debug --all photo.jpg
```

### Python API Usage

#### Basic Synchronous Usage
```python
from gps_toolkit import GPSLocationExtractor

# Initialize extractor
extractor = GPSLocationExtractor(debug=False)

# Process image with all features
result = extractor.process('photo.jpg', 
                          weather=True,
                          ocr=True,
                          faces=True,
                          qr=True,
                          colors=True)

print(result['location']['address']['city'])
```

#### Async Processing for Better Performance
```python
import asyncio
from gps_toolkit import GPSLocationExtractor

async def process_image():
    extractor = GPSLocationExtractor(debug=True)
    
    # Async processing with parallel strategy
    result = await extractor.process_async(
        'photo.jpg',
        strategy='parallel',  # or 'maximal', 'conservative', 'sequential'
        weather=True,
        enhanced_weather=True,
        ocr=True,
        faces=True,
        qr=True,
        colors=True,
        web_content=True
    )
    
    return result

# Run async processing
result = asyncio.run(process_image())
```

#### Human-Readable Output
```python
# Format as human-readable text
extractor = GPSLocationExtractor()
data = extractor.process('photo.jpg', weather=True)
text = extractor.format_human_readable(data, {'date': True})
print(text)
# Output: "This photo was taken on Sunday, October 15, 2023 at 2:30 PM at this address: Main Street in 12345 Berlin (Germany)."
```

## Architecture Overview

The GPS Toolkit follows a service-oriented architecture with clear separation of concerns:

### Core Components

- **`main.py`**: Main `GPSLocationExtractor` class that orchestrates all services
- **`cli.py`**: Command-line interface with comprehensive argument parsing
- **`core/`**: Core utilities (validators, extractors, models, utilities)
- **`services/`**: Independent service modules for specific functionality
- **`processors/`**: Processing utilities (async coordination, JSON formatting, timing)
- **`config/`**: Configuration management

### Service Modules

1. **Location Service** (`services/location.py`)
   - Reverse geocoding
   - Elevation data
   - Points of interest
   - Venue information
   - Holiday and historical event data

2. **Weather Service** (`services/weather.py`)
   - Historical weather data
   - Air quality information
   - UV index
   - Moon phase calculations

3. **Image Analysis Service** (`services/image_analysis.py`)
   - Face detection with optimized models
   - QR code and barcode scanning
   - Dominant color extraction

4. **Text Extraction Service** (`services/text_extraction.py`)
   - OCR text extraction
   - Language detection
   - URL extraction from text

5. **Web Content Service** (`services/web_content.py`)
   - Web page content extraction
   - URL validation and normalization
   - Content summarization

### Async Processing

The async coordinator enables concurrent execution of independent operations:

```python
from gps_toolkit.processors.async_coordinator import AsyncCoordinator

# Create task groups
coordinator = AsyncCoordinator(debug=True)

# Group 1: Location data
group1 = coordinator.create_group("Location Data")
group1.add_task("geocoding", location_service.reverse_geocode, lat, lon)
group1.add_task("weather", weather_service.get_weather, lat, lon)

# Group 2: Image analysis
group2 = coordinator.create_group("Image Analysis")
group2.add_task("faces", image_service.detect_faces, image_path)
group2.add_task("qr", image_service.detect_qr_codes, image_path)

# Execute groups concurrently
results = await coordinator.execute_groups_concurrently()
```

## Configuration

### Environment Variables

```bash
# Set user agent for API requests
export GPS_TOOLKIT_USER_AGENT="MyApp/1.0"

# Set maximum colors to extract
export GPS_TOOLKIT_MAX_COLORS=5

# Enable/disable specific features
export GPS_TOOLKIT_ENABLE_FACE_DETECTION=true
export GPS_TOOLKIT_ENABLE_OCR=true
```

### Configuration File

The toolkit uses a configuration system in `config/settings.py`:

```python
from gps_toolkit.config import settings

# Access configuration
print(settings.USER_AGENT)
print(settings.MAX_DOMINANT_COLORS)
```

## Output Formats

### JSON Output (Default)

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
    "timestamp": "2023-07-15T14:30:00",
    "local_time": "2:30 PM",
    "weekday": "Saturday"
  },
  "weather": {
    "temperature_c": 17.9,
    "description": "overcast",
    "air_quality": {"aqi": 34, "category": "Good"}
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
  }
}
```

### Debug Output

With `--debug` flag, includes timing information:

```json
{
  "debug_info": {
    "total_processing_time": 2.45,
    "timing_breakdown": {
      "exif_extraction": 0.12,
      "reverse_geocoding": 0.45,
      "face_detection": 0.85,
      "ocr_extraction": 0.75
    }
  },
  // ... regular output
}
```

### Human-Readable Text

With `--text` flag:

```
This photo was taken on Saturday, July 15, 2023 at 2:30 PM at this address: Geirangervegen in 6216 Geiranger (Norge).
```

## Advanced Usage

### Processing Strategies

The async processing supports different strategies:

- **`parallel`** (default): Balanced grouping for optimal performance
- **`maximal`**: Maximum parallelism (one operation per group)
- **`conservative`**: Conservative grouping for limited resources
- **`sequential`**: Sequential execution (no parallelism)

```bash
# Maximal parallelism
gps-toolkit --async --strategy maximal --all photo.jpg

# Conservative for resource-constrained environments
gps-toolkit --async --strategy conservative --all photo.jpg
```

### Custom Service Usage

You can use individual services independently:

```python
from gps_toolkit.services.image_analysis import ImageAnalysisService
from gps_toolkit.services.location import LocationService

# Use services independently
image_service = ImageAnalysisService()
faces = image_service.detect_faces('photo.jpg')

location_service = LocationService("MyApp/1.0")
address = location_service.reverse_geocode(lat, lon)
```

### Error Handling

The toolkit is designed to be resilient:

```python
result = extractor.process('photo.jpg', faces=True, ocr=True)

# Check if individual features succeeded
if 'faces_in_image' in result:
    print(f"Found {result['faces_in_image']['count']} faces")
else:
    print("Face detection failed or unavailable")

if 'error' in result:
    print(f"Processing failed: {result['error']}")
```

## Performance Tips

1. **Use async processing** for multiple features: `--async`
2. **Choose appropriate strategy**: `maximal` for powerful machines, `conservative` for limited resources
3. **Enable only needed features**: Don't use `--all` if you only need specific features
4. **Use debug mode** to identify bottlenecks: `--debug`
5. **Install optional dependencies** for better performance:
   ```bash
   pip install .[all]  # Installs optimized libraries
   ```

## Troubleshooting

### Common Issues

1. **Missing system dependencies**:
   ```bash
   # Install required system packages
   brew install tesseract zbar exiftool  # macOS
   ```

2. **Face detection is slow**:
   - Install optimized OpenCV: `pip install opencv-contrib-python`
   - Use async processing: `--async`
   - Consider using `--strategy conservative`

3. **OCR fails**:
   - Ensure Tesseract is installed: `tesseract --version`
   - Check image quality and contrast

4. **No GPS coordinates found**:
   - Verify image has GPS data: `exiftool -GPS* image.jpg`
   - Some images may have GPS disabled

### Debug Mode

Use debug mode to diagnose issues:

```bash
gps-toolkit --debug --all photo.jpg 2> debug.log
```

The debug output includes:
- Timing information for each operation
- Error messages from individual services
- Processing strategy information
- Service availability status

## API Reference

See individual module documentation:

- [GPSLocationExtractor](main.py) - Main processing class
- [AsyncCoordinator](processors/async_coordinator.py) - Async processing coordination
- [Services](services/) - Individual service modules
- [CLI](cli.py) - Command-line interface

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Run the test suite: `python -m pytest`
5. Submit a pull request

## Changelog

### v2.0.0
- Complete architectural refactoring to modular service-oriented design
- Async processing with up to 3x performance improvements
- Optimized face detection (sub-1s performance)
- Enhanced error handling and resilience
- Improved CLI with comprehensive options
- Added web content extraction capabilities
- Better memory efficiency and resource management