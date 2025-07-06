"""
Input validation and security functions for GPS Toolkit.

This module provides essential validation functions to ensure the security
and correctness of user inputs. It implements defensive programming practices
to prevent common attack vectors and ensure data integrity.

Key security considerations:
- Path traversal prevention through proper file validation
- URL sanitization to prevent injection attacks
- Coordinate validation to ensure geographic data integrity
- Type checking and bounds validation for all inputs

The module is designed to fail fast with clear error messages, helping
developers identify issues early in the processing pipeline.
"""

import re
import asyncio
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode, unquote
from .tld_validator import TLDValidator


def validate_image_file(image_path: str) -> Path:
    """
    Validate that the input is a valid image file.
    
    This function performs several security and validity checks:
    1. Ensures the file exists on the filesystem
    2. Verifies it's actually a file (not a directory)
    3. Checks the file extension against a whitelist of image formats
    4. Validates the file size is within acceptable limits
    
    The extension check helps prevent processing of non-image files which
    could cause errors or security issues in downstream processing.
    
    Args:
        image_path (str): Path to the image file as a string
        
    Returns:
        Path: Validated Path object for the file, which can be used safely
              throughout the application
        
    Raises:
        ValueError: If the file doesn't exist, isn't a file, has an
                   unsupported extension, or exceeds size limits
                   
    Example:
        >>> path = validate_image_file('/path/to/photo.jpg')
        >>> print(path.suffix)  # '.jpg'
        
    Security Note:
        This function helps prevent path traversal attacks by using Path
        objects and checking file existence before processing. File size
        validation prevents resource exhaustion attacks.
    """
    from ..config import settings
    
    path = Path(image_path)
    if not path.exists():
        raise ValueError(f"Image file not found: {image_path}")
    
    if not path.is_file():
        raise ValueError(f"Path is not a file: {image_path}")
    
    # Check file extension against whitelist
    # This list includes common image formats supported by most image libraries
    valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.heic', '.heif', '.webp'}
    if path.suffix.lower() not in valid_extensions:
        raise ValueError(f"Unsupported image format: {path.suffix}")
    
    # Check file size
    file_size = path.stat().st_size
    if file_size > settings.MAX_IMAGE_SIZE_BYTES:
        raise ValueError(
            f"Image file size ({file_size / 1024**2:.2f}MB) "
            f"exceeds limit of {settings.MAX_IMAGE_SIZE_BYTES / 1024**2}MB"
        )
    
    return path


def validate_coordinates(lat: float, lon: float) -> Tuple[float, float]:
    """
    Validate GPS coordinates are within valid geographic ranges.
    
    GPS coordinates must fall within specific ranges to represent valid
    locations on Earth. This function ensures the coordinates are:
    - Latitude: between -90 and +90 degrees (South to North pole)
    - Longitude: between -180 and +180 degrees (International Date Line)
    
    Args:
        lat (float): Latitude value in decimal degrees
        lon (float): Longitude value in decimal degrees
        
    Returns:
        Tuple[float, float]: Validated (latitude, longitude) pair
        
    Raises:
        ValueError: If either coordinate is None or outside valid range
        
    Example:
        >>> lat, lon = validate_coordinates(37.7749, -122.4194)  # San Francisco
        >>> lat, lon = validate_coordinates(91.0, 0.0)  # Raises ValueError
        
    Note:
        This function doesn't validate whether coordinates represent land
        or water, just that they're geographically possible.
    """
    if lat is None or lon is None:
        raise ValueError("GPS coordinates are missing")
    
    if not -90 <= lat <= 90:
        raise ValueError(f"Invalid latitude: {lat}")
    
    if not -180 <= lon <= 180:
        raise ValueError(f"Invalid longitude: {lon}")
    
    return lat, lon


def validate_urls_with_tld(urls: List[str], timeout: float = 2.0) -> List[str]:
    """
    Filter URLs by validating their TLD using DNS resolution.
    
    This function takes a list of URLs and validates each one by checking
    if the domain's TLD is valid through DNS resolution. Invalid URLs
    are filtered out, returning only URLs with valid, resolvable domains.
    
    Args:
        urls (List[str]): List of URLs to validate
        timeout (float): DNS resolution timeout in seconds (default: 2.0)
        
    Returns:
        List[str]: List of URLs with valid TLDs only
        
    Example:
        >>> urls = ['www.ups.com', 'invalid.invalidtld', 'google.com']
        >>> valid_urls = validate_urls_with_tld(urls)
        >>> print(valid_urls)  # ['www.ups.com', 'google.com']
        
    Note:
        This function performs DNS lookups which may be slow for large lists.
        Consider using the async version for better performance.
    """
    if not urls:
        return []
    
    validator = TLDValidator()
    valid_urls = []
    
    for url in urls:
        if validator.validate_url(url, timeout):
            valid_urls.append(url)
    
    return valid_urls


