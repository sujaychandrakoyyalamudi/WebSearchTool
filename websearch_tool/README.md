# WebSearchTool for LangChain

A comprehensive, production-ready web search tool designed for seamless integration with LangChain AI agents and LLM applications.

## Features

### Core Functionality
- **Multiple Search Backends**: Google Custom Search, Bing Web Search, DuckDuckGo (fallback)
- **Query Intelligence**: Automatic query rewriting, spell correction hints, intent detection
- **Advanced Filtering**: Date range, domain allow/block lists, safe search, content type
- **Result Processing**: Snippet extraction, deduplication, confidence scoring, attribution
- **Multi-turn Context**: Conversation-aware search with context propagation

### Non-Functional Features
- **Performance**: In-memory caching with TTL, async-ready architecture
- **Reliability**: Automatic backend fallback, rate limiting, error handling
- **Security**: TLS encryption, API key management, no PII logging
- **Observability**: Built-in statistics, logging, monitoring hooks

### LangChain Integration
- Native `Tool` wrapper for agent frameworks (`langchain_core.tools.Tool`)
- RAG pipeline support
- Batch search capabilities
- Customizable result formatting

## Installation

```bash
pip install langchain langchain-core requests pydantic python-dotenv
```

Or with all dependencies:
```bash
cd websearch_tool
pip install -r requirements.txt
```

## Quick Start

### Basic Usage

```python
from websearch_tool import search

# Quick search with defaults
results = search("Python programming language", num_results=5)

print(f"Found {results['total_results']} results")
for result in results['results']:
    print(f"- {result['title']}: {result['url']}")
```

### With LangChain Agent

```python
from langchain.agents import initialize_agent, AgentType
from langchain_openai import ChatOpenAI
from websearch_tool import create_langchain_tool, SearchConfig

# Create search tool
search_tool = create_langchain_tool(
    SearchConfig(num_results=5, backend='auto')
)

# Setup agent
llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = initialize_agent(
    tools=[search_tool],
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# Use agent
response = agent.run("What are the latest developments in quantum computing?")
print(response)
```

### Advanced Configuration

```python
from websearch_tool import WebSearchTool, SearchConfig

config = SearchConfig(
    backend='google',  # or 'bing', 'duckduckgo', 'auto'
    num_results=10,
    safe_search=True,
    date_range_days=7,  # Last week only
    allowed_domains=['wikipedia.org', 'github.com'],
    enable_cache=True,
    cache_ttl_seconds=1800,
    language='en',
    country='us'
)

tool = WebSearchTool(config)
results = tool.search("machine learning frameworks")
```

## Configuration Options

### SearchConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `backend` | str | `'auto'` | Search backend: `'google'`, `'bing'`, `'duckduckgo'`, `'auto'` |
| `google_api_key` | str | `None` | Google Custom Search API key |
| `google_engine_id` | str | `None` | Google Programmable Search Engine ID |
| `bing_api_key` | str | `None` | Bing Web Search API key |
| `num_results` | int | `10` | Number of results to return (1-100) |
| `language` | str | `'en'` | Language code (e.g., `'en'`, `'fr'`, `'de'`) |
| `country` | str | `'us'` | Country code (e.g., `'us'`, `'uk'`, `'de'`) |
| `safe_search` | bool | `True` | Enable safe search filtering |
| `date_range_days` | int | `None` | Limit results to last N days |
| `allowed_domains` | List[str] | `None` | Only search these domains |
| `blocked_domains` | List[str] | `None` | Exclude these domains |
| `content_type` | str | `'web'` | Content type: `'web'`, `'image'`, `'video'`, `'news'` |
| `enable_cache` | bool | `True` | Enable result caching |
| `cache_ttl_seconds` | int | `3600` | Cache time-to-live in seconds |
| `rate_limit_per_minute` | int | `60` | Max requests per minute |
| `rate_limit_per_day` | int | `1000` | Max requests per day |
| `enable_query_rewriting` | bool | `True` | Auto-rewrite queries for better results |
| `enable_deduplication` | bool | `True` | Remove duplicate results |
| `timeout_seconds` | int | `10` | Request timeout |

## Environment Variables

Set these in your `.env` file or environment:

```bash
# Google Custom Search
GOOGLE_API_KEY=your_google_api_key
GOOGLE_ENGINE_ID=your_engine_id

# Bing Web Search
BING_API_KEY=your_bing_api_key

# Optional: Tool configuration
WEBSEARCH_BACKEND=auto
WEBSEARCH_NUM_RESULTS=10
WEBSEARCH_LANGUAGE=en
WEBSEARCH_COUNTRY=us
```

## API Reference

