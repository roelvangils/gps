"""Utility functions for GPS Toolkit"""

import re
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from .tld_validator import TLDValidator


def format_focal_length(focal_length: str) -> str:
    """Format focal length to remove unnecessary decimals"""
    if not focal_length or focal_length == 'Unknown':
        return focal_length
    
    # Extract numeric value
    match = re.match(r'([\d.]+)mm', focal_length)
    if match:
        value = float(match.group(1))
        # Format to remove unnecessary decimals
        if value.is_integer():
            return f"{int(value)}mm"
        else:
            # Round to 1 decimal place if needed
            return f"{value:.1f}mm".rstrip('0').rstrip('.') + "mm"
    return focal_length


def format_date(datetime_info: Dict[str, Any]) -> Optional[str]:
    """Format datetime info to human-readable date"""
    try:
        # Check if we have a timestamp
        if 'timestamp' in datetime_info:
            # Parse ISO format timestamp
            dt = datetime.fromisoformat(datetime_info['timestamp'])
            return dt.strftime('%B %d, %Y')
        elif 'local_time' in datetime_info:
            # Try to parse from local_time if it includes date
            # This is just time, so we can't get the date from it
            return None
    except:
        return None


def remove_empty_values(obj: Union[Dict, List, Any]) -> Optional[Union[Dict, List, Any]]:
    """Recursively remove None, empty strings, empty lists, and empty dicts from a nested structure"""
    if isinstance(obj, dict):
        # Create new dict with only non-empty values
        result = {}
        for k, v in obj.items():
            cleaned = remove_empty_values(v)
            # Only add if the value is not None, empty string, empty list, or empty dict
            if cleaned is not None and cleaned != "" and cleaned != [] and cleaned != {}:
                result[k] = cleaned
        return result if result else None
    elif isinstance(obj, list):
        # Filter out empty values from lists
        result = [remove_empty_values(item) for item in obj]
        result = [item for item in result if item is not None and item != "" and item != [] and item != {}]
        return result if result else None
    else:
        # Return the value as-is if it's not a dict or list
        return obj


def extract_urls_from_text(text: str, validate_tld: bool = True, timeout: float = 2.0) -> List[str]:
    """
    Extract URLs from text using enhanced regex patterns and TLD validation.
    
    This function implements sophisticated URL extraction with false positive reduction:
    - Filters out obvious false positives (single letters, abbreviations)
    - Validates domain structure and minimum length requirements
    - Optionally validates TLD using DNS resolution
    - Handles various URL formats including scheme-less URLs
    
    Args:
        text (str): Text to extract URLs from
        validate_tld (bool): Whether to validate TLD using DNS (default: True)
        timeout (float): DNS validation timeout in seconds (default: 2.0)
        
    Returns:
        List[str]: List of validated URLs
        
    Examples:
        >>> extract_urls_from_text("Visit www.ups.com for shipping")
        ['www.ups.com']
        >>> extract_urls_from_text("Text with zij.n and C.O.D abbreviations") 
        []  # Filters out false positives
    """
    if not text:
        return []
    
    # Enhanced URL regex pattern with stricter requirements
    url_pattern = re.compile(
        r'(?:'
        r'(?:https?)://'  # Explicit scheme - only http and https allowed
        r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*'  # Subdomains
        r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'  # Domain
        r'(?::[0-9]{1,5})?'  # Optional port
        r'(?:/[^\s]*)?'  # Optional path
        r'|'  # OR
        r'(?:www\.)?'  # Optional www prefix
        r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'  # Domain part
        r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*'  # Subdomains
        r'\.[a-zA-Z]{2,}'  # TLD (minimum 2 characters)
        r'(?::[0-9]{1,5})?'  # Optional port
        r'(?:/[^\s]*)?'  # Optional path
        r')',
        re.IGNORECASE
    )
    
    # Common false positive patterns to exclude
    false_positive_patterns = [
        r'^[a-zA-Z]\.n$',  # Single letter followed by .n (like "zij.n")
        r'^[A-Z]\.O\.D$',  # Abbreviations like "C.O.D"
        r'^[a-zA-Z]{1,2}\.[a-zA-Z]{1,2}$',  # Very short letter combinations
        r'^\d+\.\d+$',  # Numbers like "3.14"
        r'^[a-zA-Z]\.?[a-zA-Z]\.?[a-zA-Z]?$',  # Initials like "J.R.R"
        r'^etc\.',  # "etc." pattern
        r'^vs\.',   # "vs." pattern
        r'^mr\.',   # "mr." pattern
        r'^mrs\.',  # "mrs." pattern
        r'^dr\.',   # "dr." pattern
        r'^inc\.',  # "inc." pattern
        r'^ltd\.',  # "ltd." pattern
        r'^co\.',   # "co." pattern
        # File extensions (common file types that aren't domains)
        r'^.+\.(pdf|doc|docx|xls|xlsx|ppt|pptx|txt|rtf|odt|ods|odp)$',  # Office files
        r'^.+\.(jpg|jpeg|png|gif|bmp|tiff|svg|webp|ico)$',  # Image files
        r'^.+\.(mp3|mp4|avi|mov|wmv|flv|wav|aac|ogg)$',  # Media files
        r'^.+\.(zip|rar|tar|gz|7z|bz2)$',  # Archive files
        r'^.+\.(exe|msi|dmg|pkg|deb|rpm)$',  # Executable files
    ]
    
    urls = []
    validator = TLDValidator() if validate_tld else None
    
    for match in url_pattern.finditer(text):
        url = match.group(0).strip()
        
        # Skip empty matches
        if not url:
            continue
        
        # Check for false positive patterns
        is_false_positive = any(
            re.match(pattern, url, re.IGNORECASE) 
            for pattern in false_positive_patterns
        )
        if is_false_positive:
            continue
        
        # Require minimum domain length (excluding TLD)
        if not url.startswith(('http://', 'https://', 'ftp://', 'ftps://')):
            # For scheme-less URLs, check domain length
            domain_part = url.split('/')[0].split(':')[0]  # Remove path and port
            if domain_part.startswith('www.'):
                domain_part = domain_part[4:]
            
            # Split by dots and check main domain length
            parts = domain_part.split('.')
            if len(parts) < 2:  # Must have at least domain.tld
                continue
                
            # Check if main domain part is too short
            main_domain = parts[-2] if len(parts) >= 2 else parts[0]
            if len(main_domain) < 2:  # Minimum 2 characters for domain
                continue
        
        # Validate TLD if requested
        if validate_tld and validator:
            if not validator.validate_url(url, timeout):
                continue
        
        urls.append(url)
    
    return urls


