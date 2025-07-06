# GPS Toolkit - Enhanced Location Extractor

A high-performance, modular GPS location extractor with advanced image analysis capabilities. Extract GPS coordinates, detailed weather data, addresses, nearby places, and much more from your photos.

## 🚀 Quick Start

```bash
# Install the toolkit
pip install .[all]

# Extract GPS data with all features (recommended)
gps-toolkit --async --all --ocr --faces --qr --colors photo.jpg

# Human-readable output with weather
gps-toolkit --text --date --weather --enhanced-weather photo.jpg

# Get detailed JSON output
gps-toolkit --weather --enhanced-weather photo.jpg
```

## ✨ What's New in v2.0

Version 2.0 introduces a **complete architectural refactoring** with dramatic performance improvements:

| Feature | v1.x | v2.0 | Improvement |
|---------|------|------|-------------|
| **Face Detection** | 3-5s | <1s | **3-5x faster** |
| **OCR Processing** | 2-4s | <1s | **2-4x faster** |
| **Overall Speed** | 8-15s | 3-6s | **2-3x faster** |
| **Memory Usage** | 200-400MB | 100-200MB | **50% reduction** |
| **Architecture** | Monolithic | Modular Services | **Maintainable** |

## 📋 Features

### Core GPS Extraction
- **EXIF GPS Coordinates**: Extract latitude/longitude from image metadata
- **Reverse Geocoding**: Convert coordinates to human-readable addresses
- **Date/Time Analysis**: Photo timestamp with timezone and day-of-week
- **Camera Information**: Camera model, settings, and exposure data

### Location Intelligence
- **Enhanced Weather Data**: Comprehensive historical weather including:
  - Temperature (actual and feels-like)
  - Wind speed, direction, and gusts
  - Humidity and dew point
  - Atmospheric pressure
  - Precipitation (rain/snow)
  - Visibility
  - UV index with category
  - Weather description
- **Air Quality**: AQI, PM2.5, PM10, ozone levels with health categories
- **Moon Phase**: Phase name and illumination percentage
- **Elevation**: Altitude above sea level
- **Points of Interest**: Nearby landmarks, attractions
- **Venues**: Restaurants, bars, cafes within walking distance
- **Businesses**: Nearby businesses by category
- **Holiday Information**: Local holidays for photo date
- **Historical Events**: Significant events on photo date

### Advanced Image Analysis
- **Face Detection**: Optimized sub-1s face counting (was 3-5s)
- **OCR Text Extraction**: Extract and process visible text
- **QR Code Scanning**: Decode QR codes and barcodes
- **Color Analysis**: Extract dominant colors with names
- **Language Detection**: Identify text languages
- **Web Content**: Extract content from URLs found in images

### Performance Features  
- **Async Processing**: 1.5-3x speedup through parallel execution
- **Multiple Strategies**: Optimize for different hardware configurations
- **Debug Mode**: Comprehensive timing and performance analysis
- **Memory Efficiency**: Lazy loading and optimized resource management

## 🛠 Installation

### System Dependencies

```bash
# macOS
brew install tesseract zbar exiftool

# Ubuntu/Debian
sudo apt-get install tesseract-ocr libzbar0 exiftool

# CentOS/RHEL  
sudo yum install tesseract zbar exiftool
```

### Python Installation

```bash
# All features (recommended)
pip install .[all]

# Selective installation
pip install .[ocr]    # OCR support
pip install .[face]   # Face detection  
pip install .[color]  # Advanced color analysis
pip install .[moon]   # Moon phase calculations
pip install .[web]    # Web content extraction

# Development installation
pip install -e .[all]
```

## 🖥 Usage Examples

### Command Line

