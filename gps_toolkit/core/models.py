"""Data models and classes for GPS Toolkit"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class Coordinates:
    """GPS coordinates"""
    lat: float
    lon: float
    
    def to_dict(self) -> Dict[str, float]:
        return {'lat': self.lat, 'lon': self.lon}


@dataclass
class Address:
    """Physical address information"""
    street: Optional[str] = None
    house_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, str]:
        result = {}
        if self.street:
            result['street'] = self.street
        if self.house_number:
            result['house_number'] = self.house_number
        if self.postal_code:
            result['postal_code'] = self.postal_code
        if self.city:
            result['city'] = self.city
        if self.state:
            result['state'] = self.state
        if self.country:
            result['country'] = self.country
        if self.country_code:
            result['country_code'] = self.country_code
        return result


@dataclass
class CameraInfo:
    """Camera and lens information"""
    make: str = 'Unknown'
    model: str = 'Unknown'
    lens_model: str = 'Unknown'
    software: str = 'Unknown'
    
    def to_dict(self) -> Dict[str, str]:
        return {
            'make': self.make,
            'model': self.model,
            'lens_model': self.lens_model,
            'software': self.software
        }


@dataclass
class ExposureSettings:
    """Camera exposure settings"""
    exposure_time: str = 'Unknown'
    f_number: str = 'Unknown'
    iso: str = 'Unknown'
    focal_length: str = 'Unknown'
    flash: str = 'Unknown'
    exposure_mode: str = 'Unknown'
    white_balance: str = 'Unknown'
    metering_mode: str = 'Unknown'
    exposure_program: str = 'Unknown'
    
    def to_dict(self) -> Dict[str, str]:
        return {
            'exposure_time': self.exposure_time,
            'f_number': self.f_number,
            'iso': self.iso,
            'focal_length': self.focal_length,
            'flash': self.flash,
            'exposure_mode': self.exposure_mode,
            'white_balance': self.white_balance,
            'metering_mode': self.metering_mode,
            'exposure_program': self.exposure_program
        }


@dataclass
class WeatherData:
    """Weather information"""
    temperature_c: Optional[float] = None
    description: Optional[str] = None
    humidity: Optional[int] = None
    wind_speed_kmh: Optional[float] = None
    wind_direction: Optional[str] = None
    precipitation_mm: Optional[float] = None
    visibility_km: Optional[float] = None
    pressure_hpa: Optional[float] = None
    uv_index: Optional[float] = None
    moon_phase: Optional[str] = None
    moon_illumination: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.temperature_c is not None:
            result['temperature_c'] = self.temperature_c
        if self.description:
            result['description'] = self.description
        if self.humidity is not None:
            result['humidity'] = self.humidity
        if self.wind_speed_kmh is not None:
            result['wind_speed_kmh'] = self.wind_speed_kmh
        if self.wind_direction:
            result['wind_direction'] = self.wind_direction
        if self.precipitation_mm is not None:
            result['precipitation_mm'] = self.precipitation_mm
        if self.visibility_km is not None:
            result['visibility_km'] = self.visibility_km
        if self.pressure_hpa is not None:
            result['pressure_hpa'] = self.pressure_hpa
        if self.uv_index is not None:
            result['uv_index'] = self.uv_index
        if self.moon_phase:
            result['moon_phase'] = self.moon_phase
        if self.moon_illumination is not None:
            result['moon_illumination'] = self.moon_illumination
        return result


@dataclass
class AirQuality:
    """Air quality information"""
    aqi: Optional[int] = None
    category: Optional[str] = None
    pm2_5: Optional[float] = None
    pm10: Optional[float] = None
    ozone: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.aqi is not None:
            result['aqi'] = self.aqi
        if self.category:
            result['category'] = self.category
        if self.pm2_5 is not None:
            result['pm2_5'] = self.pm2_5
        if self.pm10 is not None:
            result['pm10'] = self.pm10
        if self.ozone is not None:
            result['ozone'] = self.ozone
        return result


@dataclass
class QRCode:
    """QR code information"""
    data: str
    type: str
    position: Optional[Tuple[int, int, int, int]] = None  # x, y, width, height
    
    def to_dict(self) -> Dict[str, Any]:
        result = {'data': self.data, 'type': self.type}
        if self.position:
            result['position'] = {
                'x': self.position[0],
                'y': self.position[1],
                'width': self.position[2],
                'height': self.position[3]
            }
        return result


@dataclass
class Face:
    """Face detection information"""
    position: Tuple[int, int, int, int]  # top, right, bottom, left
    
    def to_dict(self) -> Dict[str, int]:
        return {
            'top': self.position[0],
            'right': self.position[1],
            'bottom': self.position[2],
            'left': self.position[3]
        }


@dataclass
class Color:
    """Color information"""
    hex: str
    name: str
    percentage: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'hex': self.hex,
            'name': self.name,
            'percentage': self.percentage
        }