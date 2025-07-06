#!/usr/bin/env python3
"""Example of using GPS Toolkit with SSRF protection

This example demonstrates how the GPS Toolkit safely handles URLs
with built-in SSRF protection.
"""

import json
from gps_toolkit.services.web_content import WebContentService
from gps_toolkit.services.text_extraction import TextExtractionService


def main():
    # Example image that might contain URLs
    image_path = "example_image.jpg"
    
    print("GPS Toolkit - Safe URL Extraction Example")
    print("=" * 50)
    
    # Step 1: Extract text and URLs from image
    print("\n1. Extracting text from image...")
    text_service = TextExtractionService()
    
    try:
        text_result = text_service.extract_text(image_path)
        
        if text_result.get('success'):
            print(f"   Extracted text: {text_result.get('text', '')[:100]}...")
            urls = text_result.get('urls', [])
            print(f"   Found {len(urls)} URLs in image")
            for url in urls:
                print(f"   - {url}")
        else:
            print("   No text extracted")
            urls = []
            
    except Exception as e:
        print(f"   Error extracting text: {e}")
        urls = []
    
    # Step 2: Safely fetch content from URLs (with SSRF protection)
    if urls:
        print("\n2. Fetching content from URLs (with SSRF protection)...")
        
        # Add some test URLs to demonstrate protection
        test_urls = urls + [
            "http://192.168.1.1/admin",  # Will be blocked
            "http://localhost:8080/",    # Will be blocked
            "https://example.com/"        # Will be allowed
        ]
        
        with WebContentService() as web_service:
            results = web_service.extract_web_content(test_urls)
            
            print(f"\n   Results for {len(results)} URLs:")
            for result in results:
                url = result['url']
                if 'error' in result:
                    if result.get('error_type') == 'SecurityError':
                        print(f"   🚫 BLOCKED: {url}")
                        print(f"      Reason: {result['error']}")
                    else:
                        print(f"   ❌ ERROR: {url}")
                        print(f"      {result['error']}")
                else:
                    print(f"   ✅ SUCCESS: {url}")
                    if result.get('metadata', {}).get('title'):
                        print(f"      Title: {result['metadata']['title']}")
                    if result.get('content'):
                        preview = result['content'][:100].replace('\n', ' ')
                        print(f"      Content: {preview}...")
    
    print("\n" + "=" * 50)
    print("SSRF Protection Summary:")
    print("- Internal IPs are blocked (192.168.x.x, 10.x.x.x, etc.)")
    print("- Localhost/loopback addresses are blocked")
    print("- Cloud metadata endpoints are blocked")
    print("- Only http/https to public IPs are allowed")
    print("\nYour application is protected from SSRF attacks!")


if __name__ == "__main__":
    main()