"""IP Address Validation for SSRF Protection

This module provides comprehensive IP address validation to prevent Server-Side Request Forgery (SSRF)
attacks by blocking requests to internal networks, loopback addresses, and other potentially dangerous IPs.
"""

import ipaddress
import socket
import logging
from typing import Union, Optional, Tuple, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class IPValidator:
    """Validates IP addresses to prevent SSRF attacks"""
    
    # Define private/internal IP ranges according to RFC standards
    PRIVATE_IP_RANGES = [
        # IPv4 private ranges
        ipaddress.ip_network('10.0.0.0/8'),         # Class A private
        ipaddress.ip_network('172.16.0.0/12'),      # Class B private
        ipaddress.ip_network('192.168.0.0/16'),     # Class C private
        ipaddress.ip_network('127.0.0.0/8'),        # Loopback
        ipaddress.ip_network('169.254.0.0/16'),     # Link-local
        ipaddress.ip_network('0.0.0.0/8'),          # This network
        ipaddress.ip_network('100.64.0.0/10'),      # Shared address space
        ipaddress.ip_network('192.0.0.0/24'),       # IANA IPv4 Special Purpose
        ipaddress.ip_network('192.0.2.0/24'),       # TEST-NET-1
        ipaddress.ip_network('198.18.0.0/15'),      # Benchmarking
        ipaddress.ip_network('198.51.100.0/24'),    # TEST-NET-2
        ipaddress.ip_network('203.0.113.0/24'),     # TEST-NET-3
        ipaddress.ip_network('224.0.0.0/4'),        # Multicast
        ipaddress.ip_network('240.0.0.0/4'),        # Reserved
        ipaddress.ip_network('255.255.255.255/32'), # Broadcast
        
        # IPv6 private/special ranges
        ipaddress.ip_network('::1/128'),            # Loopback
        ipaddress.ip_network('fc00::/7'),           # Unique local
        ipaddress.ip_network('fe80::/10'),          # Link-local
        ipaddress.ip_network('ff00::/8'),           # Multicast
        ipaddress.ip_network('::/128'),             # Unspecified
        ipaddress.ip_network('::ffff:0:0/96'),      # IPv4-mapped IPv6
        ipaddress.ip_network('64:ff9b::/96'),       # IPv4/IPv6 translation
        ipaddress.ip_network('2001:db8::/32'),      # Documentation
    ]
    
    # Common internal hostnames to block
    BLOCKED_HOSTNAMES = {
        'localhost',
        'localhost.localdomain',
        'localhost4',
        'localhost4.localdomain4',
        'localhost6',
        'localhost6.localdomain6',
        'ip6-localhost',
        'ip6-loopback',
    }
    
    # Metadata service endpoints (cloud providers)
    METADATA_IPS = [
        ipaddress.ip_network('169.254.169.254/32'),  # AWS, GCP, Azure metadata
        ipaddress.ip_network('fd00:ec2::254/128'),   # AWS IPv6 metadata
    ]
    
    def __init__(self, 
                 allow_private: bool = False,
                 allow_loopback: bool = False,
                 allow_metadata: bool = False,
                 custom_blocked_ranges: Optional[List[str]] = None):
        """Initialize IP validator
        
        Args:
            allow_private: Allow private IP ranges (dangerous, not recommended)
            allow_loopback: Allow loopback addresses (dangerous, not recommended)
            allow_metadata: Allow cloud metadata endpoints (dangerous, not recommended)
            custom_blocked_ranges: Additional IP ranges to block (CIDR notation)
        """
        self.allow_private = allow_private
        self.allow_loopback = allow_loopback
        self.allow_metadata = allow_metadata
        
        # Build blocked ranges based on configuration
        self.blocked_ranges = []
        
        if not allow_private:
            self.blocked_ranges.extend(self.PRIVATE_IP_RANGES)
            
        if not allow_metadata:
            self.blocked_ranges.extend(self.METADATA_IPS)
            
        # Add custom blocked ranges
        if custom_blocked_ranges:
            for range_str in custom_blocked_ranges:
                try:
                    self.blocked_ranges.append(ipaddress.ip_network(range_str))
                except ValueError as e:
                    logger.error(f"Invalid IP range '{range_str}': {e}")
    
    def is_ip_safe(self, ip: Union[str, ipaddress.IPv4Address, ipaddress.IPv6Address]) -> Tuple[bool, Optional[str]]:
        """Check if an IP address is safe to connect to
        
        Args:
            ip: IP address to validate (string or ipaddress object)
            
        Returns:
            Tuple of (is_safe, reason_if_unsafe)
        """
        try:
            # Convert to ipaddress object if string
            if isinstance(ip, str):
                ip_obj = ipaddress.ip_address(ip)
            else:
                ip_obj = ip
                
            # Check against blocked ranges
            for blocked_range in self.blocked_ranges:
                if ip_obj in blocked_range:
                    range_desc = self._describe_ip_range(blocked_range)
                    return False, f"IP {ip_obj} is in blocked range: {range_desc}"
                    
            # Additional checks for specific addresses
            if not self.allow_loopback and ip_obj.is_loopback:
                return False, f"IP {ip_obj} is a loopback address"
                
            if ip_obj.is_multicast:
                return False, f"IP {ip_obj} is a multicast address"
                
            if ip_obj.is_reserved:
                return False, f"IP {ip_obj} is a reserved address"
                
            if isinstance(ip_obj, ipaddress.IPv4Address):
                if ip_obj.is_unspecified:
                    return False, f"IP {ip_obj} is unspecified (0.0.0.0)"
                    
            elif isinstance(ip_obj, ipaddress.IPv6Address):
                if ip_obj.is_unspecified:
                    return False, f"IP {ip_obj} is unspecified (::)"
                    
            return True, None
            
        except ValueError as e:
            return False, f"Invalid IP address: {e}"
    
    def is_hostname_safe(self, hostname: str) -> Tuple[bool, Optional[str]]:
        """Check if a hostname is safe to connect to
        
        Args:
            hostname: Hostname to validate
            
        Returns:
            Tuple of (is_safe, reason_if_unsafe)
        """
        # Check against blocked hostnames
        if hostname.lower() in self.BLOCKED_HOSTNAMES:
            return False, f"Hostname '{hostname}' is blocked"
            
        # Check for IP addresses disguised as hostnames
        try:
            # Try to parse as IP
            ip = ipaddress.ip_address(hostname)
            return self.is_ip_safe(ip)
        except ValueError:
            # Not an IP address, continue with DNS resolution
            pass
            
        # Resolve hostname to IPs and check each one
        try:
            # Get all IP addresses for the hostname
            addr_info = socket.getaddrinfo(hostname, None)
            ips = set()
            
            for family, socktype, proto, canonname, sockaddr in addr_info:
                ip = sockaddr[0]
                ips.add(ip)
                
            # Check each resolved IP
            for ip in ips:
                is_safe, reason = self.is_ip_safe(ip)
                if not is_safe:
                    return False, f"Hostname '{hostname}' resolves to unsafe IP: {reason}"
                    
            return True, None
            
        except socket.gaierror as e:
            # DNS resolution failed
            return False, f"Failed to resolve hostname '{hostname}': {e}"
        except Exception as e:
            logger.exception(f"Error validating hostname '{hostname}': {e}")
            return False, f"Error validating hostname: {e}"
    
    def is_url_safe(self, url: str) -> Tuple[bool, Optional[str]]:
        """Check if a URL is safe to connect to
        
        Args:
            url: URL to validate
            
        Returns:
            Tuple of (is_safe, reason_if_unsafe)
        """
        try:
            parsed = urlparse(url)
            
            # Check scheme
            if parsed.scheme not in ('http', 'https'):
                return False, f"Unsupported scheme '{parsed.scheme}' - only http/https allowed"
                
            # Extract hostname
            hostname = parsed.hostname
            if not hostname:
                return False, "No hostname found in URL"
                
            # Check port
            port = parsed.port
            if port is not None:
                # Block common internal service ports
                blocked_ports = {22, 23, 25, 111, 135, 139, 445, 631, 3389, 5432, 3306, 6379, 9200, 27017}
                if port in blocked_ports:
                    return False, f"Port {port} is commonly used for internal services"
                    
            # Validate hostname
            return self.is_hostname_safe(hostname)
            
        except Exception as e:
            logger.exception(f"Error validating URL '{url}': {e}")
            return False, f"Error parsing URL: {e}"
    
    def _describe_ip_range(self, network: ipaddress.IPv4Network) -> str:
        """Get human-readable description of IP range"""
        range_descriptions = {
            '10.0.0.0/8': 'Private Class A',
            '172.16.0.0/12': 'Private Class B',
            '192.168.0.0/16': 'Private Class C',
            '127.0.0.0/8': 'Loopback',
            '169.254.0.0/16': 'Link-local',
            '169.254.169.254/32': 'Cloud metadata service',
            '0.0.0.0/8': 'This network',
            '224.0.0.0/4': 'Multicast',
            '240.0.0.0/4': 'Reserved',
            'fc00::/7': 'IPv6 Unique Local',
            'fe80::/10': 'IPv6 Link-local',
            '::1/128': 'IPv6 Loopback',
        }
        
        network_str = str(network)
        return range_descriptions.get(network_str, network_str)


# Global validator instance with secure defaults
default_validator = IPValidator()


def validate_url_safety(url: str) -> Tuple[bool, Optional[str]]:
    """Convenience function to validate URL safety
    
    Args:
        url: URL to validate
        
    Returns:
        Tuple of (is_safe, reason_if_unsafe)
    """
    return default_validator.is_url_safe(url)


def validate_ip_safety(ip: str) -> Tuple[bool, Optional[str]]:
    """Convenience function to validate IP safety
    
    Args:
        ip: IP address to validate
        
    Returns:
        Tuple of (is_safe, reason_if_unsafe)
    """
    return default_validator.is_ip_safe(ip)


def validate_hostname_safety(hostname: str) -> Tuple[bool, Optional[str]]:
    """Convenience function to validate hostname safety
    
    Args:
        hostname: Hostname to validate
        
    Returns:
        Tuple of (is_safe, reason_if_unsafe)
    """
    return default_validator.is_hostname_safe(hostname)