```bash
# Basic GPS extraction
gps-toolkit photo.jpg

# Get detailed weather information
gps-toolkit --weather --enhanced-weather photo.jpg

# All features with async processing (recommended)
gps-toolkit --async --all --ocr --faces --qr --colors photo.jpg

# Human-readable output with weather
gps-toolkit --text --date --weather --enhanced-weather photo.jpg

# Weather-focused analysis
gps-toolkit --weather --enhanced-weather --elevation photo.jpg

# Location intelligence (venues, businesses, POIs)
gps-toolkit --venues --businesses --pois --distance 1000 photo.jpg

# Performance tuning
gps-toolkit --async --strategy maximal --debug --all photo.jpg

# Web content from detected URLs
gps-toolkit --ocr --qr --web-content photo.jpg
```

### Python API

```python
from gps_toolkit import GPSLocationExtractor
import asyncio

# Synchronous usage
extractor = GPSLocationExtractor()
result = extractor.process('photo.jpg', weather=True, faces=True)
print(result['location']['address']['city'])

# Async usage (recommended for better performance)
async def analyze_photo():
    extractor = GPSLocationExtractor(debug=True)
    result = await extractor.process_async(
        'photo.jpg',
        strategy='parallel',
        weather=True,
        enhanced_weather=True,
        ocr=True,
        faces=True,
        qr=True,
        colors=True,
        web_content=True
    )
    return result

result = asyncio.run(analyze_photo())
```

## 📊 Sample Output

### JSON Output (Default)
```json
{
  "location": {
    "address": {
      "street": "Geirangervegen",
      "city": "Geiranger", 
      "country": "Norge"
    }
  },
  "datetime": {
    "date": "July 15, 2023",
    "time": "2:30 PM",
    "weekday": "Saturday",
    "season": "Summer"
  },
  "weather": {
    "description": "overcast",
    "temperature_celsius": 17.9,
    "apparent_temperature_celsius": 16.2,
    "wind_speed_kmh": 12,
    "wind_direction": "NW",
    "wind_gusts_kmh": 18,
    "relative_humidity_percent": 78,
    "dewpoint_celsius": 14.1,
    "pressure_hpa": 1012,
    "rain_mm": 0.2,
    "visibility_km": 8.5,
    "uv_index": 3,
    "uv_category": "Moderate",
    "air_quality": {
      "aqi": 34,
      "category": "Good"
    }
  },
  "moon_phase": {
    "phase": "Waxing Crescent",
    "illumination": 28.5
  },
  "faces_in_image": {"count": 2},
  "text_in_image": {
    "raw_text": "Welcome to Norway",
    "language": "en"
  },
  "dominant_colours": {
    "color_1": {"hex": "#80857d", "name": "gray"}
  }
}
```

### Human-Readable Output
```
This photo was taken on Saturday, July 15, 2023 at 2:30 PM 
at this address: Geirangervegen in 6216 Geiranger (Norge).

Weather: 17.9°C (feels like 16.2°C), overcast
Wind: 12 km/h from NW, gusts up to 18 km/h
Humidity: 78%, Visibility: 8.5 km
Air quality: Good (AQI: 34)

Moon phase: Waxing Crescent (28.5% illuminated)

Faces detected: 2
Text found: Welcome to Norway
```

## ⚡ Performance Optimization

### Async Processing Strategies

Choose the optimal strategy for your hardware:

```bash
# Maximal parallelism (powerful hardware)
gps-toolkit --async --strategy maximal --all photo.jpg

# Balanced performance (default)
gps-toolkit --async --strategy parallel --all photo.jpg  

# Conservative (limited resources)
gps-toolkit --async --strategy conservative --all photo.jpg

# No parallelism (debugging)
gps-toolkit --strategy sequential --all photo.jpg
```

### Performance Monitoring

```bash
# Enable debug timing
gps-toolkit --debug --all photo.jpg 2> timing.log

# Run comprehensive benchmark
python benchmark_toolkit.py
```

## 🏗 Architecture

### Modular Service Design

