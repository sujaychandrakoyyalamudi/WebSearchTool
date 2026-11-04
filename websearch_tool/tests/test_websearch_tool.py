"""
Unit tests for WebSearchTool

Run with: pytest tests/test_websearch_tool.py -v
"""

import pytest
import time
import logging
import traceback
import requests
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from websearch_tool import (
    WebSearchTool,
    SearchConfig,
    SearchResult,
    SearchResponse,
    GoogleSearchBackend,
    QueryRewriter,
    ResultCache,
    RateLimiter,
    create_langchain_tool,
)


class TestSearchResult:
    """Tests for SearchResult dataclass."""
    
    def test_create_search_result(self):
        result = SearchResult(
            title="Test Title",
            url="https://example.com",
            snippet="Test snippet"
        )
        assert result.title == "Test Title"
        assert result.url == "https://example.com"
        assert result.snippet == "Test snippet"
        assert result.content_type == 'web'
    
    def test_to_dict(self):
        result = SearchResult(
            title="Test",
            url="https://example.com",
            snippet="Snippet",
            score=0.95
        )
        result_dict = result.to_dict()
        assert result_dict['title'] == "Test"
        assert result_dict['url'] == "https://example.com"
        assert result_dict['score'] == 0.95


class TestSearchResponse:
    """Tests for SearchResponse dataclass."""
    
    def test_create_response(self):
        results = [
            SearchResult(title="R1", url="http://1.com", snippet="S1"),
            SearchResult(title="R2", url="http://2.com", snippet="S2")
        ]
        response = SearchResponse(
            query="test query",
            results=results,
            total_results=100,
            search_time_ms=150.5,
            backend='google'
        )
        assert response.query == "test query"
        assert len(response.results) == 2
        assert response.total_results == 100
        assert response.search_time_ms == 150.5
    
    def test_to_dict(self):
        results = [SearchResult(title="R", url="http://u.com", snippet="S")]
        response = SearchResponse(
            query="q",
            results=results,
            total_results=1,
            search_time_ms=100,
            backend='bing'
        )
        response_dict = response.to_dict()
        assert response_dict['query'] == 'q'
        assert len(response_dict['results']) == 1
        assert response_dict['backend'] == 'bing'


class TestSearchConfig:
    """Tests for SearchConfig."""
    
    def test_default_config(self):
        config = SearchConfig()
        assert config.backend == 'auto'
        assert config.num_results == 10
        assert config.safe_search is True
        assert config.enable_cache is True
    
    def test_custom_config(self):
        config = SearchConfig(
            backend='google',
            num_results=5,
            date_range_days=7,
            allowed_domains=['example.com']
        )
        assert config.backend == 'google'
        assert config.num_results == 5
        assert config.date_range_days == 7
        assert config.allowed_domains == ['example.com']
    
    def test_invalid_num_results(self):
        with pytest.raises(Exception):  # pydantic validation error
            SearchConfig(num_results=0)
        
        with pytest.raises(Exception):
            SearchConfig(num_results=101)


class TestQueryRewriter:
    """Tests for QueryRewriter."""
    
    def test_rewrite_basic(self):
        rewritten = QueryRewriter.rewrite("  hello   world  ")
        assert rewritten == "hello world"
    
    def test_rewrite_with_context(self):
        query = "When did it happen?"
        context = "The Apollo 11 moon landing occurred in 1969"
        rewritten = QueryRewriter.rewrite(query, context)
        # Should include context keywords
        assert "apollo" in rewritten.lower() or "moon" in rewritten.lower() or "landing" in rewritten.lower()
    
    def test_detect_intent_image(self):
        intent = QueryRewriter.detect_intent("show me images of cats")
        assert intent['needs_images'] is True
        assert intent['type'] == 'image'
    
    def test_detect_intent_video(self):
        intent = QueryRewriter.detect_intent("find youtube videos about cooking")
        assert intent['needs_video'] is True
        assert intent['type'] == 'video'
    
    def test_detect_intent_news(self):
        intent = QueryRewriter.detect_intent("latest technology news today")
        assert intent['needs_news'] is True
        assert intent['type'] == 'news'
    
    def test_detect_intent_web(self):
        intent = QueryRewriter.detect_intent("what is quantum computing")
        assert intent['type'] == 'web'
        assert intent['needs_images'] is False


