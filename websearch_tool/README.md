# WebSearchTool reference

Detailed reference for the `websearch_tool` package. For an overview, see the [repository README](../README.md). All library code is in `websearch_tool/__init__.py`.

## Install

The package is not on PyPI and has no `setup.py` or `pyproject.toml`. Clone the repository and install the requirements:

```bash
git clone https://github.com/sujaychandrakoyyalamudi/WebSearchTool.git
cd WebSearchTool
pip install -r websearch_tool/requirements.txt
```

Run Python from the repository root (or add it to `PYTHONPATH`) so that `import websearch_tool` works. The library imports `requests` and `pydantic`, plus `langchain_core` inside `create_langchain_tool()`. `examples.py` also uses `langchain`, `langchain-community` and `python-dotenv`. `aiohttp` is listed in `requirements.txt` but not imported.

## Quick start

### One-off search

```python
from websearch_tool import search

results = search("Python programming language", num_results=5)
print(f"Found {results['total_results']} results")
for result in results["results"]:
    print(f"- {result['title']}: {result['url']}")
```

Keyword arguments to `search()` become `SearchConfig` fields. Each call creates a new `WebSearchTool`, so nothing is cached between calls.

### Configured tool

```python
from websearch_tool import WebSearchTool, SearchConfig

config = SearchConfig(
    backend="google",            # or "bing", "duckduckgo", "auto"
    num_results=10,
    safe_search=True,
    date_range_days=7,           # sent to Google as dateRestrict=w1
    allowed_domains=["wikipedia.org"],
    cache_ttl_seconds=1800,
    language="en",
    country="us",
)
tool = WebSearchTool(config)
results = tool.search("machine learning frameworks")
print(tool.get_stats())
```

### LangChain tool

```python
from websearch_tool import create_langchain_tool, SearchConfig

search_tool = create_langchain_tool(SearchConfig(num_results=5))
print(search_tool.name)                                  # WebSearch
print(search_tool.invoke("vector database comparison"))  # formatted text
```

The tool takes one string argument, so it can be added to the `tools` list of a LangChain agent. It does not pass `context`, so each call is a single-turn search.

### Follow-up queries with context

```python
from websearch_tool import WebSearchTool

tool = WebSearchTool()
first = tool.search("Who invented the telephone")
context = first["results"][0]["snippet"] if first["results"] else ""
follow_up = tool.search("when was it patented", context=context)
print(follow_up["query"])   # the rewritten query that was sent
```

Context is used only when `enable_query_rewriting` is on and the query contains `it`, `they`, `this`, `that` or `these` as a separate word. A word with punctuation attached, such as `it?`, does not count. Up to three context words longer than four characters are appended, in no particular order. The tool keeps no conversation history; pass `context` on each call.

### Batch search

```python
batch = tool.search_batch(["renewable energy", "space exploration"])
for item in batch:
    print(item.get("error") or len(item["results"]))
```

Queries run one after another. A failed query yields `{"error": ..., "query": ...}` instead of raising.

## How a search runs

`WebSearchTool.search(query, context=None)` does the following, in order:

1. Increments `total_queries` and takes a rate-limit slot. If none is free, it retries every 0.5 seconds for up to 10 seconds, then raises `RuntimeError`.
2. If `enable_query_rewriting` is on, calls `QueryRewriter.rewrite()`: strips and collapses whitespace, applies the context rule above, and wraps queries of up to three words in double quotes when `str.istitle()` is true (`Ada Lovelace` becomes `"Ada Lovelace"`).
3. Calls `QueryRewriter.detect_intent()` on the rewritten query and works on a copy of the config. If the query contains "image", "picture", "photo" or "show me", `content_type` becomes `'image'`; otherwise "video", "watch", "youtube" or "clip" give `'video'`; otherwise "news", "latest", "recent", "today" or "breaking" give `'news'` and set `date_range_days` to 7 if it is unset. A match overrides the configured `content_type`. Matching is by substring and cannot be turned off.
4. Looks up the cache, keyed by the rewritten query plus `date_range_days`, `allowed_domains`, `blocked_domains` and `content_type`.
5. Picks the backend: the configured one, or Google for `'auto'`. If its credentials are missing, it uses the first other backend that has them, in the order Google, Bing, DuckDuckGo.
6. Sends the request. Any exception increments `errors` and is raised again as `RuntimeError("Search failed: ...")`.
7. Drops results with a repeated URL (if `enable_deduplication` is on), converts the response to a dict, stores it in the cache and returns it.

