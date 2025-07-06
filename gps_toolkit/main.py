"""
Main GPS Location Extractor module that brings together all functionality.

This module serves as the central orchestrator for the GPS toolkit, coordinating
all services and processing image files to extract location data, metadata,
and various types of enriched information. It implements a modular architecture
where each service handles a specific aspect of data extraction and analysis.

The module provides:
- EXIF metadata extraction (GPS coordinates, datetime, camera info)
- Reverse geocoding (converting coordinates to addresses)
- Weather data retrieval (historical weather for the photo date/time)
- Image analysis (face detection, QR codes, dominant colors)
- Text extraction via OCR
- Web content extraction from URLs found in images
- Flexible output formatting (JSON with optional debug info)
- Async processing for concurrent execution of independent operations

Design Philosophy:
- Modular: Each service is independent and can be used separately
- Fail-safe: Individual service failures don't crash the entire process
- Extensible: New services can be added without modifying core logic
- Performance-aware: Optional timing context for performance monitoring
- Concurrent: Independent operations run in parallel for better performance
"""

import sys
import json
import warnings
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from .config import settings
from .core.validators import (
    validate_image_file, validate_coordinates, deduplicate_urls,
    deduplicate_urls_async, validate_urls_with_tld_async
)
from .core.extractors import ExifExtractor
from .core.utils import (
    remove_empty_values, extract_urls_from_text,
    extract_urls_from_text_async
)
from .processors.timing import TimingContext
from .processors.async_coordinator import AsyncCoordinator, AsyncProcessingStrategy, AsyncTimingContext
from .processors.json_formatter import build_debug_json, build_default_json
from .services.location import LocationService
from .services.weather import WeatherService
from .services.image_analysis import ImageAnalysisService
from .services.text_extraction import TextExtractionService
from .services.web_content import WebContentService

# Suppress warnings from third-party libraries to keep output clean
warnings.filterwarnings('ignore')


