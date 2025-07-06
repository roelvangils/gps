"""
TLD Validator - Robust Top-Level Domain validation service for GPS toolkit.

This module provides comprehensive domain validation including DNS-based TLD validation,
format checking, and URL parsing with caching and error handling.
"""

import re
import socket
import time
import asyncio
import urllib.parse
from typing import Dict, List, Optional, Tuple
from threading import Lock
from collections import defaultdict
import logging


def sanitize_url_for_logging(url: str) -> str:
    """
    Sanitize URL by removing credentials before logging.
    
    Args:
        url (str): URL that may contain credentials
        
    Returns:
        str: Sanitized URL safe for logging
        
    Examples:
        >>> sanitize_url_for_logging("https://user:pass@example.com/path")
        'https://[REDACTED]@example.com/path'
        >>> sanitize_url_for_logging("https://example.com/path")
        'https://example.com/path'
    """
    if not url or not isinstance(url, str):
        return str(url)
    
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.username or parsed.password:
            # Replace credentials with [REDACTED]
            netloc = parsed.hostname or ''
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            
            # Reconstruct URL without credentials
            sanitized = urllib.parse.urlunparse((
                parsed.scheme,
                f"[REDACTED]@{netloc}" if netloc else "[REDACTED]",
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
            return sanitized
    except Exception:
        # If parsing fails, check for basic patterns
        if '@' in url:
            # Simple pattern match for user:pass@domain
            parts = url.split('@', 1)
            if len(parts) == 2:
                scheme_part = parts[0].split('://', 1)
                if len(scheme_part) == 2:
                    return f"{scheme_part[0]}://[REDACTED]@{parts[1]}"
                else:
                    return f"[REDACTED]@{parts[1]}"
    
    return url


class TLDValidator:
    """
    A robust TLD validation service that provides DNS-based validation,
    format checking, and URL parsing with caching and performance optimization.
    """
    
    def __init__(self, cache_ttl: int = 300, max_cache_size: int = 1000):
        """
        Initialize the TLD validator with configurable caching.
        
        Args:
            cache_ttl (int): Time-to-live for cached results in seconds (default: 300)
            max_cache_size (int): Maximum number of cached entries (default: 1000)
        """
        self.cache_ttl = cache_ttl
        self.max_cache_size = max_cache_size
        self._cache: Dict[str, Tuple[bool, float]] = {}
        self._cache_lock = Lock()
        self._logger = logging.getLogger(__name__)
        
        # Common TLDs for fast validation (no DNS lookup needed)
        self.common_tlds = {
            'com', 'org', 'net', 'edu', 'gov', 'mil', 'int',
            'co', 'uk', 'ca', 'au', 'de', 'fr', 'jp', 'cn',
            'ru', 'br', 'in', 'it', 'es', 'mx', 'nl', 'pl',
            'tr', 'se', 'no', 'dk', 'fi', 'ch', 'at', 'be',
            'ie', 'pt', 'gr', 'cz', 'hu', 'ro', 'bg', 'hr',
            'si', 'sk', 'lt', 'lv', 'ee', 'is', 'mt', 'cy',
            'lu', 'li', 'ad', 'mc', 'sm', 'va', 'io', 'ly',
            'me', 'tv', 'cc', 'ws', 'tk', 'ml', 'ga', 'cf'
        }
        
        # Domain name pattern for basic format validation
        # Requires at least one dot (TLD separator)
        self.domain_pattern = re.compile(
            r'^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
            r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$'
        )
    
    def _cleanup_cache(self) -> None:
        """Remove expired entries from cache and enforce size limits."""
        current_time = time.time()
        expired_keys = []
        
        for domain, (result, timestamp) in self._cache.items():
            if current_time - timestamp > self.cache_ttl:
                expired_keys.append(domain)
        
        for key in expired_keys:
            del self._cache[key]
        
        # Enforce size limit by removing oldest entries
        if len(self._cache) > self.max_cache_size:
            sorted_items = sorted(
                self._cache.items(),
                key=lambda x: x[1][1]  # Sort by timestamp
            )
            items_to_remove = len(self._cache) - self.max_cache_size
            for i in range(items_to_remove):
                del self._cache[sorted_items[i][0]]
    
    def _get_cached_result(self, domain: str) -> Optional[bool]:
        """Get cached validation result if available and not expired."""
        with self._cache_lock:
            if domain in self._cache:
                result, timestamp = self._cache[domain]
                if time.time() - timestamp <= self.cache_ttl:
                    return result
                else:
                    del self._cache[domain]
            return None
    
    def _cache_result(self, domain: str, result: bool) -> None:
        """Cache validation result with timestamp."""
        with self._cache_lock:
            self._cache[domain] = (result, time.time())
            if len(self._cache) > self.max_cache_size:
                self._cleanup_cache()
    
    def is_valid_domain_format(self, domain: str) -> bool:
        """
        Validate domain format using regex pattern.
        
        Args:
            domain (str): Domain name to validate
            
        Returns:
            bool: True if domain format is valid, False otherwise
            
        Examples:
            >>> validator = TLDValidator()
            >>> validator.is_valid_domain_format("example.com")
            True
            >>> validator.is_valid_domain_format("invalid..domain")
            False
        """
        if not domain or not isinstance(domain, str) or len(domain) > 253:
            return False
        
        # Strip whitespace
        domain = domain.strip()
        if not domain:
            return False
        
        # Handle IDN domains
        try:
            # Try to encode as ASCII first
            domain.encode('ascii')
            domain_to_check = domain
        except UnicodeEncodeError:
            try:
                # Convert IDN to ASCII
                domain_to_check = domain.encode('idna').decode('ascii')
            except (UnicodeError, UnicodeDecodeError):
                return False
        
        # Check against regex pattern
        return bool(self.domain_pattern.match(domain_to_check))
    
    def extract_domain_from_url(self, url: str) -> Optional[str]:
        """
        Extract domain name from a full URL.
        
        Args:
            url (str): Full URL to parse
            
        Returns:
            Optional[str]: Domain name if successfully extracted, None otherwise
            
        Examples:
            >>> validator = TLDValidator()
            >>> validator.extract_domain_from_url("https://www.example.com/path")
            'www.example.com'
            >>> validator.extract_domain_from_url("invalid-url")
            None
        """
        if not url or not isinstance(url, str):
            self._logger.debug(f"Invalid URL input: {repr(url)}")
            return None
        
        url = url.strip()
        if not url:
            return None
        
        try:
            # Check if it looks like a simple domain without protocol
            if '://' not in url and '.' in url and ' ' not in url:
                # Try to parse as a simple domain first
                parsed = urllib.parse.urlparse(f'http://{url}')
            else:
                # Add protocol if missing but looks like a URL
                if not url.startswith(('http://', 'https://', 'ftp://')):
                    # Check if it could be a valid domain by looking for dots and no spaces
                    if '.' in url and ' ' not in url and not url.startswith('/'):
                        url = 'http://' + url
                    else:
                        return None
                parsed = urllib.parse.urlparse(url)
            
            domain = parsed.netloc
            if not domain:
                return None
            
            # Handle IPv6 addresses
            if domain.startswith('[') and ']' in domain:
                # Extract IPv6 address including brackets
                bracket_end = domain.find(']')
                if bracket_end != -1:
                    ipv6_part = domain[:bracket_end + 1]
                    return ipv6_part
            
            # Remove username/password if present (format: user:pass@domain)
            if '@' in domain:
                domain = domain.split('@')[-1]
            
            # Remove port number if present
            if ':' in domain and not domain.startswith('['):
                domain = domain.split(':')[0]
            
            return domain if domain else None
            
        except Exception as e:
            self._logger.debug(f"Failed to extract domain from URL '{sanitize_url_for_logging(url)}': {e}")
            return None
    
    def validate_tld(self, domain: str, timeout: float = 2.0) -> bool:
        """
        Validate TLD using DNS resolution with caching.
        
        Args:
            domain (str): Domain name to validate
            timeout (float): DNS resolution timeout in seconds (default: 2.0)
            
        Returns:
            bool: True if TLD is valid (DNS resolution successful), False otherwise
            
        Examples:
            >>> validator = TLDValidator()
            >>> validator.validate_tld("example.com")
            True
            >>> validator.validate_tld("invalid.invalidtld")
            False
        """
        if not domain or not isinstance(domain, str):
            return False
        
        # Convert to lowercase for consistency
        domain = domain.lower().strip()
        if not domain:
            return False
        
        # Check format first
        if not self.is_valid_domain_format(domain):
            return False
        
        # Check cache first
        cached_result = self._get_cached_result(domain)
        if cached_result is not None:
            return cached_result
        
        # Extract TLD
        tld = domain.split('.')[-1]
        
        # Fast validation for common TLDs
        if tld in self.common_tlds:
            self._cache_result(domain, True)
            return True
        
        # DNS-based validation with thread-safe timeout
        try:
            # Use asyncio with timeout for thread-safe DNS resolution
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self._validate_domain_with_timeout(domain, timeout)
                )
            finally:
                loop.close()
            
        except Exception as e:
            self._logger.debug(f"DNS resolution failed for domain: {e}")
            result = False
        
        # Cache the result
        self._cache_result(domain, result)
        return result
    
    async def _validate_domain_with_timeout(self, domain: str, timeout: float) -> bool:
        """
        Validate domain with proper timeout using asyncio.
        
        Args:
            domain (str): Domain to validate
            timeout (float): Timeout in seconds
            
        Returns:
            bool: True if domain resolves, False otherwise
        """
        try:
            loop = asyncio.get_event_loop()
            # Run DNS resolution in executor with timeout
            result = await asyncio.wait_for(
                loop.run_in_executor(None, socket.getaddrinfo, domain, None),
                timeout=timeout
            )
            return True
        except (asyncio.TimeoutError, socket.gaierror, OSError):
            return False
    
    async def _validate_domain_async(self, domain: str, timeout: float = 2.0) -> Tuple[str, bool]:
        """
        Async wrapper for domain validation.
        
        Args:
            domain (str): Domain to validate
            timeout (float): Validation timeout
            
        Returns:
            Tuple[str, bool]: Domain name and validation result
        """
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, 
                lambda: self.validate_tld(domain, timeout)
            )
            return domain, result
        except Exception as e:
            self._logger.debug(f"Async validation failed for domain: {e}")
            return domain, False
    
    async def batch_validate_domains(self, domains: List[str], timeout: float = 2.0, 
                                   max_concurrent: int = 10) -> Dict[str, bool]:
        """
        Validate multiple domains asynchronously with concurrency control.
        
        Args:
            domains (List[str]): List of domains to validate
            timeout (float): Validation timeout per domain in seconds (default: 2.0)
            max_concurrent (int): Maximum concurrent validations (default: 10)
            
        Returns:
            Dict[str, bool]: Dictionary mapping domains to validation results
            
        Examples:
            >>> validator = TLDValidator()
            >>> import asyncio
            >>> domains = ["example.com", "google.com", "invalid.invalidtld"]
            >>> results = asyncio.run(validator.batch_validate_domains(domains))
            >>> print(results)
            {'example.com': True, 'google.com': True, 'invalid.invalidtld': False}
        """
        if not domains:
            return {}
        
        # Remove duplicates while preserving order
        unique_domains = list(dict.fromkeys(domains))
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def validate_with_semaphore(domain: str) -> Tuple[str, bool]:
            async with semaphore:
                return await self._validate_domain_async(domain, timeout)
        
        # Execute validations concurrently
        tasks = [validate_with_semaphore(domain) for domain in unique_domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        validation_results = {}
        for result in results:
            if isinstance(result, Exception):
                self._logger.error(f"Batch validation error: {result}")
                continue
            
            domain, is_valid = result
            validation_results[domain] = is_valid
        
        return validation_results
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.
        
        Returns:
            Dict[str, int]: Cache statistics including size and hit rate
        """
        with self._cache_lock:
            return {
                'cache_size': len(self._cache),
                'max_cache_size': self.max_cache_size,
                'cache_ttl': self.cache_ttl
            }
    
    def clear_cache(self) -> None:
        """Clear all cached validation results."""
        with self._cache_lock:
            self._cache.clear()
    
    def validate_url(self, url: str, timeout: float = 2.0) -> bool:
        """
        Validate a complete URL by extracting and validating its domain.
        
        Args:
            url (str): URL to validate
            timeout (float): Validation timeout in seconds (default: 2.0)
            
        Returns:
            bool: True if URL has valid domain, False otherwise
            
        Examples:
            >>> validator = TLDValidator()
            >>> validator.validate_url("https://example.com/path")
            True
            >>> validator.validate_url("https://invalid.invalidtld")
            False
        """
        domain = self.extract_domain_from_url(url)
        if not domain:
            return False
        
        return self.validate_tld(domain, timeout)


# Convenience function for simple validation
def validate_domain(domain: str, timeout: float = 2.0) -> bool:
    """
    Convenience function for validating a single domain.
    
    Args:
        domain (str): Domain to validate
        timeout (float): Validation timeout in seconds (default: 2.0)
        
    Returns:
        bool: True if domain is valid, False otherwise
    """
    validator = TLDValidator()
    return validator.validate_tld(domain, timeout)


def validate_url(url: str, timeout: float = 2.0) -> bool:
    """
    Convenience function for validating a single URL.
    
    Args:
        url (str): URL to validate
        timeout (float): Validation timeout in seconds (default: 2.0)
        
    Returns:
        bool: True if URL has valid domain, False otherwise
    """
    validator = TLDValidator()
    return validator.validate_url(url, timeout)