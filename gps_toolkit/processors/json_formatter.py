"""JSON formatting and building functions for GPS Toolkit"""

import copy
from typing import Dict, Any
from ..core.utils import format_focal_length, remove_empty_values


def build_debug_json(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build debug JSON output with all available data"""
    # In debug mode, return everything as-is
    return result


def build_default_json(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build default JSON output with filtered and formatted data"""
    # Deep copy to avoid modifying original
    filtered = copy.deepcopy(result)
    
    # Remove location coordinates
    if 'location' in filtered and 'coordinates' in filtered['location']:
        del filtered['location']['coordinates']
    
    # Clean up location address
    if 'location' in filtered and 'address' in filtered['location']:
        if 'country_code' in filtered['location']['address']:
            del filtered['location']['address']['country_code']
    
    # Clean up camera information
    if 'camera_information' in filtered:
        camera = filtered['camera_information']
        if 'make' in camera:
            del camera['make']
        if 'software' in camera:
            del camera['software']
        # Remove lens_model if it's "Unknown"
        if 'lens_model' in camera and camera['lens_model'] == 'Unknown':
            del camera['lens_model']
    
    # Clean up exposure settings
    if 'exposure_settings' in filtered:
        exposure = filtered['exposure_settings']
        for key in ['exposure_mode', 'white_balance', 'metering_mode', 'exposure_program']:
            if key in exposure:
                del exposure[key]
        
        # Format focal length
        if 'focal_length' in exposure:
            exposure['focal_length'] = format_focal_length(exposure['focal_length'])
    
    # Clean up datetime
    if 'datetime' in filtered:
        dt = filtered['datetime']
        if 'timestamp' in dt:
            del dt['timestamp']
        if 'timezone' in dt:
            del dt['timezone']
    
    # Clean up POIs
    if 'nearby_points_of_interest' in filtered:
        for poi in filtered['nearby_points_of_interest']:
            if 'wikipedia' in poi:
                del poi['wikipedia']
    
    # Clean up weather - preserve detailed fields but format them nicely
    if 'weather' in filtered:
        weather = filtered['weather']
        if 'weather_code' in weather:
            del weather['weather_code']
        
        # Round all temperature values to 1 decimal
        temp_fields = ['temperature_celsius', 'apparent_temperature_celsius', 'dewpoint_celsius']
        for field in temp_fields:
            if field in weather and weather[field] is not None:
                weather[field] = round(weather[field], 1)
        
        # Round wind values to whole numbers
        wind_fields = ['wind_speed_kmh', 'wind_gusts_kmh']
        for field in wind_fields:
            if field in weather and weather[field] is not None:
                weather[field] = round(weather[field])
        
        # Round pressure values to whole numbers
        pressure_fields = ['pressure_hpa', 'surface_pressure_hpa']
        for field in pressure_fields:
            if field in weather and weather[field] is not None:
                weather[field] = round(weather[field])
        
        # Convert visibility from meters to kilometers if > 1000m
        if 'visibility_m' in weather and weather['visibility_m'] is not None:
            if weather['visibility_m'] >= 1000:
                weather['visibility_km'] = round(weather['visibility_m'] / 1000, 1)
                del weather['visibility_m']
            else:
                weather['visibility_m'] = round(weather['visibility_m'])
        
        # Clean up air quality
        if 'air_quality' in weather:
            aq = weather['air_quality']
            # Keep only essential air quality data
            essential_keys = ['aqi', 'category']
            aq_cleaned = {k: v for k, v in aq.items() if k in essential_keys}
            weather['air_quality'] = aq_cleaned
    
    # Clean up moon phase
    if 'moon_phase' in filtered:
        moon = filtered['moon_phase']
        if 'available' in moon:
            del moon['available']
        if 'rise_time' in moon:
            del moon['rise_time']
        if 'set_time' in moon:
            del moon['set_time']
    
    # Clean up text extraction
    if 'text_in_image' in filtered:
        text_data = filtered['text_in_image']
        if 'available' in text_data:
            del text_data['available']
        if 'average_confidence' in text_data:
            del text_data['average_confidence']
        # Remove ocr_method field
        if 'ocr_method' in text_data:
            del text_data['ocr_method']
    
    # Clean up faces
    if 'faces_in_image' in filtered:
        faces = filtered['faces_in_image']
        if 'available' in faces:
            del faces['available']
        if 'method' in faces:
            del faces['method']
        if 'locations' in faces:
            del faces['locations']
    
    # Clean up QR codes
    if 'qr_codes' in filtered:
        qr = filtered['qr_codes']
        if 'available' in qr:
            del qr['available']
        # Simplify codes
        if 'codes' in qr:
            simplified_codes = []
            for code in qr['codes']:
                simplified = {
                    'data': code.get('data', ''),
                    'type': code.get('type', 'QRCODE')
                }
                simplified_codes.append(simplified)
            qr['codes'] = simplified_codes
    
    # Clean up colors
    if 'dominant_colours' in filtered:
        colors = filtered['dominant_colours']
        if 'available' in colors:
            del colors['available']
        # Remove RGB values and percentages
        for i in range(1, 6):
            color_key = f'color_{i}'
            if color_key in colors and isinstance(colors[color_key], dict):
                color_data = colors[color_key]
                # Keep only hex and name
                colors[color_key] = {
                    'hex': color_data.get('hex', '#000000'),
                    'name': color_data.get('name', 'unknown')
                }
    
    # Clean up venues
    if 'nearby_venues' in filtered:
        for venue_type, venues in filtered['nearby_venues'].items():
            for venue in venues:
                # Remove wheelchair_accessible if false
                if 'wheelchair_accessible' in venue and not venue['wheelchair_accessible']:
                    del venue['wheelchair_accessible']
                # Remove wifi if false
                if 'wifi' in venue and not venue['wifi']:
                    del venue['wifi']
    
    # Clean up web content
    if 'web_content' in filtered:
        for content in filtered['web_content']:
            # Remove content_truncated if false
            if 'content_truncated' in content and not content['content_truncated']:
                del content['content_truncated']
            # Remove original_length if not truncated
            if 'original_length' in content and not content.get('content_truncated', False):
                del content['original_length']
            # Remove extraction_time_ms field
            if 'extraction_time_ms' in content:
                del content['extraction_time_ms']
    
    # Apply aggressive cleaning for non-debug mode
    filtered = _clean_json_aggressive(filtered)
    
    # Remove empty values recursively
    filtered = remove_empty_values(filtered)
    
    return filtered if filtered else {}


def _clean_json_aggressive(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggressively clean JSON output for non-debug mode.
    Removes any values that are not meaningful:
    - Empty strings
    - Null/None values
    - "0" values (as strings)
    - "Unknown" values
    - Error values
    - Specific unwanted fields
    """
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            # Skip specific fields we never want in non-debug mode
            if key in ['ocr_method', 'extraction_time_ms', 'available', 'reason']:
                continue
            
            # Recursively clean nested structures
            if isinstance(value, dict):
                cleaned_value = _clean_json_aggressive(value)
                if cleaned_value:  # Only include if not empty after cleaning
                    cleaned[key] = cleaned_value
            elif isinstance(value, list):
                cleaned_list = []
                for item in value:
                    if isinstance(item, dict):
                        cleaned_item = _clean_json_aggressive(item)
                        if cleaned_item:
                            cleaned_list.append(cleaned_item)
                    elif item not in [None, '', '0', 'Unknown', 'unknown', 'Error']:
                        cleaned_list.append(item)
                if cleaned_list:  # Only include if not empty after cleaning
                    cleaned[key] = cleaned_list
            # Check scalar values
            elif value not in [None, '', '0', 'Unknown', 'unknown', 'Error']:
                # Special handling for lens_model
                if key == 'lens_model' and value == 'Unknown':
                    continue
                # Special handling for weather fields where 0 is meaningful
                weather_fields = ['temperature_celsius', 'apparent_temperature_celsius', 'dewpoint_celsius',
                                'precipitation_mm', 'rain_mm', 'snowfall_cm', 'wind_speed_kmh', 
                                'wind_gusts_kmh', 'wind_direction_degrees', 'visibility_m', 'visibility_km']
                if key in weather_fields and value == 0:
                    cleaned[key] = value
                # Keep all other meaningful values including False and 0
                else:
                    cleaned[key] = value
        
        return cleaned
    else:
        return obj