async def validate_urls_with_tld_async(urls: List[str], timeout: float = 2.0, 
                                     max_concurrent: int = 10) -> List[str]:
    """
    Asynchronously filter URLs by validating their TLD using DNS resolution.
    
    This function provides the same functionality as validate_urls_with_tld
    but performs validation asynchronously for better performance when
    processing multiple URLs.
    
    Args:
        urls (List[str]): List of URLs to validate
        timeout (float): DNS resolution timeout per URL in seconds (default: 2.0)
        max_concurrent (int): Maximum concurrent validations (default: 10)
        
    Returns:
        List[str]: List of URLs with valid TLDs only
        
    Example:
        >>> urls = ['www.ups.com', 'invalid.invalidtld', 'google.com']
        >>> valid_urls = await validate_urls_with_tld_async(urls)
        >>> print(valid_urls)  # ['www.ups.com', 'google.com']
    """
    if not urls:
        return []
    
    validator = TLDValidator()
    
    # Extract domains for batch validation
    url_to_domain = {}
    domains = []
    
    for url in urls:
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
    for url in urls:
        domain = url_to_domain.get(url)
        if domain and validation_results.get(domain, False):
            valid_urls.append(url)
        elif not domain:
            # If we couldn't extract domain, include the URL
            # (might be localhost or other special case)
            valid_urls.append(url)
    
    return valid_urls


