# WebSearchTool

A Python web search wrapper for LangChain that queries Google Custom Search, Bing Web Search or DuckDuckGo and returns the results as dictionaries.

## What it does

For each query, `WebSearchTool.search()`:

1. takes a slot from a client-side rate limiter,
2. optionally rewrites the query,
3. sets the content type from keywords in the query,
4. returns a cached response if there is one,
5. otherwise sends the query to one backend and drops duplicate URLs,
6. returns a dict with `query`, `results`, `total_results`, `search_time_ms`, `backend` and `filters_applied`.

Each result has `title`, `url`, `snippet` and `source` (the backend name). `create_langchain_tool()` wraps the same call as a LangChain `Tool` that returns the results as text.

## Features

- Backends: Google Custom Search JSON API, Bing Web Search API v7, and DuckDuckGo's HTML results page, parsed with regular expressions. `backend='auto'` (the default) uses Google. Microsoft retired the Bing Search APIs on August 11, 2025, so the Bing backend no longer works. Google's Custom Search JSON API is closed to new customers and will be discontinued on January 1, 2027. After that date, DuckDuckGo scraping is the only backend expected to keep working (see [Safety and limits](#safety-and-limits)).
- Fallback for missing credentials: if the selected backend is missing its credentials, the tool uses the first other backend that has them, in the order Google, Bing, DuckDuckGo (which needs no key). A request that fails is not retried on another backend.
- Filters: `safe_search`, `date_range_days`, `allowed_domains` and `blocked_domains` (Google and Bing only), and `content_type` (only `'image'` on Google changes the request; other values only label the results).
- Query rewriting: collapses whitespace, quotes title-case queries of up to three words, and, when you pass `context` and the query contains `it`, `they`, `this`, `that` or `these`, appends up to three words from the context.
- Keyword intent detection: words such as "image", "video" or "news" in the query switch `content_type`; news queries also get a 7-day date range if none is set.
- Deduplication of results by exact URL.
- In-memory cache with a TTL per entry.
- Client-side rate limits per minute and per day.
- Counters from `get_stats()`: queries, cache hits and misses, errors, cache size and remaining rate-limit slots.
- Batch search: `search_batch()` runs queries one after another and returns an error entry for each failed query.
- LangChain: `create_langchain_tool()` returns a `langchain_core.tools.Tool` named `WebSearch`.

## Install

WebSearchTool is not on PyPI and has no `setup.py` or `pyproject.toml`. Clone the repository and install the requirements:

```bash
git clone https://github.com/sujaychandrakoyyalamudi/WebSearchTool.git
cd WebSearchTool
pip install -r websearch_tool/requirements.txt
```

Run Python from the repository root (or add it to `PYTHONPATH`) so that `import websearch_tool` finds the package.

## Quick start

Set credentials for at least one API backend. Without them, every search falls back to DuckDuckGo scraping, which can return no results.

```bash
export GOOGLE_API_KEY="..."     # Custom Search JSON API key
export GOOGLE_ENGINE_ID="..."   # Programmable Search Engine ID
```

```python
from websearch_tool import WebSearchTool, SearchConfig, create_langchain_tool

tool = WebSearchTool(SearchConfig(num_results=5))
response = tool.search("Python packaging guide")
print(response["backend"], response["total_results"])
for result in response["results"]:
    print(result["title"], result["url"])

# LangChain Tool named "WebSearch" that returns the results as text
search_tool = create_langchain_tool(SearchConfig(num_results=3))
print(search_tool.invoke("pydantic v2 migration guide"))
```

For a one-off call, `search(query, **config_fields)` builds a new `SearchConfig` and `WebSearchTool` and runs one search.

## Configuration

Pass a `SearchConfig` (a pydantic model) to `WebSearchTool` or `create_langchain_tool`. Commonly used fields:

| Field | Default | Effect |
|---|---|---|
| `backend` | `'auto'` | `'google'`, `'bing'`, `'duckduckgo'` or `'auto'` (Google first) |
| `num_results` | `10` | 1 to 100; Google returns at most 10 and Bing at most 50 per call |
| `safe_search` | `True` | Google `safe=active`, Bing `safeSearch=Strict`; DuckDuckGo is covered in the detailed README |
| `date_range_days` | `None` | Mapped to day, week or month buckets (and years on Google) |
| `allowed_domains`, `blocked_domains` | `None` | Google and Bing only; if both are set, only `allowed_domains` applies |
| `enable_cache`, `cache_ttl_seconds` | `True`, `3600` | In-memory cache per tool instance |
| `rate_limit_per_minute`, `rate_limit_per_day` | `60`, `1000` | Client-side limits per tool instance |
| `timeout_seconds` | `10` | HTTP timeout in seconds |

The [detailed README](websearch_tool/README.md#configuration) lists every field.

The code reads three environment variables: `GOOGLE_API_KEY`, `GOOGLE_ENGINE_ID` and `BING_API_KEY`, each used only when the matching `SearchConfig` field is empty. The package does not load `.env` files; call `load_dotenv()` from `python-dotenv` first if you keep keys there.

## Safety and limits

- Logging: importing the package calls `logging.basicConfig(level=logging.INFO)`, and every search logs the original and rewritten query at INFO level. Queries can contain personal data, so configure logging accordingly.
- API keys: the Google key is sent as the `key` URL query parameter and the Bing key in a request header; neither is included in `filters_applied`. If a request fails, the key is replaced with `***` in the error message and the original exception is not chained, so the key stays out of this package's log lines, the raised `RuntimeError` and the LangChain tool's output, which goes to the model. urllib3, which `requests` uses, logs each request URL at DEBUG level, including the Google `key` parameter, so keep urllib3 DEBUG logging off in production.
- Rate limits and the cache live in memory per `WebSearchTool` instance. When a limit is reached, `search()` waits up to 10 seconds and then raises `RuntimeError`. Cache hits also use a rate-limit slot.
- The module-level `search()` helper builds a new tool for each call, so it never reuses cached results.
- Intent detection matches substrings: "recently" switches a query to news, and "eclipse" (which contains "clip") switches it to video.
- DuckDuckGo results come from regular expressions over its HTML page and are empty if the markup does not match.
- Bing: Microsoft retired the Bing Search APIs on August 11, 2025, and new Bing keys can't be created. The Bing backend code remains, but requests to it will fail.
- Google: the Custom Search JSON API is closed to new customers and will be discontinued on January 1, 2027 ([source](https://developers.google.com/custom-search/v1/overview)). After that date, DuckDuckGo scraping is the only backend expected to keep working. A failed request is not retried on another backend, so set `backend='duckduckgo'` before then.
- The default endpoints use HTTPS.

## Project layout

```text
WebSearchTool/
├── LICENSE
├── README.md
└── websearch_tool/
    ├── __init__.py        # all library code: config, backends, cache, rate limiter, LangChain wrapper
    ├── examples.py        # 11 usage examples; most call live search APIs
    ├── requirements.txt
    ├── README.md          # detailed reference
    └── tests/
        └── test_websearch_tool.py
```

## Tests

From the repository root:

```bash
pip install pytest
python -m pytest websearch_tool/tests/test_websearch_tool.py -v
```

Use `python -m pytest` rather than `pytest`: the test file adds `websearch_tool/` (not the repository root) to `sys.path`, so the import relies on `python -m` putting the current directory on the path. Three tests depend on the environment: `test_search_caching` needs `GOOGLE_API_KEY` and `GOOGLE_ENGINE_ID` to be set (any value), and `test_tool_func_error_handling` and `test_full_workflow_no_api` send real HTTP requests and expect them to fail.

## Roadmap (not implemented yet)

- Spell-correction hints and synonym expansion in query rewriting
- Relevance or confidence scores (`score` is not computed) and `published_date`
- Async search (`aiohttp` is in `requirements.txt` but not used)
- Configuration through `WEBSEARCH_*` environment variables (`SearchConfig` sets `env_prefix`, but a plain pydantic `BaseModel` does not read the environment)
- OpenAI web search backend (`backend='openai'` passes validation but raises `KeyError`)
- Image search on Bing, and video or news endpoints on any backend
- Retrying a failed request on another backend
- Monitoring hooks, configurable LangChain output formatting, and RAG helpers such as a retriever

## License

MIT. See [LICENSE](LICENSE).

## Documentation

The [detailed README](websearch_tool/README.md) covers every `SearchConfig` field, per-backend behavior, the response format, error types, the examples script and test notes.