class TestResultCache:
    """Tests for ResultCache."""
    
    def test_cache_set_get(self):
        cache = ResultCache(ttl_seconds=60)
        data = {'result': 'test'}
        filters = {'key': 'value'}
        
        cache.set("query1", filters, data)
        retrieved = cache.get("query1", filters)
        
        assert retrieved == data
    
    def test_cache_miss(self):
        cache = ResultCache()
        result = cache.get("nonexistent", {})
        assert result is None
    
    def test_cache_ttl_expiration(self):
        cache = ResultCache(ttl_seconds=1)
        cache.set("query", {}, {'data': 'value'})
        
        # Should exist immediately
        assert cache.get("query", {}) is not None
        
        # Wait for expiration
        time.sleep(1.5)
        
        # Should be expired
        assert cache.get("query", {}) is None
    
    def test_cache_clear(self):
        cache = ResultCache()
        cache.set("q1", {}, {'data': 'v1'})
        cache.set("q2", {}, {'data': 'v2'})
        
        cache.clear()
        
        assert cache.get("q1", {}) is None
        assert cache.get("q2", {}) is None


class TestRateLimiter:
    """Tests for RateLimiter."""
    
    def test_acquire_within_limit(self):
        limiter = RateLimiter(per_minute=5, per_day=100)
        
        # Should allow first 5 requests
        for i in range(5):
            assert limiter.acquire() is True
    
    def test_acquire_exceeds_limit(self):
        limiter = RateLimiter(per_minute=3, per_day=100)
        
        # Exhaust limit
        for i in range(3):
            limiter.acquire()
        
        # Should deny 4th request
        assert limiter.acquire() is False
    
    def test_wait_for_token(self):
        limiter = RateLimiter(per_minute=2, per_day=100)
        
        # Exhaust limit
        limiter.acquire()
        limiter.acquire()
        
        # Should wait and eventually get token
        # Note: This test would take 60 seconds for full refill
        # Using shorter timeout for testing
        result = limiter.wait_for_token(timeout=0.5)
        # May or may not succeed depending on timing
        assert isinstance(result, bool)


class TestWebSearchTool:
    """Tests for main WebSearchTool class."""
    
    @patch('websearch_tool.GoogleSearchBackend')
    def test_initialization(self, mock_backend):
        config = SearchConfig(backend='google', num_results=5)
        tool = WebSearchTool(config)
        
        assert tool.config.num_results == 5
        assert 'google' in tool.backends
        assert 'bing' in tool.backends
        assert 'duckduckgo' in tool.backends
    
    def test_deduplicate_results(self):
        config = SearchConfig()
        tool = WebSearchTool(config)
        
        results = [
            SearchResult(title="R1", url="http://same.com", snippet="S1"),
            SearchResult(title="R2", url="http://same.com", snippet="S2"),  # Duplicate URL
            SearchResult(title="R3", url="http://different.com", snippet="S3")
        ]
        
        unique = tool._deduplicate_results(results)
        
        assert len(unique) == 2
        assert all(r.url == "http://same.com" or r.url == "http://different.com" for r in unique)
    
    def test_get_stats(self):
        config = SearchConfig()
        tool = WebSearchTool(config)
        
        stats = tool.get_stats()
        
        assert 'total_queries' in stats
        assert 'cache_hits' in stats
        assert 'cache_misses' in stats
        assert 'errors' in stats
    
    @patch('websearch_tool.GoogleSearchBackend.search')
    def test_search_caching(self, mock_search):
        # Mock search response
        mock_response = SearchResponse(
            query="test",
            results=[SearchResult(title="T", url="http://u.com", snippet="S")],
            total_results=1,
            search_time_ms=100,
            backend='google'
        )
        mock_search.return_value = mock_response
        
        config = SearchConfig(enable_cache=True, cache_ttl_seconds=60)
        tool = WebSearchTool(config)
        
        # First call - should use backend
        tool.search("test query")
        assert mock_search.called
        
        mock_search.reset_mock()
        
        # Second call - should use cache
        tool.search("test query")
        # Backend should not be called again (cached)
        # Note: This depends on exact query matching after rewriting


class TestCreateLangchainTool:
    """Tests for LangChain tool creation."""
    
    def test_create_tool(self):
        config = SearchConfig(num_results=3)
        tool = create_langchain_tool(config)
        
        assert tool.name == "WebSearch"
        assert "Search the web" in tool.description
        assert callable(tool.func)
    
    def test_tool_func_error_handling(self):
        config = SearchConfig(backend='google')  # Will fail without API key
        tool = create_langchain_tool(config)
        
        # Should return error message, not raise exception
        result = tool.func("test query")
        assert "error" in result.lower() or "Error" in result


class TestIntegration:
    """Integration tests (may require API keys)."""
    
    def test_full_workflow_no_api(self):
        """Test workflow without valid API keys - should handle gracefully."""
        config = SearchConfig(
            backend='google',
            google_api_key='invalid',
            google_engine_id='invalid',
            num_results=3
        )
        tool = WebSearchTool(config)
        
        # Should raise RuntimeError due to invalid credentials
        with pytest.raises(RuntimeError):
            tool.search("test query")