## Backends

Microsoft retired the Bing Search APIs on August 11, 2025, so the Bing column describes code that can no longer get results. Google's Custom Search JSON API is closed to new customers and will be discontinued on January 1, 2027 ([source](https://developers.google.com/custom-search/v1/overview)). After that date, DuckDuckGo scraping is the only backend expected to keep working.

| | Google | Bing | DuckDuckGo |
|---|---|---|---|
| Class | `GoogleSearchBackend` | `BingSearchBackend` | `DuckDuckGoBackend` |
| Request | GET `https://customsearch.googleapis.com/customsearch/v1` | GET `bing_endpoint` | POST `https://html.duckduckgo.com/html/` |
| Credentials | `google_api_key` and `google_engine_id` | `bing_api_key` | None |
| Results per call | Up to 10 | Up to 50 | Regex matches on one page, cut to `num_results` |
| `safe_search` | `safe=active` when on | `safeSearch=Strict` or `Off` | Adds `kh=1` when on (not verified to control safe search) |
| `date_range_days` | `dateRestrict`: `d1` (1), `w1` (2 to 7), `m1` (8 to 30), otherwise `y<days // 365>` | `freshness`: `Day`, `Week` or `Month`; not sent above 30 days | Not applied |
| Domains | Comma-joined `siteSearch` with `siteSearchFilter` `i` or `e` | `site:` or `-site:` operators added to the query | Not applied |
| `content_type` | `'image'` sets `searchType=image`; other values only label results | Label only | Label only |
| `language`, `country` | `hl`, `gl` | `mkt` and `Accept-Language` set to `<language>-<COUNTRY>` | `kl` set to `<country>-<language>` |
| Parsing | JSON `items` | JSON `webPages.value` | Regular expressions over the HTML |

Notes:

- On Google, a `date_range_days` value from 31 to 364 produces `dateRestrict=y0`.
- If both `allowed_domains` and `blocked_domains` are set, Google and Bing apply only `allowed_domains`.
- For Google image searches, `image_url` is taken from the item's `pagemap.cse_image` entry when it exists.
- DuckDuckGo needs no key, so it always passes the credential check. The `ValueError("No valid search backend configured")` branch in `search()` is therefore never reached.

## Configuration

`SearchConfig` is a pydantic `BaseModel`. Every field below is read by the code.

| Field | Default | Notes |
|---|---|---|
| `backend` | `'auto'` | `'google'`, `'bing'`, `'duckduckgo'` or `'auto'` (Google first). The type also accepts `'openai'`, but no OpenAI backend exists and selecting it raises `KeyError`. |
| `google_api_key` | `None` | Falls back to `GOOGLE_API_KEY` |
| `google_engine_id` | `None` | Programmable Search Engine ID; falls back to `GOOGLE_ENGINE_ID` |
| `bing_api_key` | `None` | Falls back to `BING_API_KEY` |
| `bing_endpoint` | `'https://api.bing.microsoft.com/v7.0/search'` | Bing request URL |
| `num_results` | `10` | Validated to 1 to 100. Google returns at most 10 and Bing at most 50 per call; there is no pagination. |
| `language` | `'en'` | See the backend table |
| `country` | `'us'` | See the backend table |
| `safe_search` | `True` | See the backend table |
| `date_range_days` | `None` | Coarse buckets; see the backend table |
| `allowed_domains` | `None` | Google and Bing only; takes precedence over `blocked_domains` |
| `blocked_domains` | `None` | Google and Bing only |
| `content_type` | `'web'` | `'web'`, `'image'`, `'video'` or `'news'`; intent detection can override it per query |
| `enable_cache` | `True` | In-memory cache per tool instance |
| `cache_ttl_seconds` | `3600` | Lifetime of each cache entry |
| `rate_limit_per_minute` | `60` | Client-side, per tool instance |
| `rate_limit_per_day` | `1000` | Client-side, per tool instance |
| `enable_query_rewriting` | `True` | Turns `QueryRewriter.rewrite()` on or off; intent detection always runs |
| `enable_deduplication` | `True` | Drops results whose URL was already seen in the same response |
| `timeout_seconds` | `10` | Passed to `requests` as the timeout |

