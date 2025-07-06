"""Web content extraction service for GPS Toolkit

Enhanced with proper timeouts, connectivity testing, and concurrent processing.
"""

import os
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from urllib.parse import urlparse
from dataclasses import dataclass, field
from datetime import datetime
import aiohttp
from aiohttp import ClientTimeout, ClientError

# Import optional library
try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

# Import our connectivity tester
from .url_connectivity import URLConnectivityTester, ConnectivityResult
from ..config import settings
from ..security import validate_url_safety

logger = logging.getLogger(__name__)


@dataclass
class WebContentResult:
    """Result of web content extraction"""
    url: str
    content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_type: Optional[str] = None
    extraction_time_ms: Optional[float] = None
    content_truncated: bool = False
    original_length: Optional[int] = None
    connectivity_passed: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)


class WebContentService:
    """Service for extracting content from URLs with connectivity testing"""
    
    def __init__(
        self,
        connectivity_tester: Optional[URLConnectivityTester] = None,
        max_concurrent: int = 5,
        ping_timeout: float = 5.0,
        extraction_timeout: float = 10.0,
        max_content_length: int = 5000,
        rate_limit_delay: float = 0.5,
        enable_connectivity_check: bool = True,
        thread_pool: Optional[ThreadPoolExecutor] = None
    ):
        """Initialize the web content service
        
        Args:
            connectivity_tester: Optional URLConnectivityTester instance
            max_concurrent: Maximum concurrent extractions
            ping_timeout: Timeout for connectivity testing in seconds
            extraction_timeout: Timeout for content extraction per URL in seconds
            max_content_length: Maximum content length before truncation
            rate_limit_delay: Delay between requests in seconds
            enable_connectivity_check: Whether to pre-check URL connectivity
            thread_pool: Optional shared thread pool executor
        """
        self.connectivity_tester = connectivity_tester or URLConnectivityTester(
            max_concurrent=max_concurrent,
            default_timeout=ping_timeout
        )
        self.max_concurrent = max_concurrent
        self.ping_timeout = ping_timeout
        self.extraction_timeout = extraction_timeout
        self.max_content_length = max_content_length
        self.rate_limit_delay = rate_limit_delay
        self.enable_connectivity_check = enable_connectivity_check
        self.user_agent = settings.USER_AGENT  # Store user agent for fallback requests
        
        # Semaphore for concurrent extractions
        self._semaphore = asyncio.Semaphore(max_concurrent)
        
        # Thread pool for blocking trafilatura calls
        self._thread_pool = thread_pool
        self._owns_thread_pool = thread_pool is None
        if self._owns_thread_pool:
            self._thread_pool = ThreadPoolExecutor(max_workers=max_concurrent)
    
    def extract_web_content(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Extract content from a list of URLs using trafilatura.
        Synchronous wrapper around async implementation.
        
        Args:
            urls: List of URLs to extract content from
            
        Returns:
            List of dictionaries containing URL and extracted content/metadata
        """
        if not urls:
            return []
            
        # Use async implementation
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an async context, create a new loop in thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.extract_multiple_urls_async(urls))
                    results = future.result(timeout=len(urls) * self.extraction_timeout + 5)
            else:
                results = asyncio.run(self.extract_multiple_urls_async(urls))
        except Exception as e:
            logger.exception(f"Error in synchronous extraction: {e}")
            results = []
            
        # Convert WebContentResult objects to dicts for backward compatibility
        return [self._result_to_dict(r) for r in results]
    
    def extract_web_content_with_validation(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Extract content with pre-validation of URL connectivity.
        
        Args:
            urls: List of URLs to extract content from
            
        Returns:
            List of dictionaries with extraction results
        """
        return self.extract_web_content(urls)
    
    async def _extract_single_url(self, url: str) -> WebContentResult:
        """
        Extract content from a single URL with timeout control.
        
        Args:
            url: URL to extract content from
            
        Returns:
            WebContentResult with extraction details
        """
        result = WebContentResult(url=url)
        start_time = time.time()
        
        # First, validate URL for SSRF protection
        is_safe, reason = validate_url_safety(url)
        if not is_safe:
            result.error_type = "SecurityError"
            result.error = f"URL blocked for security: {reason}"
            result.extraction_time_ms = (time.time() - start_time) * 1000
            logger.warning(f"Blocked potentially unsafe URL: {url} - {reason}")
            return result
        
        # Check connectivity first if enabled
        if self.enable_connectivity_check:
            try:
                connectivity = await self.connectivity_tester.is_url_reachable(
                    url, timeout=self.ping_timeout
                )
                if not connectivity['reachable']:
                    result.connectivity_passed = False
                    result.error_type = connectivity.get('error_type', 'ConnectivityFailed')
                    result.error = connectivity.get('error_message', 'URL not reachable')
                    result.extraction_time_ms = (time.time() - start_time) * 1000
                    return result
            except Exception as e:
                logger.warning(f"Connectivity check failed for {url}: {e}")
                # Continue with extraction anyway
        
        if not HAS_TRAFILATURA:
            result.error = "trafilatura not installed"
            result.error_type = "DependencyError"
            return result
            
        try:
            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)
            
            # Run trafilatura in thread pool with timeout
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(
                self._thread_pool,
                self._extract_with_trafilatura,
                url
            )
            
            # Apply timeout
            try:
                extraction_data = await asyncio.wait_for(
                    future,
                    timeout=self.extraction_timeout
                )
                
                # Process extraction results
                if extraction_data:
                    result.content = extraction_data.get('content')
                    result.metadata = extraction_data.get('metadata', {})
                    result.content_truncated = extraction_data.get('content_truncated', False)
                    result.original_length = extraction_data.get('original_length')
                else:
                    result.error = "No content extracted"
                    result.error_type = "ExtractionFailed"
                    
            except asyncio.TimeoutError:
                result.error = f"Extraction timeout after {self.extraction_timeout}s"
                result.error_type = "ExtractionTimeout"
                logger.warning(f"Extraction timeout for {url}")
                
        except Exception as e:
            result.error = str(e)
            result.error_type = type(e).__name__
            logger.exception(f"Error extracting content from {url}: {e}")
            
        result.extraction_time_ms = (time.time() - start_time) * 1000
        return result
    
    def _extract_with_trafilatura(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract content using trafilatura (blocking call).
        
        Args:
            url: URL to extract from
            
        Returns:
            Dict with extracted content and metadata
        """
        try:
            # Download the content with custom settings
            downloaded = trafilatura.fetch_url(
                url,
                no_ssl=False,
                config=trafilatura.settings.use_config()
            )
            
            # If trafilatura.fetch_url fails (e.g., for 404 pages), 
            # try with requests as fallback
            if not downloaded:
                try:
                    import requests
                    # Re-validate URL before making request (paranoid check)
                    is_safe, _ = validate_url_safety(url)
                    if not is_safe:
                        return None
                    response = requests.get(
                        url, 
                        headers={'User-Agent': self.user_agent or settings.USER_AGENT},
                        timeout=self.extraction_timeout
                    )
                    # Accept any status code that returns HTML
                    if response.text and 'text/html' in response.headers.get('Content-Type', ''):
                        downloaded = response.text
                        logger.debug(f"Used requests fallback for {url} (status: {response.status_code})")
                except Exception as e:
                    logger.debug(f"Requests fallback failed for {url}: {e}")
                    
            if not downloaded:
                return None
                
            # Extract content with metadata
            # Try with precision first
            content = trafilatura.extract(
                downloaded,
                output_format='markdown',
                include_formatting=True,
                include_images=False,
                include_links=True,
                favor_precision=True,
                deduplicate=True,
                config=trafilatura.settings.use_config()
            )
            
            # If no content extracted, try with more lenient settings
            # This helps with error pages, 404s, etc.
            if not content:
                content = trafilatura.extract(
                    downloaded,
                    output_format='markdown',
                    include_formatting=True,
                    include_images=False,
                    include_links=True,
                    favor_recall=True,  # More lenient
                    favor_precision=False,
                    deduplicate=True,
                    config=trafilatura.settings.use_config()
                )
                if content:
                    logger.debug(f"Used lenient extraction for {url}")
            
            # Extract metadata
            metadata = trafilatura.extract_metadata(downloaded)
            
            result_data = {
                'content': None,
                'metadata': {},
                'content_truncated': False,
                'original_length': None
            }
            
            # Process content
            if content:
                original_length = len(content)
                if original_length > self.max_content_length:
                    result_data['content'] = content[:self.max_content_length] + '\n\n[Content truncated...]'
                    result_data['content_truncated'] = True
                    result_data['original_length'] = original_length
                else:
                    result_data['content'] = content
                    
            # Process metadata
            if metadata:
                metadata_dict = {}
                if metadata.title:
                    metadata_dict['title'] = metadata.title
                if metadata.author:
                    metadata_dict['author'] = metadata.author
                if metadata.date:
                    metadata_dict['date'] = metadata.date
                if metadata.description:
                    metadata_dict['description'] = metadata.description
                if metadata.sitename:
                    metadata_dict['site_name'] = metadata.sitename
                if metadata.language:
                    metadata_dict['language'] = metadata.language
                result_data['metadata'] = metadata_dict
                
            return result_data if (result_data['content'] or result_data['metadata']) else None
            
        except Exception as e:
            logger.exception(f"Trafilatura extraction error for {url}: {e}")
            raise
    
    async def extract_multiple_urls_async(
        self,
        urls: List[str],
        validate_connectivity: bool = None
    ) -> List[WebContentResult]:
        """
        Extract content from multiple URLs concurrently.
        
        Args:
            urls: List of URLs to extract
            validate_connectivity: Override connectivity check setting
            
        Returns:
            List of WebContentResult objects
        """
        if not urls:
            return []
            
        # Use class setting if not overridden
        if validate_connectivity is None:
            validate_connectivity = self.enable_connectivity_check
            
        # Pre-filter URLs if connectivity check is enabled
        if validate_connectivity:
            logger.info(f"Pre-filtering {len(urls)} URLs for connectivity...")
            reachable_urls = await self.connectivity_tester.filter_reachable_urls(
                urls, timeout=self.ping_timeout
            )
            
            # Create results for unreachable URLs
            unreachable_results = []
            for url in urls:
                if url not in reachable_urls:
                    result = WebContentResult(
                        url=url,
                        connectivity_passed=False,
                        error="URL not reachable during pre-check",
                        error_type="ConnectivityFailed"
                    )
                    unreachable_results.append(result)
                    
            urls_to_process = reachable_urls
            logger.info(f"Processing {len(urls_to_process)} reachable URLs")
        else:
            unreachable_results = []
            urls_to_process = urls
            
        # Extract content from reachable URLs
        async with self._semaphore:
            tasks = [self._extract_single_url(url) for url in urls_to_process]
            extraction_results = await asyncio.gather(*tasks, return_exceptions=True)
            
        # Process results
        final_results = []
        
        # Add unreachable results first
        final_results.extend(unreachable_results)
        
        # Process extraction results
        for url, result in zip(urls_to_process, extraction_results):
            if isinstance(result, Exception):
                error_result = WebContentResult(
                    url=url,
                    error=str(result),
                    error_type=type(result).__name__
                )
                final_results.append(error_result)
            else:
                final_results.append(result)
                
        return final_results
    
    async def extract_web_content_async(
        self,
        urls: List[str]
    ) -> List[WebContentResult]:
        """
        Async version of extract_web_content.
        
        Args:
            urls: List of URLs to extract
            
        Returns:
            List of WebContentResult objects
        """
        return await self.extract_multiple_urls_async(urls)
    
    def _result_to_dict(self, result: WebContentResult) -> Dict[str, Any]:
        """
        Convert WebContentResult to dictionary for backward compatibility.
        
        Args:
            result: WebContentResult object
            
        Returns:
            Dictionary representation
        """
        data = {
            'url': result.url
        }
        
        if result.error:
            data['error'] = result.error
            if result.error_type:
                data['error_type'] = result.error_type
        else:
            if result.content:
                data['content'] = result.content
            if result.metadata:
                data['metadata'] = result.metadata
            if result.content_truncated:
                data['content_truncated'] = True
                if result.original_length:
                    data['original_length'] = result.original_length
                    
        if result.extraction_time_ms:
            data['extraction_time_ms'] = result.extraction_time_ms
            
        if not result.connectivity_passed:
            data['connectivity_passed'] = False
            
        return data
    
    def is_near_duplicate_url(self, url1: str, url2: str, threshold: float = 0.8) -> bool:
        """
        Check if two URLs are near-duplicates based on domain and path similarity.
        
        Args:
            url1: First URL
            url2: Second URL
            threshold: Similarity threshold (0-1)
            
        Returns:
            True if URLs are considered near-duplicates
        """
        try:
            parsed1 = urlparse(url1)
            parsed2 = urlparse(url2)
            
            # Same domain check
            domain1 = parsed1.netloc.lower().replace('www.', '')
            domain2 = parsed2.netloc.lower().replace('www.', '')
            
            if domain1 != domain2:
                return False
            
            # Path similarity check
            path1 = parsed1.path.lower().rstrip('/')
            path2 = parsed2.path.lower().rstrip('/')
            
            # Exact match
            if path1 == path2:
                return True
            
            # Check if one is a subpath of the other
            if path1.startswith(path2 + '/') or path2.startswith(path1 + '/'):
                return True
            
            # Calculate simple similarity ratio
            common_prefix = os.path.commonprefix([path1, path2])
            if len(common_prefix) > 0:
                similarity = len(common_prefix) / max(len(path1), len(path2))
                return similarity >= threshold
            
            return False
            
        except Exception:
            return False
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources"""
        self.cleanup()
        return False
    
    def cleanup(self):
        """Cleanup resources properly"""
        if self._owns_thread_pool and self._thread_pool:
            try:
                self._thread_pool.shutdown(wait=True, cancel_futures=True)
            except Exception:
                pass
            self._thread_pool = None
    


# Convenience functions for backward compatibility
def extract_web_content(
    urls: List[str],
    timeout: float = 10.0,
    validate_connectivity: bool = True
) -> List[Dict[str, Any]]:
    """
    Extract web content with default settings.
    
    Args:
        urls: List of URLs to extract
        timeout: Extraction timeout per URL
        validate_connectivity: Whether to pre-check connectivity
        
    Returns:
        List of extraction results
    """
    with WebContentService(
        extraction_timeout=timeout,
        enable_connectivity_check=validate_connectivity
    ) as service:
        return service.extract_web_content(urls)


async def extract_web_content_async(
    urls: List[str],
    timeout: float = 10.0,
    validate_connectivity: bool = True
) -> List[Dict[str, Any]]:
    """
    Async extraction with default settings.
    
    Args:
        urls: List of URLs to extract
        timeout: Extraction timeout per URL
        validate_connectivity: Whether to pre-check connectivity
        
    Returns:
        List of extraction results
    """
    service = WebContentService(
        extraction_timeout=timeout,
        enable_connectivity_check=validate_connectivity
    )
    try:
        results = await service.extract_web_content_async(urls)
        return [service._result_to_dict(r) for r in results]
    finally:
        service.cleanup()