"""Weather and moon phase services for GPS Toolkit"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import requests

from ..config import settings

# Set up logging
logger = logging.getLogger(__name__)

# Try to import ephem for moon phase calculations
try:
    import ephem
    HAS_EPHEM = True
except ImportError:
    HAS_EPHEM = False


class WeatherService:
    """Service for weather-related operations"""
    
    def __init__(self, thread_pool=None):
        """Initialize weather service.
        
        Args:
            thread_pool: Optional shared ThreadPoolExecutor for consistency
                        with other services. Not used directly but allows
                        future async-native implementations.
        """
        self._thread_pool = thread_pool
        self.weather_codes = {
            0: "clear sky",
            1: "mainly clear", 2: "mainly clear",
            3: "overcast",
            45: "foggy", 48: "foggy",
            51: "drizzle", 53: "drizzle", 55: "drizzle",
            61: "rain", 63: "rain", 65: "rain",
            71: "snow", 73: "snow", 75: "snow",
            80: "rain showers", 81: "rain showers", 82: "rain showers",
            95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm"
        }
    
    def get_enhanced_weather_data(self, lat: float, lon: float, dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Get enhanced weather data including air quality and UV index"""
        # Validate coordinates
        if lat is None or lon is None:
            return {}
        if not (-90 <= lat <= 90):
            raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and 90.")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Invalid longitude: {lon}. Must be between -180 and 180.")
        
        weather_data = {}
        
        # Get basic weather data
        if dt:
            # Historical weather - request comprehensive weather parameters
            date_str = dt.strftime('%Y-%m-%d')
            hour = dt.hour
            
            # Request detailed weather parameters including wind, humidity, pressure, etc.
            weather_params = [
                'temperature_2m',
                'apparent_temperature',
                'precipitation',
                'rain',
                'snowfall',
                'weathercode',
                'cloudcover',
                'windspeed_10m',
                'winddirection_10m',
                'windgusts_10m',
                'relativehumidity_2m',
                'dewpoint_2m',
                'pressure_msl',
                'surface_pressure',
                'visibility',
                'uv_index'
            ]
            
            url = f"https://archive-api.open-meteo.com/v1/era5?latitude={lat}&longitude={lon}&start_date={date_str}&end_date={date_str}&hourly={','.join(weather_params)}&timezone=auto"
            
            try:
                response = requests.get(url, timeout=settings.REQUEST_TIMEOUT_S)
                response.raise_for_status()
                data = response.json()
                
                if 'hourly' in data:
                    # Extract all weather parameters
                    hourly = data['hourly']
                    
                    # Temperature data
                    weather_data['temperature_celsius'] = hourly['temperature_2m'][hour] if hour < len(hourly['temperature_2m']) else None
                    weather_data['apparent_temperature_celsius'] = hourly.get('apparent_temperature', [None] * 24)[hour] if hour < len(hourly.get('apparent_temperature', [])) else None
                    
                    # Precipitation data
                    weather_data['precipitation_mm'] = hourly['precipitation'][hour] if hour < len(hourly['precipitation']) else None
                    weather_data['rain_mm'] = hourly.get('rain', [None] * 24)[hour] if hour < len(hourly.get('rain', [])) else None
                    weather_data['snowfall_cm'] = hourly.get('snowfall', [None] * 24)[hour] if hour < len(hourly.get('snowfall', [])) else None
                    
                    # Wind data
                    weather_data['wind_speed_kmh'] = hourly.get('windspeed_10m', [None] * 24)[hour] if hour < len(hourly.get('windspeed_10m', [])) else None
                    weather_data['wind_direction_degrees'] = hourly.get('winddirection_10m', [None] * 24)[hour] if hour < len(hourly.get('winddirection_10m', [])) else None
                    weather_data['wind_gusts_kmh'] = hourly.get('windgusts_10m', [None] * 24)[hour] if hour < len(hourly.get('windgusts_10m', [])) else None
                    
                    # Atmospheric data
                    weather_data['relative_humidity_percent'] = hourly.get('relativehumidity_2m', [None] * 24)[hour] if hour < len(hourly.get('relativehumidity_2m', [])) else None
                    weather_data['dewpoint_celsius'] = hourly.get('dewpoint_2m', [None] * 24)[hour] if hour < len(hourly.get('dewpoint_2m', [])) else None
                    weather_data['pressure_hpa'] = hourly.get('pressure_msl', [None] * 24)[hour] if hour < len(hourly.get('pressure_msl', [])) else None
                    weather_data['surface_pressure_hpa'] = hourly.get('surface_pressure', [None] * 24)[hour] if hour < len(hourly.get('surface_pressure', [])) else None
                    
                    # Cloud and visibility
                    weather_data['cloud_cover_percent'] = hourly['cloudcover'][hour] if hour < len(hourly['cloudcover']) else None
                    weather_data['visibility_m'] = hourly.get('visibility', [None] * 24)[hour] if hour < len(hourly.get('visibility', [])) else None
                    
                    # UV and weather code
                    weather_data['weather_code'] = hourly['weathercode'][hour] if hour < len(hourly['weathercode']) else None
                    weather_data['uv_index'] = hourly.get('uv_index', [None] * 24)[hour] if hour < len(hourly.get('uv_index', [])) else None
                    
                    weather_data['timezone'] = data.get('timezone', 'UTC')
                    
                    # Decode weather code
                    weather_code = weather_data.get('weather_code')
                    if weather_code is not None:
                        weather_data['description'] = self._decode_weather_code(weather_code)
                    
                    # Add wind direction as compass point
                    wind_dir = weather_data.get('wind_direction_degrees')
                    if wind_dir is not None:
                        weather_data['wind_direction'] = self._get_wind_direction(wind_dir)
            except requests.RequestException as e:
                logger.warning(f"Failed to get weather data for lat={lat}, lon={lon}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error getting weather data: {e}", exc_info=True)
        else:
            # Current weather - also request comprehensive parameters
            weather_params = [
                'temperature_2m',
                'apparent_temperature',
                'precipitation',
                'rain',
                'snowfall',
                'weathercode',
                'cloudcover',
                'windspeed_10m',
                'winddirection_10m',
                'windgusts_10m',
                'relativehumidity_2m',
                'dewpoint_2m',
                'pressure_msl',
                'surface_pressure',
                'visibility',
                'uv_index'
            ]
            
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current={','.join(weather_params)}&timezone=auto"
            
            try:
                response = requests.get(url, timeout=settings.REQUEST_TIMEOUT_S)
                response.raise_for_status()
                data = response.json()
                
                if 'current' in data:
                    current = data['current']
                    
                    # Temperature data
                    weather_data['temperature_celsius'] = current.get('temperature_2m')
                    weather_data['apparent_temperature_celsius'] = current.get('apparent_temperature')
                    
                    # Precipitation data
                    weather_data['precipitation_mm'] = current.get('precipitation')
                    weather_data['rain_mm'] = current.get('rain')
                    weather_data['snowfall_cm'] = current.get('snowfall')
                    
                    # Wind data
                    weather_data['wind_speed_kmh'] = current.get('windspeed_10m')
                    weather_data['wind_direction_degrees'] = current.get('winddirection_10m')
                    weather_data['wind_gusts_kmh'] = current.get('windgusts_10m')
                    
                    # Atmospheric data
                    weather_data['relative_humidity_percent'] = current.get('relativehumidity_2m')
                    weather_data['dewpoint_celsius'] = current.get('dewpoint_2m')
                    weather_data['pressure_hpa'] = current.get('pressure_msl')
                    weather_data['surface_pressure_hpa'] = current.get('surface_pressure')
                    
                    # Cloud and visibility
                    weather_data['cloud_cover_percent'] = current.get('cloudcover')
                    weather_data['visibility_m'] = current.get('visibility')
                    
                    # UV and weather code
                    weather_data['weather_code'] = current.get('weathercode')
                    weather_data['uv_index'] = current.get('uv_index')
                    
                    weather_data['timezone'] = data.get('timezone', 'UTC')
                    weather_data['current_time'] = current.get('time')
                    
                    # Decode weather code
                    weather_code = weather_data.get('weather_code')
                    if weather_code is not None:
                        weather_data['description'] = self._decode_weather_code(weather_code)
                    
                    # Add wind direction as compass point
                    wind_dir = weather_data.get('wind_direction_degrees')
                    if wind_dir is not None:
                        weather_data['wind_direction'] = self._get_wind_direction(wind_dir)
                        
            except requests.RequestException as e:
                logger.warning(f"Failed to get current weather data for lat={lat}, lon={lon}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error getting current weather data: {e}", exc_info=True)
        
        # Get air quality data
        try:
            if dt:
                date_str = dt.strftime('%Y-%m-%d')
                url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&hourly=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone,us_aqi&start_date={date_str}&end_date={date_str}"
            else:
                url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone,us_aqi"
            
            response = requests.get(url, timeout=settings.REQUEST_TIMEOUT_S)
            response.raise_for_status()
            aq_data = response.json()
            
            if dt and 'hourly' in aq_data:
                hour = dt.hour
                weather_data['air_quality'] = {
                    'aqi': aq_data['hourly']['us_aqi'][hour] if hour < len(aq_data['hourly']['us_aqi']) else None,
                    'pm2_5': aq_data['hourly']['pm2_5'][hour] if hour < len(aq_data['hourly']['pm2_5']) else None,
                    'pm10': aq_data['hourly']['pm10'][hour] if hour < len(aq_data['hourly']['pm10']) else None,
                    'ozone': aq_data['hourly']['ozone'][hour] if hour < len(aq_data['hourly']['ozone']) else None,
                }
            elif 'current' in aq_data:
                weather_data['air_quality'] = {
                    'aqi': aq_data['current'].get('us_aqi'),
                    'pm2_5': aq_data['current'].get('pm2_5'),
                    'pm10': aq_data['current'].get('pm10'),
                    'ozone': aq_data['current'].get('ozone'),
                }
            
            # Add AQI category
            aqi = weather_data.get('air_quality', {}).get('aqi')
            if aqi is not None:
                weather_data['air_quality']['category'] = self._get_aqi_category(aqi)
                    
        except requests.RequestException as e:
            logger.warning(f"Failed to get air quality data for lat={lat}, lon={lon}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting air quality data: {e}", exc_info=True)
        
        # Add UV index category
        uv_index = weather_data.get('uv_index')
        if uv_index is not None:
            weather_data['uv_category'] = self._get_uv_category(uv_index)
        
        return weather_data
    
    def calculate_moon_phase(self, lat: float, lon: float, dt: datetime) -> Dict[str, Any]:
        """Calculate moon phase and position for given location and time"""
        if not HAS_EPHEM:
            return {'available': False, 'reason': 'ephem not installed'}
        
        try:
            # Create observer
            observer = ephem.Observer()
            observer.lat = str(lat)
            observer.lon = str(lon)
            observer.date = dt
            
            # Create moon object
            moon = ephem.Moon(observer)
            
            # Calculate moon phase
            phase = moon.phase  # 0-100, where 0 is new moon, 100 is full moon
            
            # Determine phase name
            if phase < 1:
                phase_name = "New Moon"
            elif phase < 49:
                phase_name = "Waxing Crescent"
            elif phase < 51:
                phase_name = "First Quarter"
            elif phase < 99:
                phase_name = "Waxing Gibbous"
            elif phase < 101:
                phase_name = "Full Moon"
            elif phase < 149:
                phase_name = "Waning Gibbous"
            elif phase < 151:
                phase_name = "Last Quarter"
            else:
                phase_name = "Waning Crescent"
            
            # Calculate position
            altitude = float(moon.alt) * 180 / 3.14159  # Convert radians to degrees
            azimuth = float(moon.az) * 180 / 3.14159
            
            # Calculate rise and set times
            try:
                rise_time = observer.next_rising(moon)
                set_time = observer.next_setting(moon)
                
                return {
                    'available': True,
                    'phase': phase_name,
                    'illumination': round(phase, 1),
                    'position': {
                        'altitude': round(altitude, 1),
                        'azimuth': round(azimuth, 1)
                    },
                    'rise_time': str(rise_time),
                    'set_time': str(set_time)
                }
            except ephem.AlwaysUpError:
                return {
                    'available': True,
                    'phase': phase_name,
                    'illumination': round(phase, 1),
                    'position': {
                        'altitude': round(altitude, 1),
                        'azimuth': round(azimuth, 1)
                    },
                    'status': 'Always visible'
                }
            except ephem.NeverUpError:
                return {
                    'available': True,
                    'phase': phase_name,
                    'illumination': round(phase, 1),
                    'status': 'Not visible'
                }
                
        except Exception as e:
            return {
                'available': True,
                'error': str(e)
            }
    
    def _decode_weather_code(self, code: int) -> str:
        """Decode WMO weather code to description"""
        return self.weather_codes.get(code, "unknown")
    
    def _get_aqi_category(self, aqi: float) -> str:
        """Get AQI category from AQI value"""
        if aqi <= 50:
            return 'Good'
        elif aqi <= 100:
            return 'Moderate'
        elif aqi <= 150:
            return 'Unhealthy for Sensitive Groups'
        elif aqi <= 200:
            return 'Unhealthy'
        elif aqi <= 300:
            return 'Very Unhealthy'
        else:
            return 'Hazardous'
    
    def _get_uv_category(self, uv_index: float) -> str:
        """Get UV category from UV index value"""
        if uv_index < 3:
            return 'Low'
        elif uv_index < 6:
            return 'Moderate'
        elif uv_index < 8:
            return 'High'
        elif uv_index < 11:
            return 'Very High'
        else:
            return 'Extreme'
    
    def _get_wind_direction(self, degrees: float) -> str:
        """Convert wind direction in degrees to compass direction"""
        if degrees is None:
            return None
        
        # Normalize to 0-360
        degrees = degrees % 360
        
        # Define compass directions
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                     'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        
        # Calculate index (22.5 degrees per direction)
        index = round(degrees / 22.5) % 16
        
        return directions[index]
    
    # Note: Async versions removed as AsyncCoordinator in main.py already
    # handles running synchronous methods in the shared thread pool