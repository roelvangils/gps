"""URL Connectivity Testing Service for GPS Toolkit

This module provides robust URL connectivity testing with async support,
circuit breaker pattern, and comprehensive error handling.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from urllib.parse import urlparse
import socket
import ssl

import aiohttp
from aiohttp import ClientTimeout, ClientError, ServerTimeoutError
from aiohttp.resolver import AsyncResolver
import aiodns

from ..config import settings
from ..security import validate_url_safety

logger = logging.getLogger(__name__)


@dataclass
class ConnectivityResult:
    """Detailed connectivity test result"""
    url: str
    reachable: bool
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    redirect_chain: List[str] = field(default_factory=list)
    final_url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    ssl_info: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CircuitBreakerState:
    """Circuit breaker state for a domain"""
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    state: str = "closed"  # closed, open, half-open
    next_retry: Optional[datetime] = None


class URLConnectivityTester:
    """Robust URL connectivity testing with async support and circuit breaker"""
    
    def __init__(
        self,
        max_concurrent: int = 10,
        default_timeout: float = None,
        max_redirects: int = 3,
        user_agent: str = None,
        retry_attempts: int = 2,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 300,  # 5 minutes
        enable_ipv6: bool = True
    ):
        """Initialize the URL connectivity tester
        
        Args:
            max_concurrent: Maximum concurrent connections
            default_timeout: Default timeout in seconds
            max_redirects: Maximum number of redirects to follow
            user_agent: User-Agent header to use
            retry_attempts: Number of retry attempts for failed requests
            circuit_breaker_threshold: Failures before opening circuit
            circuit_breaker_timeout: Seconds before retrying open circuit
            enable_ipv6: Enable IPv6 support
        """
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout or settings.REQUEST_TIMEOUT_S
        self.max_redirects = max_redirects
        self.user_agent = user_agent or settings.USER_AGENT
        self.retry_attempts = retry_attempts
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_timeout = circuit_breaker_timeout
        self.enable_ipv6 = enable_ipv6
        
        # Circuit breaker state per domain
        self._circuit_breakers: Dict[str, CircuitBreakerState] = defaultdict(CircuitBreakerState)
        
        # Semaphore for concurrent requests
        self._semaphore = asyncio.Semaphore(max_concurrent)
        
        # Connection pool settings
        self._connector_kwargs = {
            'limit': max_concurrent * 2,
            'limit_per_host': 5,
            'ttl_dns_cache': 300,
            'enable_cleanup_closed': True,
            'force_close': False,
            'keepalive_timeout': 30,
            'use_dns_cache': True,
        }
        
        if enable_ipv6:
            self._connector_kwargs['family'] = socket.AF_UNSPEC
        else:
            self._connector_kwargs['family'] = socket.AF_INET
            
        # SSL context for handling certificate issues
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = True
        self._ssl_context.verify_mode = ssl.CERT_REQUIRED
        
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower()
        
    def _check_circuit_breaker(self, domain: str) -> bool:
        """Check if circuit breaker allows request
        
        Returns:
            True if request is allowed, False if circuit is open
        """
        state = self._circuit_breakers[domain]
        
        if state.state == "closed":
            return True
            
        elif state.state == "open":
            if datetime.utcnow() >= state.next_retry:
                # Try half-open state
                state.state = "half-open"
                logger.info(f"Circuit breaker for {domain} entering half-open state")
                return True
            return False
            
        elif state.state == "half-open":
            return True
            
        return False
        
    def _record_success(self, domain: str):
        """Record successful request for circuit breaker"""
        state = self._circuit_breakers[domain]
        state.last_success = datetime.utcnow()
        state.failure_count = 0
        
        if state.state == "half-open":
            state.state = "closed"
            logger.info(f"Circuit breaker for {domain} closed after successful request")
            
    def _record_failure(self, domain: str):
        """Record failed request for circuit breaker"""
        state = self._circuit_breakers[domain]
        state.failure_count += 1
        state.last_failure = datetime.utcnow()
        
        if state.failure_count >= self.circuit_breaker_threshold:
            if state.state != "open":
                state.state = "open"
                state.next_retry = datetime.utcnow() + timedelta(seconds=self.circuit_breaker_timeout)
                logger.warning(
                    f"Circuit breaker for {domain} opened after {state.failure_count} failures. "
                    f"Next retry at {state.next_retry}"
                )
        elif state.state == "half-open":
            # Failed in half-open state, go back to open
            state.state = "open"
            state.next_retry = datetime.utcnow() + timedelta(seconds=self.circuit_breaker_timeout)
            logger.warning(f"Circuit breaker for {domain} reopened after failure in half-open state")
            
    async def _create_session(self) -> aiohttp.ClientSession:
        """Create aiohttp session with custom resolver and connector"""
        # Use AsyncResolver with aiodns for better DNS handling
        resolver = AsyncResolver()
        
        connector = aiohttp.TCPConnector(
            resolver=resolver,
            ssl=self._ssl_context,
            **self._connector_kwargs
        )
        
        timeout = ClientTimeout(
            total=self.default_timeout,
            connect=self.default_timeout / 2,
            sock_connect=self.default_timeout / 2,
            sock_read=self.default_timeout
        )
        
        return aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': self.user_agent}
        )
        
    async def _test_url_connectivity(
        self,
        session: aiohttp.ClientSession,
        url: str,
        timeout: float,
        follow_redirects: bool = True
    ) -> ConnectivityResult:
        """Test connectivity to a single URL
        
        Args:
            session: aiohttp session
            url: URL to test
            timeout: Timeout in seconds
            follow_redirects: Whether to follow redirects
            
        Returns:
            ConnectivityResult with detailed information
        """
        domain = self._get_domain(url)
        result = ConnectivityResult(url=url, reachable=False)
        
        # First, validate URL for SSRF protection
        is_safe, reason = validate_url_safety(url)
        if not is_safe:
            result.error_type = "SecurityError"
            result.error_message = f"URL blocked for security: {reason}"
            logger.warning(f"Blocked potentially unsafe URL: {url} - {reason}")
            return result
        
        # Check circuit breaker
        if not self._check_circuit_breaker(domain):
            result.error_type = "CircuitBreakerOpen"
            result.error_message = f"Circuit breaker is open for domain {domain}"
            logger.debug(f"Circuit breaker blocked request to {url}")
            return result
            
        start_time = time.time()
        
        # Custom timeout for this request
        custom_timeout = ClientTimeout(
            total=timeout,
            connect=timeout / 2,
            sock_connect=timeout / 2,
            sock_read=timeout
        )
        
        attempt = 0
        last_error = None
        
        while attempt <= self.retry_attempts:
            try:
                async with self._semaphore:
                    # Use HEAD request for lightweight testing
                    async with session.head(
                        url,
                        timeout=custom_timeout,
                        allow_redirects=follow_redirects,
                        ssl=self._ssl_context
                    ) as response:
                        # Record response details
                        result.status_code = response.status
                        result.response_time_ms = (time.time() - start_time) * 1000
                        result.final_url = str(response.url)
                        result.headers = dict(response.headers)
                        
                        # Get redirect chain
                        if response.history:
                            result.redirect_chain = [str(r.url) for r in response.history]
                            
                        # Get SSL info if HTTPS
                        if response.url.scheme == 'https':
                            try:
                                if hasattr(response, 'connection') and response.connection:
                                    if hasattr(response.connection, 'transport') and response.connection.transport:
                                        ssl_info = response.connection.transport.get_extra_info('ssl_object')
                                        if ssl_info:
                                            result.ssl_info = {
                                                'version': ssl_info.version(),
                                                'cipher': ssl_info.cipher(),
                                            }
                            except Exception as e:
                                logger.debug(f"Could not extract SSL info: {e}")
                                
                        # Get IP address
                        try:
                            if hasattr(response, 'connection') and response.connection:
                                if hasattr(response.connection, 'transport') and response.connection.transport:
                                    peername = response.connection.transport.get_extra_info('peername')
                                    if peername:
                                        result.ip_address = peername[0]
                        except Exception as e:
                            logger.debug(f"Could not extract IP address: {e}")
                            
                        # Consider successful if status < 500 (allow client errors like 404)
                        # Many 4xx pages have useful content (error pages, etc.)
                        if response.status < 500:
                            result.reachable = True
                            self._record_success(domain)
                            logger.debug(
                                f"URL {url} is reachable (status: {response.status}, "
                                f"time: {result.response_time_ms:.1f}ms)"
                            )
                        else:
                            result.error_type = "HTTPError"
                            result.error_message = f"HTTP {response.status}"
                            self._record_failure(domain)
                            logger.debug(f"URL {url} returned HTTP {response.status}")
                            
                        return result
                        
            except asyncio.TimeoutError:
                last_error = "Timeout"
                result.error_type = "Timeout"
                result.error_message = f"Request timed out after {timeout}s"
                logger.debug(f"Timeout testing {url} (attempt {attempt + 1})")
                
            except aiohttp.ClientConnectorError as e:
                last_error = "ConnectionError"
                result.error_type = "ConnectionError"
                if "Name or service not known" in str(e):
                    result.error_message = "DNS resolution failed"
                elif "Connection refused" in str(e):
                    result.error_message = "Connection refused"
                else:
                    result.error_message = str(e)
                logger.debug(f"Connection error for {url}: {e} (attempt {attempt + 1})")
                
            except aiohttp.ClientSSLError as e:
                last_error = "SSLError"
                result.error_type = "SSLError"
                result.error_message = f"SSL certificate error: {str(e)}"
                logger.debug(f"SSL error for {url}: {e}")
                break  # Don't retry SSL errors
                
            except aiohttp.ClientError as e:
                last_error = "ClientError"
                result.error_type = "ClientError"
                result.error_message = str(e)
                logger.debug(f"Client error for {url}: {e} (attempt {attempt + 1})")
                
            except Exception as e:
                last_error = "UnknownError"
                result.error_type = "UnknownError"
                result.error_message = str(e)
                logger.exception(f"Unexpected error testing {url}")
                break
                
            attempt += 1
            if attempt <= self.retry_attempts:
                # Exponential backoff
                await asyncio.sleep(2 ** (attempt - 1))
                
        # Record failure if all attempts failed
        if not result.reachable:
            self._record_failure(domain)
            result.response_time_ms = (time.time() - start_time) * 1000
            
        return result
        
    async def ping_url(self, url: str, timeout: float = None) -> bool:
        """Test if URL is reachable
        
        Args:
            url: URL to test
            timeout: Timeout in seconds (default: 5.0)
            
        Returns:
            True if reachable, False otherwise
        """
        timeout = timeout or self.default_timeout
        
        async with await self._create_session() as session:
            result = await self._test_url_connectivity(session, url, timeout)
            return result.reachable
            
    async def batch_ping_urls(
        self,
        urls: List[str],
        timeout: float = None
    ) -> Dict[str, bool]:
        """Async batch ping testing
        
        Args:
            urls: List of URLs to test
            timeout: Timeout per URL in seconds
            
        Returns:
            Dict mapping URL to reachability status
        """
        timeout = timeout or self.default_timeout
        results = {}
        
        async with await self._create_session() as session:
            tasks = [
                self._test_url_connectivity(session, url, timeout)
                for url in urls
            ]
            
            connectivity_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for url, result in zip(urls, connectivity_results):
                if isinstance(result, Exception):
                    logger.exception(f"Exception testing {url}: {result}")
                    results[url] = False
                else:
                    results[url] = result.reachable
                    
        return results
        
    async def is_url_reachable(
        self,
        url: str,
        timeout: float = None
    ) -> Dict[str, Any]:
        """Get detailed connectivity info for URL
        
        Args:
            url: URL to test
            timeout: Timeout in seconds
            
        Returns:
            Dict with detailed connectivity information
        """
        timeout = timeout or self.default_timeout
        
        async with await self._create_session() as session:
            result = await self._test_url_connectivity(session, url, timeout)
            
            return {
                'url': result.url,
                'reachable': result.reachable,
                'status_code': result.status_code,
                'response_time_ms': result.response_time_ms,
                'error_type': result.error_type,
                'error_message': result.error_message,
                'redirect_chain': result.redirect_chain,
                'final_url': result.final_url,
                'ip_address': result.ip_address,
                'ssl_info': result.ssl_info,
                'timestamp': result.timestamp.isoformat()
            }
            
    async def filter_reachable_urls(
        self,
        urls: List[str],
        timeout: float = None
    ) -> List[str]:
        """Return only reachable URLs from list
        
        Args:
            urls: List of URLs to test
            timeout: Timeout per URL in seconds
            
        Returns:
            List of reachable URLs
        """
        timeout = timeout or self.default_timeout
        reachable_urls = []
        
        async with await self._create_session() as session:
            tasks = [
                self._test_url_connectivity(session, url, timeout)
                for url in urls
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for url, result in zip(urls, results):
                if isinstance(result, Exception):
                    logger.exception(f"Exception testing {url}: {result}")
                elif result.reachable:
                    reachable_urls.append(url)
                    
        logger.info(f"Filtered {len(reachable_urls)} reachable URLs from {len(urls)} total")
        return reachable_urls
        
    def get_circuit_breaker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current circuit breaker status for all domains
        
        Returns:
            Dict mapping domain to circuit breaker state
        """
        status = {}
        for domain, state in self._circuit_breakers.items():
            status[domain] = {
                'state': state.state,
                'failure_count': state.failure_count,
                'last_failure': state.last_failure.isoformat() if state.last_failure else None,
                'last_success': state.last_success.isoformat() if state.last_success else None,
                'next_retry': state.next_retry.isoformat() if state.next_retry else None
            }
        return status
        
    def reset_circuit_breaker(self, domain: str = None):
        """Reset circuit breaker for domain or all domains
        
        Args:
            domain: Specific domain to reset, or None for all
        """
        if domain:
            if domain in self._circuit_breakers:
                del self._circuit_breakers[domain]
                logger.info(f"Reset circuit breaker for {domain}")
        else:
            self._circuit_breakers.clear()
            logger.info("Reset all circuit breakers")


# Convenience functions for synchronous usage
def ping_url_sync(url: str, timeout: float = 5.0) -> bool:
    """Synchronous wrapper for ping_url"""
    tester = URLConnectivityTester()
    return asyncio.run(tester.ping_url(url, timeout))


def batch_ping_urls_sync(urls: List[str], timeout: float = 5.0) -> Dict[str, bool]:
    """Synchronous wrapper for batch_ping_urls"""
    tester = URLConnectivityTester()
    return asyncio.run(tester.batch_ping_urls(urls, timeout))


def is_url_reachable_sync(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Synchronous wrapper for is_url_reachable"""
    tester = URLConnectivityTester()
    return asyncio.run(tester.is_url_reachable(url, timeout))


def filter_reachable_urls_sync(urls: List[str], timeout: float = 5.0) -> List[str]:
    """Synchronous wrapper for filter_reachable_urls"""
    tester = URLConnectivityTester()
    return asyncio.run(tester.filter_reachable_urls(urls, timeout))