class GPSLocationExtractor:
    """
    Enhanced GPS Location Extractor with advanced features.
    
    This is the main class that orchestrates all data extraction from images.
    It coordinates multiple services to provide comprehensive information about
    photos including location, weather, text content, faces, and more.
    
    The class follows a service-oriented architecture where each type of
    functionality is delegated to a specialized service class. This makes
    the code more maintainable and allows services to be reused independently.
    
    Attributes:
        debug (bool): Whether to include timing and debug information in output
        user_agent (str): User agent string for API requests
        location_service: Service for geocoding and location-related APIs
        weather_service: Service for weather and environmental data
        image_analysis_service: Service for face detection, QR codes, colors
        text_extraction_service: Service for OCR text extraction
        web_content_service: Service for fetching content from URLs
    """
    
    def __init__(self, debug: bool = False):
        """
        Initialize the GPS Location Extractor.
        
        Args:
            debug (bool): Enable debug mode for detailed timing information
                         and additional diagnostic output. Default is False.
        
        Notes:
            Services are initialized lazily to avoid unnecessary resource
            allocation if certain features aren't used. Each service manages
            its own dependencies and gracefully handles missing libraries.
        """
        self.debug = debug
        self.user_agent = settings.USER_AGENT
        
        # Create shared thread pool for all services
        from concurrent.futures import ThreadPoolExecutor
        self._shared_thread_pool = ThreadPoolExecutor(
            max_workers=settings.MAX_CONCURRENT_WEB_EXTRACTIONS
        )
        
        # Initialize services - each service is self-contained and handles
        # its own optional dependencies gracefully
        self.location_service = LocationService(self.user_agent, thread_pool=self._shared_thread_pool)
        self.weather_service = WeatherService(thread_pool=self._shared_thread_pool)
        self.image_analysis_service = ImageAnalysisService(thread_pool=self._shared_thread_pool)
        self.text_extraction_service = TextExtractionService()
        
        # Initialize web content service with enhanced configuration
        self.web_content_service = WebContentService(
            max_concurrent=settings.MAX_CONCURRENT_WEB_EXTRACTIONS,
            ping_timeout=settings.WEB_CONTENT_PING_TIMEOUT,
            extraction_timeout=settings.WEB_CONTENT_EXTRACTION_TIMEOUT,
            max_content_length=settings.WEB_CONTENT_MAX_LENGTH,
            rate_limit_delay=settings.WEB_CONTENT_RATE_LIMIT_DELAY,
            enable_connectivity_check=settings.ENABLE_URL_CONNECTIVITY_CHECK,
            thread_pool=self._shared_thread_pool
        )
        
        # Initialize async coordinator with shared thread pool
        self.async_coordinator = AsyncCoordinator(debug=debug, thread_pool=self._shared_thread_pool)
    
    def extract_all_urls(self, ocr_data: Optional[Dict[str, Any]], 
                        qr_data: Optional[Dict[str, Any]]) -> List[str]:
        """
        Extract and deduplicate all URLs from OCR text and QR codes.
        
        This method combines URLs from multiple sources (OCR-extracted text and
        QR code data) and applies sophisticated deduplication to ensure we don't
        process the same URL multiple times. The deduplication handles variations
        like http vs https, www prefixes, and parameter ordering.
        
        Args:
            ocr_data: OCR extraction results dictionary containing:
                     - 'available': bool indicating if OCR was performed
                     - 'urls': List of URLs found in the text
            qr_data: QR code detection results dictionary containing:
                    - 'available': bool indicating if QR detection was performed
                    - 'codes': List of detected QR codes with 'data' field
            
        Returns:
            List[str]: Deduplicated list of unique URLs found in the image
        
        Example:
            >>> urls = extractor.extract_all_urls(
            ...     {'available': True, 'urls': ['http://example.com']},
            ...     {'available': True, 'codes': [{'data': 'https://example.com'}]}
            ... )
            >>> print(urls)  # ['https://example.com'] - deduped and https preferred
        """
        all_urls = []
        
        # Extract URLs from OCR text
        if ocr_data and ocr_data.get('available') and ocr_data.get('urls'):
            all_urls.extend(ocr_data['urls'])
        
        # Extract URLs from QR codes
        if qr_data and qr_data.get('available') and qr_data.get('codes'):
            for code in qr_data['codes']:
                data = code.get('data', '')
                # Check if QR code data is a URL directly
                if data and any(data.startswith(prefix) for prefix in ['http://', 'https://', 'www.']):
                    all_urls.append(data)
                # Also extract URLs from QR code text (QR might contain text with URLs)
                urls = extract_urls_from_text(data, validate_tld=True, timeout=settings.URL_VALIDATION_TIMEOUT)
                all_urls.extend(urls)
        
        # Deduplicate URLs using advanced normalization with TLD validation
        return deduplicate_urls(all_urls, validate_tld=True, timeout=settings.URL_VALIDATION_TIMEOUT)
    
    async def extract_all_urls_async(self, ocr_data: Optional[Dict[str, Any]], 
                                   qr_data: Optional[Dict[str, Any]]) -> List[str]:
        """
        Asynchronously extract and deduplicate all URLs from OCR text and QR codes.
        
        This async version provides better performance through concurrent TLD validation
        and enhanced URL extraction with false positive filtering (e.g., "zij.n", "C.O.D").
        
        Args:
            ocr_data: OCR extraction results dictionary
            qr_data: QR code detection results dictionary
            
        Returns:
            List[str]: Deduplicated list of validated URLs
        """
        all_urls = []
        
        # Extract URLs from OCR text
        if ocr_data and ocr_data.get('available') and ocr_data.get('urls'):
            all_urls.extend(ocr_data['urls'])
        
        # Extract URLs from QR codes with enhanced validation
        if qr_data and qr_data.get('available') and qr_data.get('codes'):
            for code in qr_data['codes']:
                data = code.get('data', '')
                # Check if QR code data is a URL directly
                if data and any(data.startswith(prefix) for prefix in ['http://', 'https://', 'www.']):
                    all_urls.append(data)
                # Extract URLs using async enhanced validation
                urls = await extract_urls_from_text_async(
                    data, 
                    validate_tld=True, 
                    timeout=settings.URL_VALIDATION_TIMEOUT,
                    max_concurrent=settings.MAX_CONCURRENT_URL_VALIDATIONS
                )
                all_urls.extend(urls)
        
        # Deduplicate URLs using async advanced normalization with TLD validation
        return await deduplicate_urls_async(
            all_urls, 
            validate_tld=True, 
            timeout=settings.URL_VALIDATION_TIMEOUT,
            max_concurrent=settings.MAX_CONCURRENT_URL_VALIDATIONS
        )
    
    def process(self, image_path: str, **options) -> Dict[str, Any]:
        """
        Process an image and extract all requested information.
        
        This is the main entry point for processing images. It orchestrates
        all available services based on the options provided. The method is
        designed to be resilient - if one service fails, others continue.
        
        Processing Flow:
        1. Validate input image file
        2. Extract EXIF metadata (GPS coordinates, datetime, camera info)
        3. Perform reverse geocoding to get address
        4. Based on options, extract additional information:
           - Weather data for the photo's date/time
           - Elevation data
           - Nearby points of interest
           - Holiday information
           - OCR text extraction
           - Face detection
           - QR code detection
           - Dominant color analysis
           - Web content from found URLs
        
        Args:
            image_path (str): Path to the image file to process
            **options: Processing options as keyword arguments:
                - date (bool): Include datetime in human-readable output
                - weather (bool): Fetch basic weather data
                - enhanced_weather (bool): Include moon phase and air quality
                - elevation (bool): Get elevation data
                - pois (bool): Find nearby points of interest
                - venues (bool): Find nearby restaurants/bars
                - businesses (bool): Find nearby businesses
                - distance (int): Search radius in meters for POIs/venues/businesses (default: 500)
                - holidays (bool): Check for holidays on photo date
                - events (bool): Get historical events for photo date
                - ocr (bool): Extract text using OCR
                - faces (bool): Detect faces in the image
                - qr (bool): Detect and decode QR codes
                - colors (bool): Extract dominant colors
                - web_content (bool): Fetch content from URLs in image
            
        Returns:
            Dict[str, Any]: JSON-serializable dictionary with extracted data.
                           Structure depends on options and debug mode.
            
        Raises:
            ValueError: If image file is invalid or coordinates are missing
            
        Example:
            >>> extractor = GPSLocationExtractor(debug=True)
            >>> result = extractor.process('photo.jpg', 
            ...                           weather=True, 
            ...                           ocr=True, 
            ...                           faces=True)
            >>> print(result['location']['address']['city'])
        """
        result = {}
        
        try:
            # Validate image file
            with TimingContext("Validating image file", self.debug):
                image_path = validate_image_file(image_path)
            
            # Extract EXIF data
            with TimingContext("Extracting EXIF data", self.debug):
                exif_data = ExifExtractor.extract_exif_data(image_path)
                
                # Check if GPS data is available
                has_gps = exif_data.get('lat') is not None and exif_data.get('lon') is not None
                lat, lon = None, None
                
                if has_gps:
                    # Validate coordinates only if they exist
                    lat, lon = validate_coordinates(exif_data['lat'], exif_data['lon'])
                    # Store basic info
                    result['location'] = {'coordinates': {'lat': lat, 'lon': lon}}
                else:
                    # No GPS data available
                    result['location'] = {
                        'note': 'No GPS coordinates found in image EXIF data'
                    }
                
                if exif_data.get('datetime_info'):
                    result['datetime'] = exif_data['datetime_info']
                
                if exif_data.get('camera_info'):
                    result['camera_information'] = exif_data['camera_info']
                
                if exif_data.get('exposure_settings'):
                    result['exposure_settings'] = exif_data['exposure_settings']
            
            # Get location data only if GPS is available
            if has_gps:
                with TimingContext("Reverse geocoding", self.debug):
                    location_data = self.location_service.reverse_geocode(lat, lon)
                    result['location'].update(location_data)
            
            # Extract datetime for weather and other services
            photo_datetime = None
            if result.get('datetime') and result['datetime'].get('timestamp'):
                try:
                    photo_datetime = datetime.fromisoformat(result['datetime']['timestamp'])
                except (ValueError, TypeError):
                    pass
            
            # Get weather data only if GPS is available and requested
            if has_gps and (options.get('weather') or options.get('enhanced_weather')):
                with TimingContext("Fetching weather data", self.debug):
                    weather_data = self.weather_service.get_enhanced_weather_data(lat, lon, photo_datetime)
                    if weather_data:
                        result['weather'] = weather_data
                
                # Get moon phase if requested and datetime is available
                if options.get('enhanced_weather') and photo_datetime:
                    with TimingContext("Calculating moon phase", self.debug):
                        moon_data = self.weather_service.calculate_moon_phase(lat, lon, photo_datetime)
                        if moon_data and moon_data.get('available'):
                            result['moon_phase'] = moon_data
            
            # Get elevation only if GPS is available
            if has_gps and options.get('elevation'):
                with TimingContext("Fetching elevation data", self.debug):
                    elevation = self.location_service.get_elevation(lat, lon)
                    if elevation is not None:
                        result['elevation_m'] = elevation
            
            # Get POIs only if GPS is available
            if has_gps and options.get('pois'):
                with TimingContext("Fetching points of interest", self.debug):
                    distance = options.get('distance', 500)  # Default to 500m if not specified
                    pois = self.location_service.get_nearby_pois(lat, lon, distance)
                    if pois:
                        result['nearby_points_of_interest'] = pois
            
            # Get venues only if GPS is available
            if has_gps and options.get('venues'):
                with TimingContext("Fetching nearby venues", self.debug):
                    distance = options.get('distance', 500)  # Default to 500m if not specified
                    venues = self.location_service.get_enhanced_nearby_venues(lat, lon, distance)
                    if venues:
                        result['nearby_venues'] = venues
            
            # Get businesses only if GPS is available
            if has_gps and options.get('businesses'):
                with TimingContext("Fetching nearby businesses", self.debug):
                    distance = options.get('distance', 500)  # Default to 500m if not specified
                    businesses = self.location_service.get_nearby_businesses(lat, lon, distance)
                    if businesses:
                        result['nearby_businesses'] = businesses
            
            # Get holidays only if GPS and datetime are available
            if has_gps and options.get('holidays') and photo_datetime:
                with TimingContext("Fetching holiday information", self.debug):
                    date_str = photo_datetime.strftime('%Y-%m-%d')
                    holidays = self.location_service.get_holiday_info(lat, lon, date_str)
                    if holidays:
                        result['holidays'] = holidays
            
            # Get historical events only if datetime is available (doesn't need GPS)
            if options.get('events') and photo_datetime:
                with TimingContext("Fetching historical events", self.debug):
                    date_str = photo_datetime.strftime('%Y-%m-%d')
                    events = self.location_service.get_historical_events(date_str)
                    if events:
                        result['historical_events'] = events
            
            # OCR text extraction
            ocr_data = None
            if options.get('ocr'):
                with TimingContext("Extracting text (OCR)", self.debug):
                    ocr_data = self.text_extraction_service.extract_text_from_image(str(image_path))
                    if ocr_data and ocr_data.get('available'):
                        result['text_in_image'] = ocr_data
            
            # Face detection
            if options.get('faces'):
                with TimingContext("Detecting faces", self.debug):
                    face_data = self.image_analysis_service.detect_faces(str(image_path))
                    if face_data and face_data.get('available'):
                        result['faces_in_image'] = face_data
            
            # QR code detection
            qr_data = None
            if options.get('qr'):
                with TimingContext("Detecting QR codes", self.debug):
                    qr_data = self.image_analysis_service.detect_qr_codes(str(image_path))
                    if qr_data and qr_data.get('available'):
                        result['qr_codes'] = qr_data
            
            # Color extraction
            if options.get('colors'):
                with TimingContext("Extracting dominant colors", self.debug):
                    color_data = self.image_analysis_service.extract_dominant_colors(
                        str(image_path), settings.MAX_DOMINANT_COLORS
                    )
                    if color_data and color_data.get('available'):
                        result['dominant_colours'] = color_data
            
            # Web content extraction
            if options.get('web_content'):
                # Extract all URLs from OCR and QR codes with enhanced validation
                all_urls = self.extract_all_urls(ocr_data, qr_data)
                
                # Apply URL count limit to prevent resource exhaustion
                if len(all_urls) > settings.MAX_URLS_TO_PROCESS:
                    if self.debug:
                        print(f"Warning: Found {len(all_urls)} URLs, processing first {settings.MAX_URLS_TO_PROCESS}")
                    all_urls = all_urls[:settings.MAX_URLS_TO_PROCESS]
                
                if all_urls:
                    with TimingContext(f"Extracting web content from {len(all_urls)} URLs", self.debug):
                        # Use enhanced web content service with timeouts and connectivity testing
                        web_content = self.web_content_service.extract_web_content_with_validation(all_urls)
                        if web_content:
                            result['web_content'] = web_content
                            
                            # Add timing info in debug mode
                            if self.debug:
                                success_count = sum(1 for item in web_content if not item.get('error'))
                                fail_count = len(web_content) - success_count
                                print(f"  Web content extraction: {success_count} successful, {fail_count} failed")
            
            # Format output based on debug mode
            if self.debug:
                return build_debug_json(result)
            else:
                return build_default_json(result)
                
        except Exception as e:
            if self.debug:
                import traceback
                traceback.print_exc()
            return {'error': str(e)}
    
    async def process_async(self, image_path: str, strategy: str = 'parallel', **options) -> Dict[str, Any]:
        """
        Process an image asynchronously with concurrent execution of independent operations.
        
        This method provides the same functionality as process() but with concurrent
        execution of independent operations for improved performance. Operations are
        grouped based on their dependencies and executed in parallel where possible.
        
        Processing Strategies:
        - 'parallel': Standard parallel groups (recommended)
        - 'maximal': Maximum parallelism (one operation per group)
        - 'conservative': Conservative grouping for limited resources
        - 'sequential': Sequential execution (same as process())
        
        Args:
            image_path (str): Path to the image file to process
            strategy (str): Processing strategy for grouping operations
            **options: Processing options (same as process() method)
        
        Returns:
            Dict[str, Any]: JSON-serializable dictionary with extracted data
            
        Example:
            >>> extractor = GPSLocationExtractor(debug=True)
            >>> result = await extractor.process_async('photo.jpg', 
            ...                                        strategy='parallel',
            ...                                        weather=True, 
            ...                                        ocr=True, 
            ...                                        faces=True)
        """
        result = {}
        
        try:
            # Phase 1: Extract EXIF data (always sequential)
            async with AsyncTimingContext("Extracting EXIF data", self.debug):
                image_path = validate_image_file(image_path)
                exif_data = ExifExtractor.extract_exif_data(image_path)
                
                # Check if GPS coordinates are available
                lat, lon = None, None
                has_gps = exif_data.get('has_gps', False)
                
                if has_gps:
                    # Validate coordinates if they exist
                    lat, lon = validate_coordinates(exif_data['lat'], exif_data['lon'])
                    result['location'] = {'coordinates': {'lat': lat, 'lon': lon}}
                else:
                    # No GPS data - note this in the result
                    result['location'] = {
                        'note': 'No GPS coordinates found in image EXIF data'
                    }
                
                # Always include datetime, camera, and exposure info if available
                if exif_data.get('datetime'):
                    result['datetime'] = exif_data['datetime']
                
                if exif_data.get('camera_info'):
                    result['camera_information'] = exif_data['camera_info']
                
                if exif_data.get('exposure_settings'):
                    result['exposure_settings'] = exif_data['exposure_settings']
            
            # Extract datetime for other services
            photo_datetime = None
            if result.get('datetime') and result['datetime'].get('timestamp'):
                try:
                    photo_datetime = datetime.fromisoformat(result['datetime']['timestamp'])
                except (ValueError, TypeError):
                    pass
            
            # Phase 2: Execute operations based on strategy
            if strategy == 'sequential':
                # Use original sequential processing
                return await self._process_sequential_async(result, lat, lon, photo_datetime, image_path, options, has_gps)
            else:
                # Use parallel processing
                return await self._process_parallel_async(result, lat, lon, photo_datetime, image_path, strategy, options, has_gps)
                
        except Exception as e:
            if self.debug:
                import traceback
                traceback.print_exc()
            return {'error': str(e)}
    
    async def _process_sequential_async(self, result: Dict[str, Any], lat: Optional[float], lon: Optional[float], 
                                       photo_datetime: Optional[datetime], image_path: str, 
                                       options: Dict[str, Any], has_gps: bool = True) -> Dict[str, Any]:
        """Process operations sequentially (async version of original process method)"""
        
        # Only process location-dependent operations if GPS coordinates are available
        if has_gps and lat is not None and lon is not None:
            # Get location data
            async with AsyncTimingContext("Reverse geocoding", self.debug):
                location_data = await self._run_sync_in_thread(self.location_service.reverse_geocode, lat, lon)
                result['location'].update(location_data)
            
            # Weather data
            if options.get('weather') or options.get('enhanced_weather'):
                async with AsyncTimingContext("Fetching weather data", self.debug):
                    weather_data = await self._run_sync_in_thread(
                        self.weather_service.get_enhanced_weather_data, lat, lon, photo_datetime
                    )
                    if weather_data:
                        result['weather'] = weather_data
                
                if options.get('enhanced_weather') and photo_datetime:
                    async with AsyncTimingContext("Calculating moon phase", self.debug):
                        moon_data = await self._run_sync_in_thread(
                            self.weather_service.calculate_moon_phase, lat, lon, photo_datetime
                        )
                        if moon_data and moon_data.get('available'):
                            result['moon_phase'] = moon_data
        
        # Use the coordinator for remaining operations
        coordinator = AsyncCoordinator(self.debug)
        
        # Add location-dependent operations only if GPS is available
        if has_gps and lat is not None and lon is not None:
            if options.get('elevation'):
                group = coordinator.create_group("Elevation")
                group.add_task("elevation", self.location_service.get_elevation, lat, lon)
            
            if options.get('pois'):
                group = coordinator.create_group("POIs")
                distance = options.get('distance', 500)  # Default to 500m if not specified
                group.add_task("pois", self.location_service.get_nearby_pois, lat, lon, distance)
            
            if options.get('venues'):
                group = coordinator.create_group("Venues")
                distance = options.get('distance', 500)  # Default to 500m if not specified
                group.add_task("venues", self.location_service.get_enhanced_nearby_venues, lat, lon, distance)
            
            if options.get('businesses'):
                group = coordinator.create_group("Businesses")
                distance = options.get('distance', 500)  # Default to 500m if not specified
                group.add_task("businesses", self.location_service.get_nearby_businesses, lat, lon, distance)
            
            if options.get('holidays') and photo_datetime:
                group = coordinator.create_group("Holidays")
                date_str = photo_datetime.strftime('%Y-%m-%d')
                group.add_task("holidays", self.location_service.get_holiday_info, lat, lon, date_str)
            
            if options.get('events') and photo_datetime:
                group = coordinator.create_group("Events")
                date_str = photo_datetime.strftime('%Y-%m-%d')
                group.add_task("events", self.location_service.get_historical_events, date_str)
        
        if options.get('ocr'):
            group = coordinator.create_group("OCR")
            group.add_task("ocr", self.text_extraction_service.extract_text_from_image, str(image_path))
        
        if options.get('faces'):
            group = coordinator.create_group("Faces")
            group.add_task("faces", self.image_analysis_service.detect_faces, str(image_path))
        
        if options.get('qr'):
            group = coordinator.create_group("QR")
            group.add_task("qr", self.image_analysis_service.detect_qr_codes, str(image_path))
        
        if options.get('colors'):
            group = coordinator.create_group("Colors")
            group.add_task("colors", self.image_analysis_service.extract_dominant_colors, 
                          str(image_path), settings.MAX_DOMINANT_COLORS)
        
        # Execute all tasks
        task_results = await coordinator.execute_all_groups()
        
        # Process results and add to main result
        self._merge_task_results(result, task_results, options)
        
        # Web content extraction (depends on OCR/QR results)
        if options.get('web_content'):
            ocr_data = task_results.get('ocr')
            qr_data = task_results.get('qr')
            # Use async URL extraction with enhanced validation
            all_urls = await self.extract_all_urls_async(ocr_data, qr_data)
            
            if all_urls:
                async with AsyncTimingContext(f"Extracting web content from {len(all_urls)} URLs", self.debug):
                    # Use enhanced async web content extraction
                    web_content_results = await self.web_content_service.extract_multiple_urls_async(
                        all_urls, validate_connectivity=settings.ENABLE_URL_CONNECTIVITY_CHECK
                    )
                    
                    # Convert results to legacy format for compatibility
                    if web_content_results:
                        web_content = [self._convert_web_content_result(r) for r in web_content_results]
                        
                        result['web_content'] = web_content
                        
                        # Add timing info in debug mode
                        if self.debug:
                            success_count = sum(1 for r in web_content_results if not r.error)
                            fail_count = len(web_content_results) - success_count
                            print(f"  Web content extraction: {success_count} successful, {fail_count} failed")
        
        # Format output
        if self.debug:
            return build_debug_json(result)
        else:
            return build_default_json(result)
    
    async def _process_parallel_async(self, result: Dict[str, Any], lat: Optional[float], lon: Optional[float],
                                     photo_datetime: Optional[datetime], image_path: str,
                                     strategy: str, options: Dict[str, Any], has_gps: bool = True) -> Dict[str, Any]:
        """Process operations using parallel execution strategy"""
        
        # Get processing strategy
        if strategy == 'maximal':
            group_definitions = AsyncProcessingStrategy.get_maximal_parallel_groups()
        elif strategy == 'conservative':
            group_definitions = AsyncProcessingStrategy.get_conservative_groups()
        else:  # 'parallel'
            group_definitions = AsyncProcessingStrategy.get_parallel_groups()
        
        # Phase 1: Core location data (only if GPS is available)
        if has_gps and lat is not None and lon is not None:
            group1 = self.async_coordinator.create_group("Core Location Data")
            
            # Get location data
            group1.add_task("location", self.location_service.reverse_geocode, lat, lon)
            
            if options.get('weather') or options.get('enhanced_weather'):
                group1.add_task("weather", self.weather_service.get_enhanced_weather_data, lat, lon, photo_datetime)
            
            if options.get('elevation'):
                group1.add_task("elevation", self.location_service.get_elevation, lat, lon)
            
            phase1_results = await group1.execute()
            
            # Update location data
            if 'location' in phase1_results:
                result['location'].update(phase1_results['location'])
            
            if 'weather' in phase1_results and phase1_results['weather']:
                result['weather'] = phase1_results['weather']
            
            if 'elevation' in phase1_results and phase1_results['elevation'] is not None:
                result['elevation_m'] = phase1_results['elevation']
            
            # Moon phase calculation if enhanced weather requested
            if options.get('enhanced_weather') and photo_datetime:
                async with AsyncTimingContext("Calculating moon phase", self.debug):
                    moon_data = await self._run_sync_in_thread(
                        self.weather_service.calculate_moon_phase, lat, lon, photo_datetime
                    )
                    if moon_data and moon_data.get('available'):
                        result['moon_phase'] = moon_data
        
        # Phase 2: Image analysis (faces, QR, OCR, colors)
        group2 = self.async_coordinator.create_group("Image Analysis")
        
        if options.get('faces'):
            group2.add_task("faces", self.image_analysis_service.detect_faces, str(image_path))
        
        if options.get('qr'):
            group2.add_task("qr", self.image_analysis_service.detect_qr_codes, str(image_path))
        
        if options.get('ocr'):
            group2.add_task("ocr", self.text_extraction_service.extract_text_from_image, str(image_path))
        
        if options.get('colors'):
            group2.add_task("colors", self.image_analysis_service.extract_dominant_colors, 
                          str(image_path), settings.MAX_DOMINANT_COLORS)
        
        # Phase 3: Location-based enrichment (only if GPS is available)
        group3 = self.async_coordinator.create_group("Location Enrichment")
        
        if has_gps and lat is not None and lon is not None:
            if options.get('venues'):
                distance = options.get('distance', 500)  # Default to 500m if not specified
                group3.add_task("venues", self.location_service.get_enhanced_nearby_venues, lat, lon, distance)
            
            if options.get('pois'):
                distance = options.get('distance', 500)  # Default to 500m if not specified
                group3.add_task("pois", self.location_service.get_nearby_pois, lat, lon, distance)
            
            if options.get('businesses'):
                distance = options.get('distance', 500)  # Default to 500m if not specified
                group3.add_task("businesses", self.location_service.get_nearby_businesses, lat, lon, distance)
            
            if options.get('holidays') and photo_datetime:
                date_str = photo_datetime.strftime('%Y-%m-%d')
                group3.add_task("holidays", self.location_service.get_holiday_info, lat, lon, date_str)
            
            if options.get('events') and photo_datetime:
                date_str = photo_datetime.strftime('%Y-%m-%d')
                group3.add_task("events", self.location_service.get_historical_events, date_str)
        
        # Execute Groups 2 and 3 concurrently
        self.async_coordinator.clear_groups()  # Clear previous groups
        self.async_coordinator.groups = [group2, group3]
        
        parallel_results = await self.async_coordinator.execute_groups_concurrently()
        
        # Process results
        self._merge_task_results(result, parallel_results, options)
        
        # Phase 4: Web content extraction (depends on URLs from OCR/QR)
        if options.get('web_content'):
            ocr_data = parallel_results.get('ocr')
            qr_data = parallel_results.get('qr')
            # Use async URL extraction with enhanced validation
            all_urls = await self.extract_all_urls_async(ocr_data, qr_data)
            
            # Apply URL count limit to prevent resource exhaustion
            if len(all_urls) > settings.MAX_URLS_TO_PROCESS:
                if self.debug:
                    print(f"Warning: Found {len(all_urls)} URLs, processing first {settings.MAX_URLS_TO_PROCESS}")
                all_urls = all_urls[:settings.MAX_URLS_TO_PROCESS]
            
            if all_urls:
                async with AsyncTimingContext(f"Extracting web content from {len(all_urls)} URLs", self.debug):
                    # Use enhanced async web content extraction
                    web_content_results = await self.web_content_service.extract_multiple_urls_async(
                        all_urls, validate_connectivity=settings.ENABLE_URL_CONNECTIVITY_CHECK
                    )
                    
                    # Convert results to legacy format for compatibility
                    if web_content_results:
                        web_content = [self._convert_web_content_result(r) for r in web_content_results]
                        
                        result['web_content'] = web_content
                        
                        # Add timing info in debug mode
                        if self.debug:
                            success_count = sum(1 for r in web_content_results if not r.error)
                            fail_count = len(web_content_results) - success_count
                            print(f"  Web content extraction: {success_count} successful, {fail_count} failed")
        
        # Format output
        if self.debug:
            return build_debug_json(result)
        else:
            return build_default_json(result)
    
    async def _run_sync_in_thread(self, func, *args, **kwargs):
        """Run a synchronous function in a thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._shared_thread_pool, lambda: func(*args, **kwargs))
    
    def _convert_web_content_result(self, result) -> Dict[str, Any]:
        """Convert WebContentResult to legacy dictionary format"""
        item = {'url': result.url}
        if result.content:
            item['content'] = result.content
            if result.content_truncated:
                item['content_truncated'] = True
                item['original_length'] = result.original_length
        if result.metadata:
            item['metadata'] = result.metadata
        if result.error:
            item['error'] = result.error
            item['error_type'] = result.error_type
        if result.extraction_time_ms:
            item['extraction_time_ms'] = result.extraction_time_ms
        return item
    
    def _merge_task_results(self, result: Dict[str, Any], task_results: Dict[str, Any], 
                           options: Dict[str, Any]):
        """Merge task results into the main result dictionary"""
        
        # Map task names to result keys
        result_mapping = {
            'faces': 'faces_in_image',
            'qr': 'qr_codes',
            'ocr': 'text_in_image',
            'colors': 'dominant_colours',
            'venues': 'nearby_venues',
            'pois': 'nearby_points_of_interest',
            'businesses': 'nearby_businesses',
            'holidays': 'holidays',
            'events': 'historical_events'
        }
        
        for task_name, task_result in task_results.items():
            if task_name in result_mapping and task_result is not None:
                # Handle different result formats
                if isinstance(task_result, dict):
                    # For dict results, check if they have 'available' flag
                    if task_result.get('available', True):  # Default to True if no 'available' key
                        result[result_mapping[task_name]] = task_result
                elif isinstance(task_result, list):
                    # For list results (like venues, pois), store directly if not empty
                    if task_result:  # Only store non-empty lists
                        result[result_mapping[task_name]] = task_result
                else:
                    # For other types (strings, numbers), store directly
                    result[result_mapping[task_name]] = task_result
    
    def format_human_readable(self, data: Dict[str, Any], options: Dict[str, bool]) -> str:
        """
        Format the extracted data as human-readable text.
        
        This method converts the structured JSON data into natural language
        sentences suitable for display to end users. It follows the original
        shell script's output format for compatibility.
        
        The output format varies based on available data:
        - With datetime: "This photo was taken on [day], [month] [date], [year]..."
        - Without datetime: "This photo was taken at this address:..."
        
        Additional sections can be added for weather, POIs, events, etc.
        based on the options provided and data available.
        
        Args:
            data (Dict[str, Any]): Processed data from the process() method
            options (Dict[str, bool]): Options indicating what to include:
                - date: Include date/time information
                - weather: Include weather description
                - Others can be added as needed
                
        Returns:
            str: Human-readable text description, with sections separated
                by double newlines
                
        Example:
            >>> text = extractor.format_human_readable(data, {'date': True})
            >>> print(text)
            This photo was taken on Sunday, October 15, 2023 at 2:30 PM
            at this address: Main Street in 12345 Berlin (Germany).
            
        Note:
            This method prioritizes readability over completeness. Not all
            data from the JSON structure is included in the text output.
        """
        output = []
        
        # Location and datetime
        if 'location' in data and 'address' in data['location']:
            addr = data['location']['address']
            
            if options.get('date') and 'datetime' in data:
                dt = data['datetime']
                # Format: "This photo was taken on Sunday, October 15, 2023 at 2:30 PM..."
                date_str = f"{dt.get('weekday', 'Unknown day')}, "
                date_str += f"{dt.get('month_name', 'Unknown')} {dt.get('day', 'Unknown')}, {dt.get('year', 'Unknown')}"
                time_str = dt.get('local_time', 'Unknown time')
                
                output.append(
                    f"This photo was taken on {date_str} at {time_str} "
                    f"at this address: {addr.get('street', 'Unknown')} "
                    f"in {addr.get('postal_code', '')} {addr.get('city', 'Unknown')} "
                    f"({addr.get('country', 'Unknown')})."
                )
            else:
                output.append(
                    f"This photo was taken at this address: {addr.get('street', 'Unknown')} "
                    f"in {addr.get('postal_code', '')} {addr.get('city', 'Unknown')} "
                    f"({addr.get('country', 'Unknown')}). Date and time are unknown."
                )
        
        # Weather information
        if options.get('weather') and 'weather' in data:
            weather = data['weather']
            weather_parts = []
            
            # Temperature
            if 'temperature_celsius' in weather:
                temp = weather['temperature_celsius']
                weather_parts.append(f"{temp}°C")
                if 'apparent_temperature_celsius' in weather:
                    apparent = weather['apparent_temperature_celsius']
                    if apparent != temp:
                        weather_parts.append(f"feels like {apparent}°C")
            
            # Description
            if 'description' in weather:
                weather_parts.append(weather['description'])
            
            # Wind
            if 'wind_speed_kmh' in weather and weather['wind_speed_kmh'] > 0:
                wind_str = f"wind {weather['wind_speed_kmh']} km/h"
                if 'wind_direction' in weather:
                    wind_str += f" {weather['wind_direction']}"
                if 'wind_gusts_kmh' in weather and weather['wind_gusts_kmh'] > weather['wind_speed_kmh']:
                    wind_str += f" (gusts {weather['wind_gusts_kmh']} km/h)"
                weather_parts.append(wind_str)
            
            # Precipitation
            precip_parts = []
            if 'rain_mm' in weather and weather['rain_mm'] > 0:
                precip_parts.append(f"rain {weather['rain_mm']}mm")
            if 'snowfall_cm' in weather and weather['snowfall_cm'] > 0:
                precip_parts.append(f"snow {weather['snowfall_cm']}cm")
            if precip_parts:
                weather_parts.append(', '.join(precip_parts))
            elif 'precipitation_mm' in weather and weather['precipitation_mm'] == 0:
                weather_parts.append("no precipitation")
            
            # Humidity
            if 'relative_humidity_percent' in weather:
                weather_parts.append(f"humidity {weather['relative_humidity_percent']}%")
            
            # Visibility
            if 'visibility_km' in weather:
                weather_parts.append(f"visibility {weather['visibility_km']} km")
            elif 'visibility_m' in weather:
                weather_parts.append(f"visibility {weather['visibility_m']}m")
            
            # UV Index
            if 'uv_index' in weather and 'uv_category' in weather:
                weather_parts.append(f"UV index {weather['uv_index']} ({weather['uv_category']})")
            
            if weather_parts:
                output.append(f"Weather: {', '.join(weather_parts)}")
        
        # Enhanced weather (moon phase, air quality, UV)
        if options.get('enhanced_weather'):
            if 'moon_phase' in data and data['moon_phase'].get('phase'):
                output.append(f"Moon phase: {data['moon_phase']['phase']}")
            if 'air_quality' in data['weather'] and data['weather']['air_quality'].get('category'):
                output.append(f"Air quality: {data['weather']['air_quality']['category']}")
        
        # Elevation
        if options.get('elevation') and 'elevation_m' in data:
            output.append(f"Elevation: {data['elevation_m']} meters")
        
        # Points of Interest
        if options.get('pois') and 'nearby_points_of_interest' in data:
            pois = data['nearby_points_of_interest']
            if pois:
                poi_lines = ["Nearby points of interest:"]
                for poi in pois[:3]:  # Limit to first 3
                    poi_lines.append(f"- {poi['name']} ({poi['type']}) - {poi['distance_m']}m away")
                output.append('\n'.join(poi_lines))
        
        # Businesses
        if options.get('businesses') and 'nearby_businesses' in data:
            businesses = data['nearby_businesses']
            if businesses:
                business_lines = ["Nearby businesses:"]
                for category, types in businesses.items():
                    business_lines.append(f"\n{category.title()}:")
                    for biz_type, biz_list in types.items():
                        if biz_list:
                            business_lines.append(f"  {biz_type}:")
                            for biz in biz_list[:2]:  # Limit to 2 per type
                                business_lines.append(f"  - {biz['name']} ({biz['distance_m']}m)")
                output.append('\n'.join(business_lines))
        
        # Venues
        if options.get('venues') and 'nearby_venues' in data:
            venues = data['nearby_venues']
            if venues:
                venue_lines = ["Nearby venues:"]
                for venue_type, venue_list in venues.items():
                    if venue_list:
                        venue_lines.append(f"\n{venue_type.replace('_', ' ').title()}s:")
                        for venue in venue_list[:3]:  # Limit to 3 per type
                            venue_lines.append(f"- {venue['name']} ({venue['distance_m']}m)")
                output.append('\n'.join(venue_lines))
        
        # Holidays
        if options.get('holidays') and 'holidays' in data:
            holidays = data['holidays']
            if holidays:
                holiday_names = [h['name'] for h in holidays]
                output.append(f"Holidays: {', '.join(holiday_names)}")
        
        # Historical events
        if options.get('events') and 'historical_events' in data:
            events = data['historical_events']
            if events:
                event_lines = ["Historical events on this date:"]
                for event in events:
                    event_lines.append(f"- {event}")
                output.append('\n'.join(event_lines))
        
        # OCR text
        if options.get('ocr') and 'text_in_image' in data:
            text_data = data['text_in_image']
            if text_data.get('raw_text'):
                output.append(f"Text found in image:\n{text_data['raw_text'][:200]}..." 
                             if len(text_data['raw_text']) > 200 else f"Text found in image:\n{text_data['raw_text']}")
        
        # Face detection
        if options.get('faces') and 'faces_in_image' in data:
            face_data = data['faces_in_image']
            if face_data.get('count', 0) > 0:
                output.append(f"Faces detected: {face_data['count']}")
        
        # QR codes
        if options.get('qr') and 'qr_codes' in data:
            qr_data = data['qr_codes']
            if qr_data.get('count', 0) > 0:
                qr_lines = [f"QR codes detected: {qr_data['count']}"]
                for code in qr_data.get('codes', [])[:3]:  # Limit to first 3
                    qr_lines.append(f"- {code['type']}: {code['data'][:50]}..." 
                                   if len(code['data']) > 50 else f"- {code['type']}: {code['data']}")
                output.append('\n'.join(qr_lines))
        
        # Dominant colors
        if options.get('colors') and 'dominant_colours' in data:
            colors = data['dominant_colours']
            color_names = []
            for i in range(1, 6):  # Up to 5 colors
                color_key = f'color_{i}'
                if color_key in colors and 'name' in colors[color_key]:
                    color_names.append(colors[color_key]['name'])
            if color_names:
                output.append(f"Dominant colors: {', '.join(color_names)}")
        
        # Web content
        if options.get('web_content') and 'web_content' in data:
            web_data = data['web_content']
            if web_data.get('urls_analyzed', 0) > 0:
                output.append(f"Web content extracted from {web_data['urls_analyzed']} URL(s)")
        
        return '\n\n'.join(output) if output else "No location information available."
    
    def cleanup(self):
        """Cleanup resources used by the extractor"""
        # Cleanup web content service
        if hasattr(self, 'web_content_service'):
            self.web_content_service.cleanup()
        
        # Shutdown shared thread pool
        if hasattr(self, '_shared_thread_pool'):
            try:
                self._shared_thread_pool.shutdown(wait=True)
            except Exception:
                pass
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources"""
        self.cleanup()
        return False
    
    # Note: __del__ method removed as it's unreliable for resource cleanup.
    # Use context manager or explicit cleanup() calls instead.