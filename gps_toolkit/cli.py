"""Command-line interface for GPS Toolkit"""

import sys
import json
import argparse
import asyncio
import logging
from pathlib import Path

from .main import GPSLocationExtractor
from .core.utils import parse_distance


def main():
    """Main entry point for the GPS Toolkit CLI"""
    parser = argparse.ArgumentParser(
        description='Enhanced GPS Location Extractor v2 - Extract location and metadata from images',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (JSON output)
  gps-toolkit photo.jpg
  
  # Human-readable output with date
  gps-toolkit --text --date photo.jpg
  
  # ALL features (location, enhanced, and image analysis)
  gps-toolkit --all photo.jpg
  
  # Enhanced features
  gps-toolkit --ocr --faces --qr --colors photo.jpg
  
  # Nearby businesses within 100 meters
  gps-toolkit --businesses --distance 100m photo.jpg
  
  # Web content extraction from detected URLs
  gps-toolkit --ocr --qr --web-content photo.jpg
  
  # Debug mode with timing information
  gps-toolkit --debug --all photo.jpg
  
  # Async processing for better performance
  gps-toolkit --async --all photo.jpg
  gps-toolkit --async --strategy maximal --distance 0.5km --businesses photo.jpg
"""
    )
    
    parser.add_argument('image', help='Path to the image file')
    
    # Output format
    parser.add_argument('--text', action='store_true',
                        help='Output in human-readable text format instead of JSON')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode with timing information and full output')
    
    # Processing options
    parser.add_argument('--async', action='store_true', dest='use_async',
                        help='Use async processing for better performance (experimental)')
    parser.add_argument('--strategy', choices=['parallel', 'maximal', 'conservative', 'sequential'],
                        default='parallel',
                        help='Processing strategy for async mode (default: parallel)')
    
    # Basic features
    parser.add_argument('--date', action='store_true',
                        help='Include date and time information')
    parser.add_argument('--weather', action='store_true',
                        help='Include weather data')
    parser.add_argument('--elevation', action='store_true',
                        help='Include elevation data')
    parser.add_argument('--pois', action='store_true',
                        help='Include nearby points of interest')
    parser.add_argument('--venues', action='store_true',
                        help='Include nearby venues (restaurants, bars, cafes)')
    parser.add_argument('--holidays', action='store_true',
                        help='Include holiday information')
    parser.add_argument('--events', action='store_true',
                        help='Include historical events')
    
    # Enhanced features
    parser.add_argument('--ocr', action='store_true',
                        help='Extract text from image using OCR')
    parser.add_argument('--faces', action='store_true',
                        help='Detect faces in the image')
    parser.add_argument('--qr', action='store_true',
                        help='Detect and decode QR codes')
    parser.add_argument('--colors', action='store_true',
                        help='Extract dominant colors')
    parser.add_argument('--enhanced-weather', action='store_true',
                        help='Include enhanced weather data (air quality, UV index, moon phase)')
    parser.add_argument('--web-content', action='store_true',
                        help='Extract content from URLs found in image (requires --ocr or --qr)')
    parser.add_argument('--businesses', action='store_true',
                        help='Include nearby businesses (shops, services, offices)')
    
    # Distance parameter
    parser.add_argument('--distance', default='50',
                        help='Search radius for nearby places (default: 50m). Accepts values like "50", "50m", "0.5km"')
    
    # Convenience options
    parser.add_argument('--all', action='store_true',
                        help='Enable ALL features (location, enhanced, and image analysis)')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format='[%(levelname)s] %(name)s: %(message)s',
        stream=sys.stderr
    )
    
    # Parse distance parameter
    try:
        distance_meters = parse_distance(args.distance)
    except ValueError as e:
        logging.warning(f"{e}, using default 50m")
        distance_meters = 50
    
    # Define all available features
    BASIC_LOCATION_FEATURES = ['date', 'weather', 'elevation', 'pois', 'venues', 'holidays', 'events', 'businesses']
    ENHANCED_FEATURES = ['ocr', 'faces', 'qr', 'colors', 'enhanced_weather', 'web_content']
    ALL_FEATURES = BASIC_LOCATION_FEATURES + ENHANCED_FEATURES
    
    # Handle --all flag
    if args.all:
        for feature in ALL_FEATURES:
            setattr(args, feature, True)
    
    # Enhanced weather implies basic weather
    if args.enhanced_weather:
        args.weather = True
    
    # Web content requires URL extraction
    if args.web_content and not (args.ocr or args.qr):
        logging.warning("--web-content requires --ocr or --qr to extract URLs")
    
    # Create extractor instance
    extractor = GPSLocationExtractor(debug=args.debug)
    
    # Process the image
    # Build options dictionary from args
    options = {feature: getattr(args, feature) for feature in ALL_FEATURES}
    options['distance'] = distance_meters
    
    try:
        # Choose processing method
        if args.use_async:
            # Use async processing
            result = asyncio.run(extractor.process_async(args.image, strategy=args.strategy, **options))
        else:
            # Use traditional sync processing
            result = extractor.process(args.image, **options)
        
        if 'error' in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        
        # Output results
        if args.text:
            # Human-readable format
            text_output = extractor.format_human_readable(result, options)
            print(text_output)
        else:
            # JSON format
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()