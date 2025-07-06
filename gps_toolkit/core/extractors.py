"""EXIF data extraction functionality for GPS Toolkit"""

import json
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path

from .utils import parse_exif_datetime


class ExifExtractor:
    """Extract EXIF data from images"""
    
    @staticmethod
    def extract_exif_data(image_path: Path) -> Dict[str, Any]:
        """Extract comprehensive EXIF data including camera information"""
        try:
            # Use exiftool to extract comprehensive EXIF data
            result = subprocess.run(
                ['exiftool', '-j', '-n', '-gpslatitude', '-gpslongitude', '-DateTimeOriginal',
                 '-Make', '-Model', '-LensModel', '-ExposureTime', '-FNumber', '-ISO',
                 '-FocalLength', '-Flash', '-Software', '-LensID', '-ExposureMode',
                 '-WhiteBalance', '-MeteringMode', '-ExposureProgram', '--', str(image_path)],
                capture_output=True,
                text=True,
                check=True
            )
            
            exif_data = json.loads(result.stdout)[0]
            
            lat = exif_data.get('GPSLatitude')
            lon = exif_data.get('GPSLongitude')
            date_time = exif_data.get('DateTimeOriginal')
            
            # Always compile camera information (available even without GPS)
            camera_info = {
                'make': exif_data.get('Make', 'Unknown'),
                'model': exif_data.get('Model', 'Unknown'),
                'lens_model': exif_data.get('LensModel') or exif_data.get('LensID', 'Unknown'),
                'software': exif_data.get('Software', 'Unknown')
            }
            
            # Always compile exposure settings (available even without GPS)
            exposure_settings = {
                'exposure_time': ExifExtractor._format_exposure_time(exif_data.get('ExposureTime')),
                'f_number': f"f/{exif_data.get('FNumber')}" if exif_data.get('FNumber') else 'Unknown',
                'iso': exif_data.get('ISO', 'Unknown'),
                'focal_length': f"{exif_data.get('FocalLength')}mm" if exif_data.get('FocalLength') else 'Unknown',
                'flash': ExifExtractor._decode_flash(exif_data.get('Flash')),
                'exposure_mode': exif_data.get('ExposureMode', 'Unknown'),
                'white_balance': exif_data.get('WhiteBalance', 'Unknown'),
                'metering_mode': exif_data.get('MeteringMode', 'Unknown'),
                'exposure_program': exif_data.get('ExposureProgram', 'Unknown')
            }
            
            # Parse datetime if available
            datetime_info = None
            if date_time:
                datetime_info = parse_exif_datetime(date_time)
            
            # Return data structure - GPS coordinates may be None
            result = {
                'lat': lat,
                'lon': lon,
                'has_gps': bool(lat and lon),
                'datetime': datetime_info,
                'datetime_raw': date_time,
                'camera_info': camera_info,
                'exposure_settings': exposure_settings
            }
            
            return result
            
        except subprocess.CalledProcessError:
            raise RuntimeError("exiftool not found. Please install it first.")
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            raise ValueError(f"Failed to parse EXIF data: {e}")
    
    @staticmethod
    def _format_exposure_time(exposure_time: Optional[float]) -> str:
        """Format exposure time as a fraction"""
        if not exposure_time:
            return 'Unknown'
        
        if exposure_time >= 1:
            return f"{exposure_time}s"
        else:
            # Convert to fraction
            denominator = int(1 / exposure_time)
            return f"1/{denominator}s"
    
    @staticmethod
    def _decode_flash(flash_value: Optional[Any]) -> str:
        """Decode flash value from EXIF"""
        if flash_value is None:
            return 'Unknown'
        
        try:
            flash_int = int(flash_value)
            if flash_int & 1:
                return 'Flash fired'
            else:
                return 'Flash did not fire'
        except (TypeError, ValueError):
            return str(flash_value)