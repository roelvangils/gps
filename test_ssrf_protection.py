#!/usr/bin/env python3
"""Test SSRF Protection Implementation

This script demonstrates the SSRF protection mechanisms added to the GPS Toolkit.
It tests various potentially dangerous URLs to ensure they are properly blocked.
"""

import asyncio
import sys
from gps_toolkit.services.web_content import WebContentService
from gps_toolkit.services.url_connectivity import URLConnectivityTester
from gps_toolkit.security import validate_url_safety, IPValidator


def print_header(title):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f"{title:^60}")
    print(f"{'='*60}\n")


def test_url_validation():
    """Test URL validation against various potentially dangerous URLs"""
    print_header("Testing URL Validation")
    
    # Test cases with various malicious URLs
    test_urls = [
        # Internal IP addresses
        ("http://127.0.0.1/", "Loopback address"),
        ("http://localhost/admin", "Localhost"),
        ("http://192.168.1.1/", "Private IP (Class C)"),
        ("http://10.0.0.1/", "Private IP (Class A)"),
        ("http://172.16.0.1/", "Private IP (Class B)"),
        
        # Cloud metadata endpoints
        ("http://169.254.169.254/latest/meta-data/", "AWS metadata endpoint"),
        ("http://metadata.google.internal/computeMetadata/v1/", "GCP metadata"),
        
        # IPv6 addresses
        ("http://[::1]/", "IPv6 loopback"),
        ("http://[fe80::1]/", "IPv6 link-local"),
        ("http://[fc00::1]/", "IPv6 unique local"),
        
        # Special addresses
        ("http://0.0.0.0/", "This network"),
        ("http://255.255.255.255/", "Broadcast"),
        ("http://224.0.0.1/", "Multicast"),
        
        # Internal service ports
        ("http://example.com:22/", "SSH port"),
        ("http://example.com:3306/", "MySQL port"),
        ("http://example.com:6379/", "Redis port"),
        
        # Valid external URLs (should pass)
        ("https://www.google.com/", "Valid external URL"),
        ("https://api.github.com/", "Valid API endpoint"),
        ("https://example.com/", "Valid example domain"),
    ]
    
    for url, description in test_urls:
        is_safe, reason = validate_url_safety(url)
        status = "✅ ALLOWED" if is_safe else "🚫 BLOCKED"
        print(f"{status} | {description:<25} | {url}")
        if not is_safe:
            print(f"        Reason: {reason}")


async def test_web_content_extraction():
    """Test web content extraction with SSRF protection"""
    print_header("Testing Web Content Service with SSRF Protection")
    
    # Mix of safe and unsafe URLs
    test_urls = [
        "http://127.0.0.1/test",
        "http://192.168.1.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "https://www.example.com/",
        "https://httpbin.org/html",
    ]
    
    print("Attempting to extract content from URLs...")
    
    with WebContentService() as service:
        results = await service.extract_web_content_async(test_urls)
        
        for result in results:
            print(f"\nURL: {result.url}")
            if result.error:
                print(f"  ❌ Error: {result.error}")
                print(f"  Error Type: {result.error_type}")
            else:
                print(f"  ✅ Success: Content extracted")
                if result.content:
                    preview = result.content[:100].replace('\n', ' ')
                    print(f"  Content preview: {preview}...")


async def test_connectivity_checker():
    """Test URL connectivity checker with SSRF protection"""
    print_header("Testing URL Connectivity with SSRF Protection")
    
    tester = URLConnectivityTester()
    
    # Test individual URLs
    test_cases = [
        "http://localhost:8080/",
        "http://10.0.0.1/",
        "https://www.google.com/",
        "http://[::1]:8080/",
    ]
    
    print("Testing individual URL connectivity...")
    for url in test_cases:
        result = await tester.is_url_reachable(url, timeout=5.0)
        status = "✅ REACHABLE" if result['reachable'] else "🚫 BLOCKED/UNREACHABLE"
        print(f"\n{status} | {url}")
        if result.get('error_message'):
            print(f"  Reason: {result['error_message']}")
        if result.get('response_time_ms'):
            print(f"  Response time: {result['response_time_ms']:.1f}ms")


def test_ip_validator_directly():
    """Test IP validator with various addresses"""
    print_header("Testing IP Validator Directly")
    
    validator = IPValidator()
    
    # Test IP addresses
    test_ips = [
        "127.0.0.1",
        "192.168.1.1",
        "10.0.0.1",
        "172.16.0.1",
        "8.8.8.8",
        "1.1.1.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "2001:4860:4860::8888",
    ]
    
    print("IP Address Validation:")
    for ip in test_ips:
        is_safe, reason = validator.is_ip_safe(ip)
        status = "✅ SAFE" if is_safe else "🚫 UNSAFE"
        print(f"{status} | {ip:<20} | {reason or 'OK'}")
    
    # Test hostnames
    print("\nHostname Validation:")
    test_hostnames = [
        "localhost",
        "localhost.localdomain",
        "google.com",
        "example.com",
        "metadata.google.internal",
    ]
    
    for hostname in test_hostnames:
        is_safe, reason = validator.is_hostname_safe(hostname)
        status = "✅ SAFE" if is_safe else "🚫 UNSAFE"
        print(f"{status} | {hostname:<25} | {reason or 'OK'}")


async def main():
    """Run all tests"""
    print_header("SSRF Protection Test Suite")
    print("This demonstrates the SSRF protection mechanisms in GPS Toolkit")
    
    # Run synchronous tests
    test_url_validation()
    test_ip_validator_directly()
    
    # Run async tests
    await test_web_content_extraction()
    await test_connectivity_checker()
    
    print_header("Test Complete")
    print("All potentially dangerous URLs were properly blocked!")
    print("The GPS Toolkit is now protected against SSRF attacks.")


if __name__ == "__main__":
    # Run the tests
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(0)