async def extract_urls_from_text_async(text: str, validate_tld: bool = True, 
                                     timeout: float = 2.0, max_concurrent: int = 10) -> List[str]:
    """
    Asynchronously extract URLs from text with TLD validation.
    
    This function provides the same functionality as extract_urls_from_text but
    performs TLD validation asynchronously for better performance when processing
    multiple URLs.
    
    Args:
        text (str): Text to extract URLs from
        validate_tld (bool): Whether to validate TLD using DNS (default: True)
        timeout (float): DNS validation timeout per URL in seconds (default: 2.0)
        max_concurrent (int): Maximum concurrent validations (default: 10)
        
    Returns:
        List[str]: List of validated URLs
        
    Examples:
        >>> urls = await extract_urls_from_text_async("Visit www.ups.com")
        >>> print(urls)
        ['www.ups.com']
    """
    if not text:
        return []
    
    # First extract URLs without TLD validation
    candidate_urls = extract_urls_from_text(text, validate_tld=False)
    
    if not candidate_urls or not validate_tld:
        return candidate_urls
    
    # Validate TLDs asynchronously
    validator = TLDValidator()
    
    # Extract domains for batch validation
    domains = []
    url_to_domain = {}
    
    for url in candidate_urls:
        domain = validator.extract_domain_from_url(url)
        if domain:
            domains.append(domain)
            url_to_domain[url] = domain
    
    # Batch validate domains
    validation_results = await validator.batch_validate_domains(
        domains, timeout=timeout, max_concurrent=max_concurrent
    )
    
    # Filter URLs based on validation results
    valid_urls = []
    for url in candidate_urls:
        domain = url_to_domain.get(url)
        if domain and validation_results.get(domain, False):
            valid_urls.append(url)
        elif not domain:
            # If we couldn't extract domain, include the URL
            # (might be localhost or other special case)
            valid_urls.append(url)
    
    return valid_urls


def get_season(month: int, hemisphere: str = 'northern') -> str:
    """
    Get season name based on month.
    
    Args:
        month (int): Month number (1-12)
        hemisphere (str): 'northern' or 'southern' hemisphere
        
    Returns:
        str: Season name
    """
    if hemisphere == 'northern':
        if month in [12, 1, 2]:
            return 'Winter'
        elif month in [3, 4, 5]:
            return 'Spring'
        elif month in [6, 7, 8]:
            return 'Summer'
        else:  # 9, 10, 11
            return 'Fall'
    else:  # southern hemisphere
        if month in [12, 1, 2]:
            return 'Summer'
        elif month in [3, 4, 5]:
            return 'Fall'
        elif month in [6, 7, 8]:
            return 'Winter'
        else:  # 9, 10, 11
            return 'Spring'


def parse_exif_datetime(date_string: str) -> Optional[Dict[str, Any]]:
    """Parse datetime from EXIF data into simplified format"""
    if not date_string:
        return None
    
    # Common EXIF datetime formats
    formats = [
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ"
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_string, fmt)
            
            # Format date as "Month Day, Year"
            formatted_date = dt.strftime('%B %-d, %Y')  # %-d removes leading zeros on Unix/Mac
            # Fallback for Windows which doesn't support %-d
            if '%-d' in formatted_date:
                formatted_date = dt.strftime('%B %d, %Y').replace(' 0', ' ')
            
            return {
                'date': formatted_date,
                'time': dt.strftime('%H:%M:%S'),
                'weekday': dt.strftime('%A'),
                'season': get_season(dt.month),
                # Keep timestamp for internal use but it will be removed in formatting
                'timestamp': dt.isoformat()
            }
        except ValueError:
            continue
    
    return None


def parse_distance(distance_str: str) -> float:
    """
    Parse a distance string to meters.
    
    Accepts formats like:
    - "50" -> 50.0 meters
    - "50m" -> 50.0 meters  
    - "0.5km" -> 500.0 meters
    - "1.5km" -> 1500.0 meters
    
    Args:
        distance_str (str): Distance string to parse
        
    Returns:
        float: Distance in meters
        
    Raises:
        ValueError: If the distance string is invalid
        
    Examples:
        >>> parse_distance("50")
        50.0
        >>> parse_distance("100m")
        100.0
        >>> parse_distance("0.5km")
        500.0
        >>> parse_distance("invalid")
        ValueError: Invalid distance format: 'invalid'
    """
    distance_str = distance_str.strip().lower()
    
    try:
        # Check for units
        if distance_str.endswith('km'):
            return float(distance_str[:-2]) * 1000
        elif distance_str.endswith('m'):
            return float(distance_str[:-1])
        else:
            # Assume meters if no unit specified
            return float(distance_str)
    except ValueError:
        raise ValueError(f"Invalid distance format: '{distance_str}'")
    except Exception as e:
        raise ValueError(f"Error parsing distance '{distance_str}': {e}")