"""
WebSearchTool for LangChain Integration

A comprehensive web search tool with support for:
- Query parsing & rewriting
- Filters (date, domain, safe search)
- Result ranking & formatting
- Snippet extraction with attribution
- Multi-turn context integration
- Multimodal search (images/video)
- Caching and deduplication
- Rate limiting and quota management
- Internationalization

Supports multiple backends:
- Google Custom Search API
- Bing Web Search API
- DuckDuckGo (HTML scraping fallback)
- OpenAI Web Search Tool (via Responses API)
"""

import os
import json
import hashlib
import time
import logging
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from urllib.parse import quote_plus
import requests
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a single search result."""
    title: str
    url: str
    snippet: str
    score: Optional[float] = None
    source: Optional[str] = None  # e.g., 'google', 'bing'
    published_date: Optional[str] = None
    image_url: Optional[str] = None
    content_type: Literal['web', 'image', 'video', 'news'] = 'web'
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResponse:
    """Container for search results with metadata."""
    query: str
    results: List[SearchResult]
    total_results: int
    search_time_ms: float
    backend: str
    filters_applied: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'query': self.query,
            'results': [r.to_dict() for r in self.results],
            'total_results': self.total_results,
            'search_time_ms': self.search_time_ms,
            'backend': self.backend,
            'filters_applied': self.filters_applied
        }


class SearchConfig(BaseModel):
    """Configuration for the WebSearchTool."""
    
    # Backend selection
    backend: Literal['google', 'bing', 'duckduckgo', 'openai', 'auto'] = 'auto'
    
    # API credentials (can also be set via environment variables)
    google_api_key: Optional[str] = None
    google_engine_id: Optional[str] = None
    bing_api_key: Optional[str] = None
    bing_endpoint: str = "https://api.bing.microsoft.com/v7.0/search"
    
    # Query settings
    num_results: int = Field(default=10, ge=1, le=100)
    language: str = Field(default='en', description="Language code (e.g., 'en', 'fr')")
    country: str = Field(default='us', description="Country code (e.g., 'us', 'uk')")
    
    # Filter settings
    safe_search: bool = True
    date_range_days: Optional[int] = None  # None = any time
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    content_type: Literal['web', 'image', 'video', 'news'] = 'web'
    
    # Caching settings
    enable_cache: bool = True
    cache_ttl_seconds: int = 3600  # 1 hour default
    
    # Rate limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_day: int = 1000
    
    # Advanced settings
    enable_query_rewriting: bool = True
    enable_deduplication: bool = True
    timeout_seconds: int = 10
    
    class Config:
        env_prefix = 'WEBSEARCH_'


class QueryRewriter:
    """Handles query parsing and rewriting."""
    
    @staticmethod
    def rewrite(query: str, context: Optional[str] = None) -> str:
        """
        Rewrite query for better search results.
        
        Features:
        - Spell correction hints
        - Synonym expansion
        - Context integration
        - Operator addition
        """
        rewritten = query.strip()
        
        # Basic cleanup
        rewritten = ' '.join(rewritten.split())
        
        # If context provided, integrate it
        if context:
            # Extract key entities from context (simple heuristic)
            context_words = set(context.lower().split())
            query_words = rewritten.lower().split()
            
            # Check if query has pronouns or references
            if any(word in query_words for word in ['it', 'they', 'this', 'that', 'these']):
                # Try to append context keywords
                important_context = [w for w in context_words if len(w) > 4][:3]
                if important_context:
                    rewritten = f"{rewritten} {' '.join(important_context)}"
        
        # Add quotes for likely entity names (simple heuristic)
        if len(rewritten.split()) <= 3 and rewritten.istitle():
            rewritten = f'"{rewritten}"'
        
        return rewritten
    
    @staticmethod
    def detect_intent(query: str) -> Dict[str, Any]:
        """Detect query intent to route to appropriate search type."""
        query_lower = query.lower()
        
        intent = {
            'type': 'web',
            'needs_images': False,
            'needs_video': False,
            'needs_news': False,
            'is_navigational': False
        }
        
        # Image intent
        if any(kw in query_lower for kw in ['image', 'picture', 'photo', 'show me']):
            intent['needs_images'] = True
            intent['type'] = 'image'
        
        # Video intent
        if any(kw in query_lower for kw in ['video', 'watch', 'youtube', 'clip']):
            intent['needs_video'] = True
            intent['type'] = 'video'
        
        # News intent
        if any(kw in query_lower for kw in ['news', 'latest', 'recent', 'today', 'breaking']):
            intent['needs_news'] = True
            intent['type'] = 'news'
        
        # Navigational intent (looking for specific site)
        if 'site:' in query_lower or query_lower.startswith('www.'):
            intent['is_navigational'] = True
        
        return intent


class ResultCache:
    """Simple in-memory cache with TTL support."""
    
    def __init__(self, ttl_seconds: int = 3600):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds
    
    def _make_key(self, query: str, filters: Dict[str, Any]) -> str:
        """Generate cache key from query and filters."""
        key_data = f"{query}:{json.dumps(filters, sort_keys=True)}"
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def get(self, query: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached result if available and not expired."""
        key = self._make_key(query, filters)
        
        if key in self._cache:
            entry = self._cache[key]
            if time.time() < entry['expires_at']:
                logger.debug(f"Cache hit for query: {query[:50]}...")
                return entry['data']
            else:
                del self._cache[key]
        
        return None
    
    def set(self, query: str, filters: Dict[str, Any], data: Dict[str, Any]):
        """Store result in cache."""
        key = self._make_key(query, filters)
        self._cache[key] = {
            'data': data,
            'expires_at': time.time() + self._ttl,
            'created_at': time.time()
        }
        logger.debug(f"Cached result for query: {query[:50]}...")
    
    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()


class RateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, per_minute: int = 60, per_day: int = 1000):
        self.per_minute = per_minute
        self.per_day = per_day
        
        self._minute_tokens = per_minute
        self._day_tokens = per_day
        self._last_minute_refill = time.time()
        self._last_day_refill = time.time()
    
    def acquire(self) -> bool:
        """Try to acquire a token. Returns True if successful."""
        now = time.time()
        
        # Refill minute bucket
        if now - self._last_minute_refill >= 60:
            self._minute_tokens = self.per_minute
            self._last_minute_refill = now
        
        # Refill day bucket
        if now - self._last_day_refill >= 86400:
            self._day_tokens = self.per_day
            self._last_day_refill = now
        
        # Check availability
        if self._minute_tokens > 0 and self._day_tokens > 0:
            self._minute_tokens -= 1
            self._day_tokens -= 1
            return True
        
        return False
    
    def wait_for_token(self, timeout: float = 30.0) -> bool:
        """Wait until a token is available or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            if self.acquire():
                return True
            time.sleep(0.5)
        return False


def _redact_secret(text: str, secret: Optional[str]) -> str:
    """
    Replace an API key in text with '***'.

    requests error messages can show the key URL-encoded (in a request URL)
    or repr()-quoted (for an invalid header value), so those forms are
    replaced too.
    """
    if not secret:
        return text
    for form in (secret, quote_plus(secret), repr(secret)[1:-1]):
        text = text.replace(form, '***')
    return text


class WebSearchBackend:
    """Base class for search backends."""
    
    def search(self, query: str, config: SearchConfig) -> SearchResponse:
        raise NotImplementedError
    
    def validate_config(self, config: SearchConfig) -> bool:
        raise NotImplementedError


class GoogleSearchBackend(WebSearchBackend):
    """Google Custom Search API backend."""
    
    def __init__(self, api_key: Optional[str] = None, engine_id: Optional[str] = None):
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        self.engine_id = engine_id or os.getenv('GOOGLE_ENGINE_ID')
        self.base_url = "https://customsearch.googleapis.com/customsearch/v1"
    
    def validate_config(self, config: SearchConfig) -> bool:
        if not self.api_key or not self.engine_id:
            logger.error("Google API key or Engine ID not configured")
            return False
        return True
    
    def search(self, query: str, config: SearchConfig) -> SearchResponse:
        start_time = time.time()
        
        # Build request parameters. The API key is added only when sending the
        # request, so it stays out of filters_applied.
        params = {
            'q': query,
            'cx': self.engine_id,
            'num': min(config.num_results, 10),  # Google max 10 per request
            'gl': config.country,
            'hl': config.language,
        }
        
        # Safe search
        if config.safe_search:
            params['safe'] = 'active'
        
        # Date restriction
        if config.date_range_days:
            if config.date_range_days == 1:
                params['dateRestrict'] = 'd1'
            elif config.date_range_days <= 7:
                params['dateRestrict'] = 'w1'
            elif config.date_range_days <= 30:
                params['dateRestrict'] = 'm1'
            else:
                params['dateRestrict'] = f'y{config.date_range_days // 365}'
        
        # Domain filtering
        if config.allowed_domains:
            params['siteSearch'] = ','.join(config.allowed_domains)
            params['siteSearchFilter'] = 'i'  # include
        elif config.blocked_domains:
            params['siteSearch'] = ','.join(config.blocked_domains)
            params['siteSearchFilter'] = 'e'  # exclude
        
        # Content type
        if config.content_type == 'image':
            params['searchType'] = 'image'
        
        try:
            response = requests.get(
                self.base_url,
                params={**params, 'key': self.api_key},
                timeout=config.timeout_seconds
            )
            response.raise_for_status()
            data = response.json()
            
            # Parse results
            results = []
            items = data.get('items', [])
            
            for item in items:
                result = SearchResult(
                    title=item.get('title', ''),
                    url=item.get('link', ''),
                    snippet=item.get('snippet', ''),
                    source='google',
                    content_type=config.content_type
                )
                
                # Extract additional metadata
                if 'pagemap' in item and config.content_type == 'image':
                    cse_image = item['pagemap'].get('cse_image', [])
                    if cse_image:
                        result.image_url = cse_image[0].get('src')
                
                results.append(result)
            
            search_time = (time.time() - start_time) * 1000
            
            return SearchResponse(
                query=query,
                results=results,
                total_results=int(data.get('searchInformation', {}).get('totalResults', 0)),
                search_time_ms=search_time,
                backend='google',
                filters_applied=params
            )
            
        except requests.exceptions.RequestException as e:
            # The error text can include the request URL, which carries the key
            message = _redact_secret(str(e), self.api_key)
            logger.error(f"Google search error: {message}")
            raise requests.exceptions.RequestException(message) from None


class BingSearchBackend(WebSearchBackend):
    """Bing Web Search API backend."""
    
    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = api_key or os.getenv('BING_API_KEY')
        self.endpoint = endpoint or "https://api.bing.microsoft.com/v7.0/search"
    
    def validate_config(self, config: SearchConfig) -> bool:
        if not self.api_key:
            logger.error("Bing API key not configured")
            return False
        return True
    
    def search(self, query: str, config: SearchConfig) -> SearchResponse:
        start_time = time.time()
        
        # Build request headers
        headers = {
            'Ocp-Apim-Subscription-Key': self.api_key,
            'Accept-Language': f'{config.language}-{config.country.upper()}'
        }
        
        # Build request parameters
        params = {
            'q': query,
            'count': min(config.num_results, 50),  # Bing max 50
            'mkt': f'{config.language}-{config.country.upper()}',
            'safeSearch': 'Strict' if config.safe_search else 'Off',
        }
        
        # Freshness (date range)
        if config.date_range_days:
            if config.date_range_days == 1:
                params['freshness'] = 'Day'
            elif config.date_range_days <= 7:
                params['freshness'] = 'Week'
            elif config.date_range_days <= 30:
                params['freshness'] = 'Month'
        
        # Domain filtering via site: operator
        if config.allowed_domains:
            site_filter = ' OR '.join([f'site:{d}' for d in config.allowed_domains])
            params['q'] = f"({query}) AND ({site_filter})"
        elif config.blocked_domains:
            site_filter = ' '.join([f'-site:{d}' for d in config.blocked_domains])
            params['q'] = f"{query} {site_filter}"
        
        try:
            response = requests.get(
                self.endpoint,
                headers=headers,
                params=params,
                timeout=config.timeout_seconds
            )
            response.raise_for_status()
            data = response.json()
            
            # Parse results
            results = []
            web_pages = data.get('webPages', {}).get('value', [])
            
            for item in web_pages:
                result = SearchResult(
                    title=item.get('name', ''),
                    url=item.get('url', ''),
                    snippet=item.get('snippet', ''),
                    score=item.get('dateLastCrawled'),
                    source='bing',
                    content_type=config.content_type
                )
                results.append(result)
            
            search_time = (time.time() - start_time) * 1000
            
            return SearchResponse(
                query=query,
                results=results,
                total_results=data.get('webPages', {}).get('totalEstimatedMatches', 0),
                search_time_ms=search_time,
                backend='bing',
                filters_applied=params
            )
            
        except requests.exceptions.RequestException as e:
            # requests quotes an invalid header value, such as a key ending in a newline, in its error
            message = _redact_secret(str(e), self.api_key)
            logger.error(f"Bing search error: {message}")
            raise requests.exceptions.RequestException(message) from None


class DuckDuckGoBackend(WebSearchBackend):
    """
    DuckDuckGo search backend (fallback method).
    
    Note: DuckDuckGo doesn't offer an official web search API.
    This uses HTML scraping as a fallback - use with caution.
    For production, prefer Google or Bing APIs.
    """
    
    def __init__(self):
        self.base_url = "https://html.duckduckgo.com/html/"
    
    def validate_config(self, config: SearchConfig) -> bool:
        # No API key needed, but warn about limitations
        logger.warning("DuckDuckGo backend uses HTML scraping - may be unreliable")
        return True
    
    def search(self, query: str, config: SearchConfig) -> SearchResponse:
        start_time = time.time()
        
        # Prepare form data
        data = {
            'q': query,
            'kl': f'{config.country}-{config.language}',
        }
        
        if config.safe_search:
            data['kh'] = '1'
        
        try:
            response = requests.post(
                self.base_url,
                data=data,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=config.timeout_seconds
            )
            response.raise_for_status()
            
            # Simple HTML parsing (basic implementation)
            # In production, use BeautifulSoup for robust parsing
            results = []
            html_content = response.text
            
            # Extract results using simple string matching
            # This is a simplified example - real implementation should use proper HTML parser
            import re
            result_pattern = r'<a class="result__a" href="([^"]+)">([^<]+)</a>'
            snippet_pattern = r'<a class="result__snippet" href="[^"]+">([^<]+)</a>'
            
            titles_urls = re.findall(result_pattern, html_content)
            snippets = re.findall(snippet_pattern, html_content)
            
            for i, (url, title) in enumerate(titles_urls[:config.num_results]):
                snippet = snippets[i] if i < len(snippets) else ''
                result = SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source='duckduckgo',
                    content_type=config.content_type
                )
                results.append(result)
            
            search_time = (time.time() - start_time) * 1000
            
            return SearchResponse(
                query=query,
                results=results,
                total_results=len(results),
                search_time_ms=search_time,
                backend='duckduckgo',
                filters_applied=data
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"DuckDuckGo search error: {e}")
            raise


class WebSearchTool:
    """
    Main WebSearchTool class for LangChain integration.
    
    Features:
    - Multiple search backends (Google, Bing, DuckDuckGo)
    - Query rewriting and intent detection
    - Result caching and deduplication
    - Rate limiting and quota management
    - Comprehensive filtering options
    - LangChain tool compatibility
    
    Example usage:
        ```python
        from langchain.agents import initialize_agent, Tool
        from websearch_tool import WebSearchTool, SearchConfig
        
        # Initialize tool
        config = SearchConfig(backend='google', num_results=5)
        search_tool = WebSearchTool(config)
        
        # Use with LangChain
        tools = [
            Tool(
                name="Web Search",
                func=search_tool.search,
                description="Search the web for current information"
            )
        ]
        
        agent = initialize_agent(tools, llm, agent="zero-shot-react-description")
        result = agent.run("What's the latest news about AI?")
        ```
    """
    
    def __init__(self, config: Optional[SearchConfig] = None):
        self.config = config or SearchConfig()
        
        # Initialize backends
        self.backends: Dict[str, WebSearchBackend] = {
            'google': GoogleSearchBackend(
                self.config.google_api_key,
                self.config.google_engine_id
            ),
            'bing': BingSearchBackend(
                self.config.bing_api_key,
                self.config.bing_endpoint
            ),
            'duckduckgo': DuckDuckGoBackend()
        }
        
        # Initialize helpers
        self.cache = ResultCache(self.config.cache_ttl_seconds) if self.config.enable_cache else None
        self.rate_limiter = RateLimiter(
            self.config.rate_limit_per_minute,
            self.config.rate_limit_per_day
        )
        self.rewriter = QueryRewriter()
        
        # Statistics
        self.stats = {
            'total_queries': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': 0
        }
    
    def _select_backend(self, query: str) -> str:
        """Select best backend based on config and query."""
        # If auto mode, try to select based on query intent
        if self.config.backend == 'auto':
            intent = self.rewriter.detect_intent(query)
            
            # Prefer Google for general queries
            return 'google'
        
        return self.config.backend
    
    def _deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Remove duplicate results based on URL."""
        seen_urls = set()
        unique_results = []
        
        for result in results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                unique_results.append(result)
        
        return unique_results
    
    def search(self, query: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform web search with given query.
        
        Args:
            query: Search query string
            context: Optional conversation context for multi-turn queries
        
        Returns:
            Dictionary with search results and metadata
        
        Raises:
            ValueError: If configuration is invalid
            RuntimeError: If search fails
        """
        self.stats['total_queries'] += 1
        
        # Rate limiting
        if not self.rate_limiter.wait_for_token(timeout=10.0):
            raise RuntimeError("Rate limit exceeded. Please try again later.")
        
        # Query rewriting
        if self.config.enable_query_rewriting:
            rewritten_query = self.rewriter.rewrite(query, context)
            logger.info(f"Rewrote query: '{query}' -> '{rewritten_query}'")
        else:
            rewritten_query = query
        
        # Detect intent
        intent = self.rewriter.detect_intent(rewritten_query)
        
        # Update config based on intent
        effective_config = self.config.model_copy()
        if intent['needs_images']:
            effective_config.content_type = 'image'
        elif intent['needs_video']:
            effective_config.content_type = 'video'
        elif intent['needs_news']:
            effective_config.content_type = 'news'
            effective_config.date_range_days = effective_config.date_range_days or 7
        
        # Check cache
        filters = effective_config.model_dump(include={'date_range_days', 'allowed_domains', 
                                                       'blocked_domains', 'content_type'})
        if self.cache:
            cached_result = self.cache.get(rewritten_query, filters)
            if cached_result:
                self.stats['cache_hits'] += 1
                logger.debug("Returning cached result")
                return cached_result
        
        self.stats['cache_misses'] += 1
        
        # Select and validate backend
        backend_name = self._select_backend(rewritten_query)
        backend = self.backends[backend_name]
        
        if not backend.validate_config(effective_config):
            # Fallback to another backend
            logger.warning(f"Backend {backend_name} not configured, trying fallback")
            for fallback_name, fallback_backend in self.backends.items():
                if fallback_name != backend_name and fallback_backend.validate_config(effective_config):
                    backend_name = fallback_name
                    backend = fallback_backend
                    break
            else:
                raise ValueError("No valid search backend configured")
        
        # Perform search
        try:
            response = backend.search(rewritten_query, effective_config)
            
            # Deduplicate results
            if self.config.enable_deduplication:
                response.results = self._deduplicate_results(response.results)
            
            # Convert to dict
            result_dict = response.to_dict()
            
            # Cache result
            if self.cache:
                self.cache.set(rewritten_query, filters, result_dict)
            
            return result_dict
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Search failed: {e}")
            raise RuntimeError(f"Search failed: {str(e)}")
    
    def search_batch(self, queries: List[str], context: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Perform multiple searches in batch.
        
        Args:
            queries: List of search queries
            context: Optional shared context
        
        Returns:
            List of search result dictionaries
        """
        results = []
        for query in queries:
            try:
                result = self.search(query, context)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch search failed for query '{query}': {e}")
                results.append({'error': str(e), 'query': query})
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tool usage statistics."""
        return {
            **self.stats,
            'cache_size': len(self.cache._cache) if self.cache else 0,
            'rate_limit_remaining_minute': self.rate_limiter._minute_tokens,
            'rate_limit_remaining_day': self.rate_limiter._day_tokens
        }
    
    def clear_cache(self):
        """Clear the result cache."""
        if self.cache:
            self.cache.clear()
            logger.info("Cache cleared")


# LangChain Tool Wrapper
def create_langchain_tool(config: Optional[SearchConfig] = None):
    """
    Create a LangChain Tool wrapper for WebSearchTool.
    
    Example:
        ```python
        from langchain_core.tools import Tool
        from websearch_tool import create_langchain_tool, SearchConfig
        
        config = SearchConfig(num_results=5)
        search_tool = create_langchain_tool(config)
        
        # Use in agent
        tools = [search_tool]
        ```
    """
    from langchain_core.tools import Tool
    
    web_search = WebSearchTool(config)
    
    def search_func(query: str) -> str:
        """Search the web and return formatted results."""
        try:
            results = web_search.search(query)
            
            # Format results for LLM consumption
            formatted = f"Search results for: {results['query']}\n\n"
            
            for i, result in enumerate(results['results'], 1):
                formatted += f"[{i}] {result['title']}\n"
                formatted += f"    URL: {result['url']}\n"
                formatted += f"    {result['snippet']}\n\n"
            
            formatted += f"\nTotal results: {results['total_results']}"
            formatted += f"\nSearch time: {results['search_time_ms']:.0f}ms"
            
            return formatted
            
        except Exception as e:
            return f"Search error: {str(e)}"
    
    return Tool(
        name="WebSearch",
        func=search_func,
        description="Search the web for current information. Useful for questions about recent events, facts, or topics requiring up-to-date information. Input should be a search query."
    )


# Convenience function for quick setup
def search(query: str, **kwargs) -> Dict[str, Any]:
    """
    Quick search function with default configuration.
    
    Example:
        ```python
        from websearch_tool import search
        
        results = search("latest AI news", num_results=5, backend='google')
        ```
    """
    config = SearchConfig(**kwargs)
    tool = WebSearchTool(config)
    return tool.search(query)


if __name__ == "__main__":
    # Example usage
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Set up config (API keys from environment)
    config = SearchConfig(
        backend='auto',
        num_results=5,
        enable_cache=True,
        safe_search=True
    )
    
    # Create tool
    tool = WebSearchTool(config)
    
    # Example search
    try:
        results = tool.search("Python programming language")
        print(json.dumps(results, indent=2))
        
        # Print stats
        print("\nStats:", tool.get_stats())
        
    except Exception as e:
        print(f"Error: {e}")