### Environment variables

| Variable | Read by | Used when |
|---|---|---|
| `GOOGLE_API_KEY` | `GoogleSearchBackend.__init__` | `google_api_key` is empty |
| `GOOGLE_ENGINE_ID` | `GoogleSearchBackend.__init__` | `google_engine_id` is empty |
| `BING_API_KEY` | `BingSearchBackend.__init__` | `bing_api_key` is empty |

They are read once, when `WebSearchTool` is created. The package does not load `.env` files; call `load_dotenv()` from `python-dotenv` before creating the tool if you keep keys in a `.env` file.

`SearchConfig` declares `env_prefix = 'WEBSEARCH_'`, but a plain pydantic `BaseModel` does not read environment variables, so variables such as `WEBSEARCH_BACKEND` have no effect.

## API reference

### `WebSearchTool(config: Optional[SearchConfig] = None)`

- `search(query: str, context: Optional[str] = None) -> Dict[str, Any]`: runs one search; see [How a search runs](#how-a-search-runs).
- `search_batch(queries: List[str], context: Optional[str] = None) -> List[Dict[str, Any]]`: calls `search()` for each query in order, with the same `context`; failures become `{"error": str, "query": str}` entries.
- `get_stats() -> Dict[str, Any]`: `total_queries`, `cache_hits`, `cache_misses`, `errors`, `cache_size`, `rate_limit_remaining_minute` and `rate_limit_remaining_day`. `errors` counts failed backend requests only. `cache_size` includes expired entries that have not been looked up since they expired. The remaining counts are as of the last request.
- `clear_cache()`: empties the cache.

### `search(query: str, **kwargs) -> Dict[str, Any]`

Module-level shortcut for `WebSearchTool(SearchConfig(**kwargs)).search(query)`. It does not accept `context`; pydantic ignores unknown keyword arguments.

### `create_langchain_tool(config: Optional[SearchConfig] = None)`

Returns `langchain_core.tools.Tool(name="WebSearch", ...)` backed by one `WebSearchTool`, so its cache and rate limits persist across calls. The tool returns text in this shape:

```text
Search results for: <query sent>

[1] <title>
    URL: <url>
    <snippet>

Total results: <total_results>
Search time: <ms>ms
```

On any exception it returns `"Search error: <message>"` instead of raising.

### Response dict

| Key | Content |
|---|---|
| `query` | The query sent to the backend, after rewriting |
| `results` | List of result dicts (below) |
| `total_results` | Google `searchInformation.totalResults`, Bing `webPages.totalEstimatedMatches`, or the number of parsed results for DuckDuckGo |
| `search_time_ms` | Time spent in the backend request and parsing |
| `backend` | `'google'`, `'bing'` or `'duckduckgo'` |
| `filters_applied` | The request parameters sent to the backend, without the API key. For Google this includes `cx`, the search engine ID. |

### Result fields (`SearchResult`)

| Field | Content |
|---|---|
| `title`, `url`, `snippet` | As returned by the backend |
| `source` | Backend name |
| `content_type` | The effective `content_type` (a label; see [Backends](#backends)) |
| `image_url` | Google image searches only, when `pagemap.cse_image` is present; otherwise `None` |
| `score` | Not computed. `None` for Google and DuckDuckGo; the Bing backend stores the page's `dateLastCrawled` string here. |
| `published_date` | Always `None`; no backend sets it |

### Errors

| Situation | Result |
|---|---|
| Rate limit still exhausted after 10 seconds | `RuntimeError("Rate limit exceeded. Please try again later.")` |
| Backend request or parsing fails | `RuntimeError("Search failed: ...")` |
| `backend='openai'` | `KeyError: 'openai'` |
| Invalid config value, for example `num_results=0` | pydantic `ValidationError` |

## Safety and limits

- Logging: importing the package calls `logging.basicConfig(level=logging.INFO)`. Each search logs the original and rewritten query at INFO level, and backend errors at ERROR level. With `backend='auto'` and no Google credentials, every search that is not served from the cache also logs an ERROR line before falling back, and every DuckDuckGo search logs a WARNING.
- API keys: the Google key is sent as the `key` URL query parameter and the Bing key in the `Ocp-Apim-Subscription-Key` header. Neither is in `filters_applied`, so neither is returned or cached. If a request fails, the backend replaces the key with `***` in the error message (including its URL-encoded form), logs that message and raises `requests.exceptions.RequestException` with `from None`, so the original exception is not chained into tracebacks. The key therefore stays out of this package's log lines, the `RuntimeError` from `search()`, `search_batch()` error entries and the LangChain tool's output. urllib3, which `requests` uses, logs each request URL at DEBUG level, including the Google `key` parameter, so keep urllib3 DEBUG logging off in production.
- Backend availability: Google's Custom Search JSON API is closed to new customers and will be discontinued on January 1, 2027 ([source](https://developers.google.com/custom-search/v1/overview)), and the Bing Search APIs were retired on August 11, 2025. After January 1, 2027, DuckDuckGo scraping is the only backend expected to keep working. Failed requests are not retried on another backend, so set `backend='duckduckgo'` before then.
- Rate limiting: the per-minute and per-day counters reset fully once 60 seconds or 24 hours have passed since their last reset. They live in memory per `WebSearchTool` instance and are not shared across instances or processes. Cache hits also use a slot.
- Caching: the cache is an unbounded dict per instance. Expired entries are removed only when they are looked up.
- Fallback covers missing credentials only. Failed requests are not retried.
- DuckDuckGo results come from regular expressions over its HTML page and are empty if the markup does not match.
- The default endpoints use HTTPS. `bing_endpoint` can be changed to any URL.

## Examples

`websearch_tool/examples.py` has 11 functions: basic search, custom configuration, LangChain tool, agent setup (prints the tool list; the agent code is disabled), image search, news search, batch search, a RAG-style prompt built from snippets, error handling, caching and multi-turn context. Run them from the repository root:

```bash
python -m websearch_tool.examples
```

- The script imports `initialize_agent`, `Tool` and `AgentType` from `langchain.agents` at the top. These are LangChain 0.x APIs, so the script needs a LangChain release that still provides them.
- Most examples send live requests. Errors in each example are caught and printed.
- The RAG example only formats snippets into a prompt string. The package has no retriever or document loader.

## Tests

From the repository root:

```bash
pip install pytest
python -m pytest websearch_tool/tests/test_websearch_tool.py -v
```

Use `python -m pytest` rather than `pytest`. The test file adds `websearch_tool/` (not the repository root) to `sys.path`, so the import relies on `python -m` putting the current directory on the path.

The tests cover `SearchResult`, `SearchResponse`, `SearchConfig` validation, `QueryRewriter`, `ResultCache` expiry, `RateLimiter`, `WebSearchTool` setup, deduplication, stats and caching, `create_langchain_tool()`, and API-key handling. The API-key tests in `TestApiKeyRedaction` mock `requests.get`, so they need no keys or network access. Three tests depend on the environment:

- `test_search_caching` mocks only `GoogleSearchBackend.search`. Unless `GOOGLE_API_KEY` and `GOOGLE_ENGINE_ID` are set (any value), the tool falls back to Bing or DuckDuckGo and the test's assertion fails.
- `test_tool_func_error_handling` and `test_full_workflow_no_api` send real HTTP requests and expect them to fail.

## Roadmap (not implemented yet)

- Spell-correction hints and synonym expansion (named in the `QueryRewriter.rewrite()` docstring)
- Relevance or confidence scores; `score` is not computed
- `published_date` extraction
- Async search (`aiohttp` is in `requirements.txt` but not used)
- Configuration through `WEBSEARCH_*` environment variables
- OpenAI web search backend (named in the module docstring and accepted by `backend`)
- Image search on Bing, and video or news endpoints on any backend
- Retrying a failed request on another backend
- Monitoring hooks
- Configurable output formatting for the LangChain tool
- RAG helpers, such as a retriever that returns LangChain documents
- Ideas from the earlier README: more backends, model-based query rewriting, Redis-backed caching (commented out in `requirements.txt`), better intent detection and vision-model handling of image results

## License

MIT. See [LICENSE](../LICENSE).