```
gps_toolkit/
├── main.py                     # Main orchestrator
├── cli.py                      # Command-line interface
├── core/                       # Core utilities
│   ├── extractors.py           # EXIF extraction
│   ├── validators.py           # Input validation
│   └── utils.py                # Utility functions
├── services/                   # Independent services
│   ├── location.py             # Geocoding & location
│   ├── weather.py              # Weather & environment
│   ├── image_analysis.py       # Face, QR, color analysis
│   ├── text_extraction.py      # OCR & text processing
│   └── web_content.py          # Web content extraction
└── processors/                 # Processing coordination
    ├── async_coordinator.py    # Async orchestration
    ├── json_formatter.py       # Output formatting
    └── timing.py               # Performance monitoring
```

### Key Architectural Benefits

- **Modular**: Each service is independent and self-contained
- **Extensible**: Add new features without modifying existing code
- **Resilient**: Service failures don't crash the entire process
- **Performance-Aware**: Built-in timing and optimization
- **Async-Ready**: Concurrent execution of independent operations

## 📚 Documentation

### Comprehensive Guides

- **[gps_toolkit/README.md](gps_toolkit/README.md)** - Complete user guide and API reference
- **[gps_toolkit/ARCHITECTURE.md](gps_toolkit/ARCHITECTURE.md)** - Detailed architecture and design patterns
- **[gps_toolkit/PERFORMANCE.md](gps_toolkit/PERFORMANCE.md)** - Performance optimization and benchmarking
- **[CLAUDE.md](CLAUDE.md)** - Development guidance and project overview

### Quick References

- **Installation**: See [Installation](#-installation) section above
- **Usage Examples**: See [Usage Examples](#-usage-examples) section above
- **Performance Tips**: See [Performance Optimization](#-performance-optimization) section above

## 🔧 Development

### Running Tests

```bash
# Install in development mode
pip install -e .[all]

# Run performance benchmark
python benchmark_toolkit.py

# Test specific features
python -m gps_toolkit.cli --debug --faces photo.jpg
python -m gps_toolkit.cli --debug --ocr photo.jpg
```

### Adding New Services

The modular architecture makes it easy to add new functionality:

1. Create a new service in `services/`
2. Add to main orchestrator in `main.py`
3. Update CLI options in `cli.py`
4. Add async coordination if needed

See [ARCHITECTURE.md](gps_toolkit/ARCHITECTURE.md) for detailed extension guidelines.

## 🐛 Troubleshooting

### Common Issues

1. **Face detection is slow**:
   ```bash
   pip install opencv-contrib-python  # Install optimized OpenCV
   gps-toolkit --async --strategy conservative --faces photo.jpg
   ```

2. **OCR fails**:
   ```bash
   tesseract --version  # Verify Tesseract installation
   brew reinstall tesseract  # macOS
   ```

3. **Memory issues**:
   ```bash
   gps-toolkit --async --strategy conservative photo.jpg
   ```

4. **Debug performance issues**:
   ```bash
   gps-toolkit --debug --all photo.jpg 2> debug.log
   grep "took" debug.log | sort -k3 -nr
   ```

## 📝 License

MIT License - see LICENSE file for details.

## 🙏 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`  
3. Make changes and add tests
4. Run the benchmark: `python benchmark_toolkit.py`
5. Submit a pull request

## 📈 Changelog

### v2.0.0 (Current)
- ✅ Complete architectural refactoring to modular service design
- ✅ Async processing with 1.5-3x performance improvements
- ✅ Optimized face detection (3-5x faster, now <1s)
- ✅ Enhanced OCR processing (2-4x faster, now <1s)  
- ✅ 50% memory usage reduction
- ✅ Web content extraction from detected URLs
- ✅ Comprehensive CLI with multiple processing strategies
- ✅ Robust error handling and service isolation
- ✅ Built-in performance monitoring and debugging

### v1.x (Legacy)
- Basic GPS extraction with monolithic architecture
- Face detection, OCR, weather data
- Sequential processing only

---

**🚀 Ready to get started?** Install with `pip install .[all]` and run `gps-toolkit --async --all photo.jpg`!