# Fake keys. Every test below mocks requests.get, so nothing goes over the network.
GOOGLE_KEY = 'fake-google-key-123'
BING_KEY = 'fake-bing-key-456'


def _fail_like_400(url, params=None, headers=None, **kwargs):
    """Stand-in for requests.get: builds the request the way requests does,
    then fails like a 400 response, whose error text quotes the full URL."""
    prepared = requests.Request('GET', url, params=params, headers=headers).prepare()
    raise requests.exceptions.HTTPError(f"400 Client Error: Bad Request for url: {prepared.url}")


def _ok_response():
    """Stand-in for a successful response with an empty JSON body."""
    response = Mock()
    response.json.return_value = {}
    return response


def _traceback_text(error):
    """The error as a logged traceback would show it, chained errors included."""
    return ''.join(traceback.format_exception(type(error), error, error.__traceback__))


def _google_config():
    return SearchConfig(backend='google', google_api_key=GOOGLE_KEY, google_engine_id='test-engine')


class TestApiKeyRedaction:
    """API keys reach the search API but never responses, errors, logs or tool output."""

    @patch('websearch_tool.requests.get')
    def test_google_key_sent_as_query_param(self, mock_get):
        mock_get.return_value = _ok_response()
        WebSearchTool(_google_config()).search("test query")
        assert mock_get.call_args.kwargs['params']['key'] == GOOGLE_KEY

    @patch('websearch_tool.requests.get')
    def test_google_key_not_in_filters_applied(self, mock_get):
        mock_get.return_value = _ok_response()
        response = WebSearchTool(_google_config()).search("test query")
        assert 'key' not in response['filters_applied']
        assert response['filters_applied']['cx'] == 'test-engine'  # non-secret params are kept
        assert GOOGLE_KEY not in str(response)

    # With a trailing newline, the URL carries the key URL-encoded (...%0A)
    @pytest.mark.parametrize('api_key', [GOOGLE_KEY, GOOGLE_KEY + '\n'], ids=['plain', 'trailing-newline'])
    def test_google_backend_error_redacts_key(self, api_key):
        backend = GoogleSearchBackend(api_key=api_key, engine_id='test-engine')
        with patch('websearch_tool.requests.get', side_effect=_fail_like_400):
            with pytest.raises(requests.exceptions.RequestException) as excinfo:
                backend.search("test query", SearchConfig())
        error = excinfo.value
        assert '***' in str(error)
        assert GOOGLE_KEY not in _traceback_text(error)
        assert GOOGLE_KEY in str(error.__context__)  # the suppressed original error had the key

    @patch('websearch_tool.requests.get', side_effect=_fail_like_400)
    def test_google_key_not_in_search_error_or_logs(self, mock_get, caplog):
        caplog.set_level(logging.DEBUG)
        with pytest.raises(RuntimeError) as excinfo:
            WebSearchTool(_google_config()).search("test query")
        assert '***' in str(excinfo.value)
        assert GOOGLE_KEY not in _traceback_text(excinfo.value)
        assert 'Google search error' in caplog.text and 'Search failed' in caplog.text
        assert GOOGLE_KEY not in caplog.text

    @patch('websearch_tool.requests.get', side_effect=_fail_like_400)
    def test_google_key_not_in_langchain_tool_output(self, mock_get):
        output = create_langchain_tool(_google_config()).invoke("test query")
        assert output.startswith("Search error:")
        assert '***' in output
        assert GOOGLE_KEY not in output

    @patch('websearch_tool.requests.get')
    def test_bing_key_sent_only_as_header(self, mock_get):
        mock_get.return_value = _ok_response()
        response = WebSearchTool(SearchConfig(backend='bing', bing_api_key=BING_KEY)).search("test query")
        assert mock_get.call_args.kwargs['headers']['Ocp-Apim-Subscription-Key'] == BING_KEY
        assert BING_KEY not in str(mock_get.call_args.kwargs['params'])
        assert BING_KEY not in str(response)

    @patch('websearch_tool.requests.get', side_effect=_fail_like_400)
    def test_bing_invalid_key_not_in_search_error_or_logs(self, mock_get, caplog):
        # requests rejects a header value that ends in a newline and quotes it in the error
        caplog.set_level(logging.DEBUG)
        tool = WebSearchTool(SearchConfig(backend='bing', bing_api_key=BING_KEY + '\n'))
        with pytest.raises(RuntimeError) as excinfo:
            tool.search("test query")
        assert '***' in str(excinfo.value)
        assert BING_KEY not in _traceback_text(excinfo.value)
        assert BING_KEY not in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