### WebSearchTool Class

#### `search(query: str, context: Optional[str] = None) -> Dict[str, Any]`

Perform a web search.

**Parameters:**
- `query`: Search query string
- `context`: Optional conversation context for multi-turn queries

**Returns:** Dictionary with:
- `query`: The search query
- `results`: List of search results
- `total_results`: Total matches found
- `search_time_ms`: Search duration
- `backend`: Backend used
- `filters_applied`: Applied filters

**Example:**
```python
tool = WebSearchTool()
results = tool.search("AI trends 2025")
```

#### `search_batch(queries: List[str], context: Optional[str] = None)`

Perform multiple searches in batch.

**Returns:** List of result dictionaries

#### `get_stats() -> Dict[str, Any]`

Get usage statistics (queries, cache hits, errors, etc.)

#### `clear_cache()`

Clear the result cache.

### SearchResult Dataclass

Each search result contains:
- `title`: Result title
- `url`: Source URL
- `snippet`: Text excerpt
- `score`: Relevance score (if available)
- `source`: Backend name ('google', 'bing', etc.)
- `published_date`: Publication date (if available)
- `image_url`: Image URL (for image searches)
- `content_type`: Type ('web', 'image', 'video', 'news')

## Examples

See `examples.py` for comprehensive usage examples including:
1. Basic standalone search
2. Custom configuration with filters
3. LangChain tool integration
4. Full agent setup
5. Multimodal search (images/video)
6. News search with freshness filter
7. Batch search
8. RAG integration pattern
9. Error handling and fallback
10. Caching behavior
11. Multi-turn conversation context

## Backend Comparison

| Feature | Google | Bing | DuckDuckGo |
|---------|--------|------|------------|
| Web Coverage | Excellent | Excellent | Limited |
| Image Search | ✓ | ✓ | ✗ |
| Date Filtering | ✓ | ✓ | ✗ |
| Domain Filter | ✓ | ✓ (via query) | ✗ |
| Safe Search | ✓ | ✓ | ✓ |
| Rate Limits | 100/day free | Tier-based | N/A |
| Pricing | $5/1K queries | Azure pricing | Free |

## Best Practices

### 1. API Key Management
```python
# Never hardcode keys
from dotenv import load_dotenv
load_dotenv()

config = SearchConfig()  # Reads from environment
```

### 2. Caching Strategy
```python
# Cache news for shorter time, general info longer
config = SearchConfig(
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour for general
)

# For news, use shorter TTL
config_news = SearchConfig(
    cache_ttl_seconds=300  # 5 minutes for news
)
```

### 3. Rate Limiting
```python
# Adjust based on your API tier
config = SearchConfig(
    rate_limit_per_minute=30,  # Conservative for free tier
    rate_limit_per_day=100
)
```

### 4. Error Handling
```python
try:
    results = tool.search(query)
except RuntimeError as e:
    logger.error(f"Search failed: {e}")
    # Implement fallback logic
```

### 5. Multi-turn Conversations
```python
# First query
result1 = tool.search("Who invented the telephone?")
context = result1['results'][0]['snippet']

# Follow-up with context
result2 = tool.search("When did he do it?", context=context)
```

## Architecture

```
User Query → Query Rewriter → Intent Detection → Backend Selection
                ↓                                      ↓
            Cache Check                          API Call
                ↓                                      ↓
            Cache Hit?                            Parse Results
                ↓                                      ↓
           Return Cached                        Deduplicate
                ↓                                      ↓
            Format Output ←--------------------- Cache Result
                ↓
            Return to User/LLM
```

## Security & Compliance

- **Encryption**: All API calls use HTTPS/TLS
- **Data Privacy**: No PII logging by default
- **GDPR/CCPA**: Compliant data handling practices
- **Rate Limiting**: Built-in protection against abuse
- **API Key Security**: Keys read from environment, never logged

## Troubleshooting

### "No valid search backend configured"
- Ensure API keys are set in environment or config
- Check that at least one backend has valid credentials

### Rate limit errors
- Increase `rate_limit_per_minute` if your API tier allows
- Enable caching to reduce API calls
- Implement exponential backoff in your application

### Poor search results
- Enable `enable_query_rewriting=True`
- Try different backend (`backend='bing'` vs `'google'`)
- Add domain restrictions for focused results

## Contributing

Contributions welcome! Areas for improvement:
- Additional search backends
- Enhanced query rewriting with ML models
- Redis integration for distributed caching
- More sophisticated intent detection
- Vision model integration for image results

## License

MIT License - See LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: Report bugs and feature requests
- Documentation: See examples.py for usage patterns

---

**Built for modern AI agents requiring real-time web knowledge.**
