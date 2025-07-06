"""Enhanced Web content extraction service with URL connectivity testing"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from .web_content import WebContentService
from .url_connectivity import URLConnectivityTester

logger = logging.getLogger(__name__)


class EnhancedWebContentService(WebContentService):
    """Enhanced web content service with connectivity pre-filtering"""
    
    def __init__(
        self,
        connectivity_tester: Optional[URLConnectivityTester] = None,
        pre_filter_urls: bool = True,
        connectivity_timeout: float = 5.0
    ):
        """Initialize enhanced web content service
        
        Args:
            connectivity_tester: URLConnectivityTester instance to use
            pre_filter_urls: Whether to pre-filter URLs for connectivity
            connectivity_timeout: Timeout for connectivity tests
        """
        super().__init__()
        self.connectivity_tester = connectivity_tester or URLConnectivityTester()
        self.pre_filter_urls = pre_filter_urls
        self.connectivity_timeout = connectivity_timeout
        
    async def extract_web_content_with_connectivity_check(
        self,
        urls: List[str],
        include_unreachable: bool = False
    ) -> List[Dict[str, Any]]:
        """Extract web content with connectivity pre-filtering
        
        Args:
            urls: List of URLs to extract content from
            include_unreachable: Whether to include unreachable URLs in results
            
        Returns:
            List of dictionaries containing URL content and connectivity info
        """
        results = []
        
        if self.pre_filter_urls:
            # Test connectivity for all URLs
            logger.info(f"Testing connectivity for {len(urls)} URLs")
            connectivity_results = await self.connectivity_tester.batch_ping_urls(
                urls, self.connectivity_timeout
            )
            
            reachable_urls = []
            for url in urls:
                if connectivity_results.get(url, False):
                    reachable_urls.append(url)
                elif include_unreachable:
                    # Add unreachable URL to results
                    results.append({
                        'url': url,
                        'reachable': False,
                        'error': 'URL is not reachable'
                    })
                    
            logger.info(
                f"Found {len(reachable_urls)} reachable URLs out of {len(urls)} total"
            )
            
            # Extract content only from reachable URLs
            if reachable_urls:
                content_results = await self.extract_web_content_async(reachable_urls)
                
                # Add reachability info to results
                for result in content_results:
                    result['reachable'] = True
                    
                results.extend(content_results)
        else:
            # Extract without pre-filtering
            results = await self.extract_web_content_async(urls)
            
        return results
        
    async def extract_with_detailed_connectivity(
        self,
        urls: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract web content with detailed connectivity information
        
        Args:
            urls: List of URLs to extract content from
            
        Returns:
            List of dictionaries with content and detailed connectivity info
        """
        results = []
        
        # Get detailed connectivity info for all URLs
        logger.info(f"Getting detailed connectivity info for {len(urls)} URLs")
        
        tasks = [
            self.connectivity_tester.is_url_reachable(url, self.connectivity_timeout)
            for url in urls
        ]
        
        connectivity_details = await asyncio.gather(*tasks, return_exceptions=True)
        
        reachable_urls = []
        url_connectivity_map = {}
        
        for url, detail in zip(urls, connectivity_details):
            if isinstance(detail, Exception):
                logger.exception(f"Error getting connectivity for {url}: {detail}")
                results.append({
                    'url': url,
                    'reachable': False,
                    'error': f'Connectivity test failed: {str(detail)}'
                })
            else:
                url_connectivity_map[url] = detail
                if detail['reachable']:
                    reachable_urls.append(url)
                else:
                    results.append({
                        'url': url,
                        'reachable': False,
                        'connectivity': detail,
                        'error': f"{detail['error_type']}: {detail['error_message']}"
                    })
                    
        # Extract content from reachable URLs
        if reachable_urls:
            content_results = await self.extract_web_content_async(reachable_urls)
            
            # Merge content and connectivity data
            for result in content_results:
                url = result['url']
                result['reachable'] = True
                result['connectivity'] = url_connectivity_map.get(url, {})
                results.append(result)
                
        return results
        
    def extract_web_content(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Override to add synchronous connectivity checking
        
        Args:
            urls: List of URLs to extract content from
            
        Returns:
            List of dictionaries containing URL content
        """
        if self.pre_filter_urls:
            # Run async connectivity check synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                reachable_urls = loop.run_until_complete(
                    self.connectivity_tester.filter_reachable_urls(
                        urls, self.connectivity_timeout
                    )
                )
                
                logger.info(
                    f"Pre-filtered to {len(reachable_urls)} reachable URLs "
                    f"from {len(urls)} total"
                )
                
                # Extract content only from reachable URLs
                return super().extract_web_content(reachable_urls)
            finally:
                loop.close()
        else:
            return super().extract_web_content(urls)
            
    def get_circuit_breaker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get circuit breaker status from connectivity tester
        
        Returns:
            Circuit breaker status for all domains
        """
        return self.connectivity_tester.get_circuit_breaker_status()
        
    def reset_circuit_breakers(self, domain: str = None):
        """Reset circuit breakers
        
        Args:
            domain: Specific domain to reset, or None for all
        """
        self.connectivity_tester.reset_circuit_breaker(domain)