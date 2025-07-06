# Enhanced Web Content Extraction Service

The enhanced web content extraction service provides robust URL content extraction with proper timeouts, connectivity testing, and concurrent processing capabilities.

## Key Features

### 1. **Timeout Management**
- **Connectivity Testing**: 5-second timeout for pre-validation
- **Content Extraction**: 10-second timeout per URL as requested
- **Configurable timeouts** for different use cases
- **Graceful timeout handling** with partial results

### 2. **URL Connectivity Testing Integration**
- Pre-validates URLs before attempting extraction
- Uses circuit breaker pattern to avoid repeated failures
- Filters out unreachable URLs to save processing time
- Provides detailed connectivity error information

### 3. **Concurrent Processing**
- Async support with configurable concurrency (default: 5 concurrent)
- Respects rate limiting to avoid overwhelming servers
- Thread pool for blocking trafilatura calls
- Efficient batch processing for multiple URLs

### 4. **Enhanced Error Handling**
- Distinguishes between connectivity and extraction failures
- Categorizes errors (timeout, DNS, SSL, HTTP errors)
- Provides detailed error messages for debugging
- Preserves partial results on failure

## Usage Examples

### Basic Usage

```python
from gps_toolkit.services.web_content import WebContentService

# Create service with default settings
service = WebContentService()

# Extract content from URLs
urls = ["https://example.com", "https://wikipedia.org"]
results = service.extract_web_content(urls)

for result in results:
    if 'error' in result:
        print(f"Failed: {result['url']} - {result['error']}")
    else:
        print(f"Success: {result['url']}")
        print(f"Content: {result.get('content', '')[:100]}...")
```

### With Custom Timeouts

```python
# Custom timeout configuration
service = WebContentService(
    ping_timeout=5.0,        # 5s for connectivity test
    extraction_timeout=10.0,  # 10s for content extraction
    max_concurrent=5         # Max 5 concurrent extractions
)

results = service.extract_web_content(urls)
```

### Async Batch Processing

```python
import asyncio

async def extract_many_urls():
    service = WebContentService()
    
    urls = [
        "https://example1.com",
        "https://example2.com",
        "https://example3.com"
    ]
    
    # Extract with pre-validation
    results = await service.extract_multiple_urls_async(
        urls,
        validate_connectivity=True
    )
    
    for result in results:
        if result.connectivity_passed and not result.error:
            print(f"✅ {result.url}: {len(result.content)} chars")
        else:
            print(f"❌ {result.url}: {result.error}")

# Run async
asyncio.run(extract_many_urls())
```

### Without Connectivity Pre-Check

```python
# Skip connectivity check for faster processing
service = WebContentService(enable_connectivity_check=False)

# Or per-request
results = await service.extract_multiple_urls_async(
    urls,
    validate_connectivity=False
)
```

### Using Convenience Functions

```python
from gps_toolkit.services.web_content import extract_web_content

# Simple synchronous extraction
results = extract_web_content(
    urls=["https://example.com"],
    timeout=10.0,
    validate_connectivity=True
)

# Async version
results = await extract_web_content_async(
    urls=["https://example.com"],
    timeout=10.0,
    validate_connectivity=True
)
```

## Configuration Options

### WebContentService Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `connectivity_tester` | None | Custom URLConnectivityTester instance |
| `max_concurrent` | 5 | Maximum concurrent extractions |
| `ping_timeout` | 5.0 | Timeout for connectivity testing (seconds) |
| `extraction_timeout` | 10.0 | Timeout for content extraction (seconds) |
| `max_content_length` | 5000 | Maximum content length before truncation |
| `rate_limit_delay` | 0.5 | Delay between requests (seconds) |
| `enable_connectivity_check` | True | Whether to pre-check URL connectivity |

## Result Structure

### WebContentResult Object

```python
@dataclass
class WebContentResult:
    url: str                           # Original URL
    content: Optional[str]             # Extracted content (markdown)
    metadata: Dict[str, Any]           # Title, author, date, etc.
    error: Optional[str]               # Error message if failed
    error_type: Optional[str]          # Error classification
    extraction_time_ms: Optional[float] # Extraction time
    content_truncated: bool            # Whether content was truncated
    original_length: Optional[int]     # Original content length
    connectivity_passed: bool          # Connectivity test result
    timestamp: datetime                # Extraction timestamp
```

### Dictionary Format (Backward Compatible)

```python
{
    'url': 'https://example.com',
    'content': 'Extracted markdown content...',
    'metadata': {
        'title': 'Page Title',
        'author': 'Author Name',
        'date': '2024-01-01',
        'description': 'Page description',
        'site_name': 'Example Site',
        'language': 'en'
    },
    'content_truncated': False,
    'extraction_time_ms': 1234.5,
    'connectivity_passed': True
}
```

## Error Types

| Error Type | Description |
|------------|-------------|
| `ConnectivityFailed` | URL not reachable during pre-check |
| `CircuitBreakerOpen` | Too many failures to domain |
| `ExtractionTimeout` | Content extraction exceeded timeout |
| `DependencyError` | Required library not installed |
| `ExtractionFailed` | General extraction failure |
| `Timeout` | Request timeout |
| `ConnectionError` | Network connection error |
| `SSLError` | SSL certificate error |
| `HTTPError` | HTTP status error (4xx, 5xx) |

## Circuit Breaker

The service includes a circuit breaker to prevent repeated requests to failing domains:

```python
# Check circuit breaker status
status = service.connectivity_tester.get_circuit_breaker_status()

# Reset circuit breaker for a domain
service.connectivity_tester.reset_circuit_breaker('example.com')

# Reset all circuit breakers
service.connectivity_tester.reset_circuit_breaker()
```

## Performance Considerations

1. **Pre-validation Trade-off**: Connectivity checking adds 5s overhead but prevents wasting time on unreachable URLs
2. **Concurrent Limits**: Default 5 concurrent to respect server limits
3. **Memory Usage**: Content is truncated at 5000 chars by default
4. **Rate Limiting**: 0.5s delay between requests to avoid overwhelming servers

## Best Practices

1. **Use async methods** for batch processing of multiple URLs
2. **Enable connectivity checking** for unknown or user-provided URLs
3. **Adjust timeouts** based on expected content size and network conditions
4. **Monitor circuit breaker** status for problematic domains
5. **Handle partial failures** gracefully in batch operations

## Dependencies

- `trafilatura`: For content extraction (required)
- `aiohttp`: For async HTTP requests (required)
- `aiodns`: For async DNS resolution (optional, improves performance)

## Installation

```bash
pip install trafilatura aiohttp aiodns
```

## Integration with GPS Enhanced

The service integrates seamlessly with the GPS enhanced image processor:

```python
from gps_enhanced_v2_secure import GPSLocationExtractor

extractor = GPSLocationExtractor()

# URLs found in OCR text are automatically extracted
# with proper timeout handling
result = extractor.extract_all_location_data(
    image_path,
    extract_text=True,
    extract_web_content=True
)

# Web content is available in result['web_content']
```