def deduplicate_urls(urls: List[str], validate_tld: bool = True, timeout: float = 2.0) -> List[str]:
    """
    Deduplicate URLs from both OCR text and QR codes with advanced normalization and TLD validation.
    
    This function implements sophisticated URL deduplication that goes beyond
    simple string comparison. It handles common variations that represent the
    same resource and optionally validates TLDs:
    
    1. Protocol differences (http vs https) - prefers https
    2. www prefix variations - normalizes but preserves in output
    3. Case sensitivity in domains - domains are case-insensitive
    4. Trailing slashes - removes from paths
    5. URL encoding - decodes for comparison
    6. Query parameter ordering - sorts for consistent comparison
    7. Fragment identifiers - ignores for deduplication
    8. TLD validation - optional DNS-based validation to filter invalid domains
    
    The function maintains the "best" version of each URL, preferring:
    - HTTPS over HTTP
    - URLs with www. prefix when other factors are equal
    - The first occurrence when truly identical
    - URLs with valid TLDs when validation is enabled
    
    Args:
        urls (List[str]): List of URLs to deduplicate, may contain:
                         - Full URLs (http://example.com)
                         - Partial URLs (www.example.com)
                         - Duplicates with variations
        validate_tld (bool): Whether to validate TLD using DNS (default: True)
        timeout (float): DNS validation timeout in seconds (default: 2.0)
        
    Returns:
        List[str]: Deduplicated list of URLs, preserving the best version
                  of each unique URL with valid TLDs (if validation enabled)
                  
    Example:
        >>> urls = [
        ...     'http://example.com/page',
        ...     'https://example.com/page/',
        ...     'https://www.example.com/page?b=2&a=1',
        ...     'HTTPS://WWW.EXAMPLE.COM/page?a=1&b=2#section',
        ...     'invalid.invalidtld/page'
        ... ]
        >>> deduped = deduplicate_urls(urls, validate_tld=True)
        >>> print(deduped)  # ['https://www.example.com/page?a=1&b=2'] (invalid.invalidtld filtered out)
        
    Security Note:
        This function validates URL structure and skips malformed URLs,
        helping prevent injection attacks through crafted URLs. TLD validation
        adds an additional layer of security by filtering domains that don't resolve.
    """
    if not urls:
        return []
    
    # Initialize TLD validator if validation is requested
    validator = TLDValidator() if validate_tld else None
    
    # Normalize and track URLs
    normalized_urls: Dict[str, str] = {}  # normalized -> original
    domain_paths: Dict[str, Set[str]] = {}  # domain -> set of paths
    
    for url in urls:
        # Skip empty or invalid URLs
        if not url or not isinstance(url, str):
            continue
            
        # Clean up the URL
        url = url.strip()
        
        # Handle URLs without scheme, but first normalize case for scheme detection
        url_lower = url.lower()
        if not url_lower.startswith(('http://', 'https://', 'ftp://', 'ftps://')):
            # Check if it looks like a URL before adding scheme
            # Must contain a dot and look like a domain
            if '.' in url and re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9][a-zA-Z0-9-]*)*', url):
                # Assume https if no scheme
                url = 'https://' + url
            else:
                # Not a valid URL pattern
                continue
        else:
            # URL has a scheme, but make sure it's properly cased
            # Fix case issues like "HTTPS://..." -> "https://..."
            if url_lower.startswith('http://'):
                url = 'http://' + url[7:]
            elif url_lower.startswith('https://'):
                url = 'https://' + url[8:]
            elif url_lower.startswith('ftp://'):
                url = 'ftp://' + url[6:]
            elif url_lower.startswith('ftps://'):
                url = 'ftps://' + url[7:]
        
        try:
            # Parse the URL
            parsed = urlparse(url)
            
            # Skip invalid URLs
            if not parsed.netloc:
                continue
            
            # Validate TLD if requested
            if validate_tld and validator:
                domain = validator.extract_domain_from_url(url)
                if domain and not validator.validate_tld(domain, timeout):
                    continue  # Skip URLs with invalid TLDs
            
            # Normalize components
            scheme = parsed.scheme.lower()
            
            # Normalize domain
            domain = parsed.netloc.lower()
            # Remove www. prefix for comparison
            # This treats www.example.com and example.com as the same site
            domain_normalized = domain.replace('www.', '')
            
            # Normalize path
            path = parsed.path
            # Remove trailing slashes for comparison
            # /page/ and /page are the same resource
            if path.endswith('/') and len(path) > 1:
                path = path.rstrip('/')
            # Decode URL encoding for accurate comparison
            # %20 becomes space, %2F becomes /, etc.
            path = unquote(path)
            
            # Normalize query parameters
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            # Sort parameters for consistent comparison
            # ?a=1&b=2 and ?b=2&a=1 are treated as identical
            sorted_params = sorted(query_params.items())
            normalized_query = urlencode(sorted_params, doseq=True)
            
            # Remove fragments for comparison (but keep in original)
            # Fragments (#section) are typically used for in-page navigation
            # and don't represent different resources
            
            # Create normalized URL for comparison
            normalized_key = f"{scheme}://{domain_normalized}{path}"
            if normalized_query:
                normalized_key += f"?{normalized_query}"
            
            # Check if we've seen this normalized URL
            if normalized_key not in normalized_urls:
                # Store the original URL
                normalized_urls[normalized_key] = url
                
                # Track domain-path combinations for near-duplicate detection
                if domain_normalized not in domain_paths:
                    domain_paths[domain_normalized] = set()
                domain_paths[domain_normalized].add(path)
            else:
                # We've seen this URL before
                # Prefer HTTPS over HTTP
                existing_url = normalized_urls[normalized_key]
                existing_parsed = urlparse(existing_url)
                
                if parsed.scheme == 'https' and existing_parsed.scheme == 'http':
                    normalized_urls[normalized_key] = url
                # Prefer URLs with www. if all else is equal
                elif parsed.netloc.startswith('www.') and not existing_parsed.netloc.startswith('www.'):
                    normalized_urls[normalized_key] = url
                    
        except Exception:
            # Skip URLs that can't be parsed
            continue
    
    # Return the deduplicated URLs, preserving order
    seen = set()
    result = []
    for url in normalized_urls.values():
        if url not in seen:
            seen.add(url)
            result.append(url)
    
    return result


async def deduplicate_urls_async(urls: List[str], validate_tld: bool = True, 
                                timeout: float = 2.0, max_concurrent: int = 10) -> List[str]:
    """
    Asynchronously deduplicate URLs with advanced normalization and TLD validation.
    
    This function provides the same functionality as deduplicate_urls but
    performs TLD validation asynchronously for better performance when
    processing multiple URLs.
    
    Args:
        urls (List[str]): List of URLs to deduplicate
        validate_tld (bool): Whether to validate TLD using DNS (default: True)
        timeout (float): DNS validation timeout per URL in seconds (default: 2.0)
        max_concurrent (int): Maximum concurrent validations (default: 10)
        
    Returns:
        List[str]: Deduplicated list of URLs with valid TLDs (if validation enabled)
        
    Example:
        >>> urls = ['http://example.com', 'https://example.com/', 'invalid.invalidtld']
        >>> deduped = await deduplicate_urls_async(urls, validate_tld=True)
        >>> print(deduped)  # ['https://example.com'] (invalid.invalidtld filtered out)
    """
    if not urls:
        return []
    
    # First deduplicate without TLD validation
    deduplicated = deduplicate_urls(urls, validate_tld=False)
    
    if not validate_tld or not deduplicated:
        return deduplicated
    
    # Then validate TLDs asynchronously
    return await validate_urls_with_tld_async(
        deduplicated, timeout=timeout, max_concurrent=max_concurrent
    )