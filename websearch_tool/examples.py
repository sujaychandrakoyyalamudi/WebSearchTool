"""
Example usage of WebSearchTool with LangChain agents.

This file demonstrates various ways to integrate the WebSearchTool
with LangChain for building AI agents with web search capabilities.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from langchain.agents import initialize_agent, Tool, AgentType
from langchain_community.llms import FakeListLLM  # Replace with real LLM in production
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from websearch_tool import WebSearchTool, SearchConfig, create_langchain_tool, search


def example_basic_search():
    """Example 1: Basic standalone search."""
    print("=" * 60)
    print("Example 1: Basic Standalone Search")
    print("=" * 60)
    
    # Quick search with default config
    results = search("Python programming language", num_results=3)
    
    print(f"Query: {results['query']}")
    print(f"Total results: {results['total_results']}")
    print(f"Search time: {results['search_time_ms']:.0f}ms\n")
    
    for i, result in enumerate(results['results'], 1):
        print(f"{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   {result['snippet']}\n")


def example_custom_config():
    """Example 2: Custom configuration with filters."""
    print("=" * 60)
    print("Example 2: Custom Configuration with Filters")
    print("=" * 60)
    
    # Create custom config
    config = SearchConfig(
        backend='google',  # or 'bing', 'duckduckgo', 'auto'
        num_results=5,
        safe_search=True,
        date_range_days=7,  # Only results from last week
        allowed_domains=['wikipedia.org', 'github.com'],  # Restrict to specific domains
        enable_cache=True,
        cache_ttl_seconds=1800,  # 30 minutes
        language='en',
        country='us'
    )
    
    # Initialize tool with config
    tool = WebSearchTool(config)
    
    # Perform search
    results = tool.search("machine learning frameworks")
    
    print(f"Query: {results['query']}")
    print(f"Backend used: {results['backend']}")
    print(f"Filters applied: {results['filters_applied']}\n")
    
    for result in results['results']:
        print(f"• {result['title']}")
        print(f"  {result['url']}\n")
    
    # Get statistics
    stats = tool.get_stats()
    print(f"Stats: {stats}")


def example_langchain_tool():
    """Example 3: Integration with LangChain Tool."""
    print("=" * 60)
    print("Example 3: LangChain Tool Integration")
    print("=" * 60)
    
    # Create LangChain-compatible tool
    search_tool = create_langchain_tool(
        SearchConfig(num_results=3, backend='auto')
    )
    
    print(f"Tool name: {search_tool.name}")
    print(f"Tool description: {search_tool.description}\n")
    
    # Use the tool directly
    result = search_tool.func("What is quantum computing?")
    print(result)


def example_langchain_agent():
    """Example 4: Full LangChain Agent with Web Search."""
    print("=" * 60)
    print("Example 4: LangChain Agent with Web Search")
    print("=" * 60)
    
    # Note: In production, replace FakeListLLM with a real LLM
    # Example with OpenAI:
    # from langchain_openai import ChatOpenAI
    # llm = ChatOpenAI(model="gpt-4", temperature=0)
    
    # For demonstration, we'll show the setup structure
    print("Setting up agent with web search tool...\n")
    
    # Create the web search tool
    web_search_tool = create_langchain_tool(
        SearchConfig(num_results=5, enable_cache=True)
    )
    
    # Define all tools
    tools = [web_search_tool]
    
    # Example agent setup (commented out - requires real LLM)
    """
    llm = ChatOpenAI(model="gpt-4", temperature=0)
    
    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True
    )
    
    # Run the agent
    response = agent.run("What are the latest developments in artificial intelligence?")
    print(f"Agent response: {response}")
    """
    
    print("Agent configured with tools:")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")
    
    print("\nTo use with a real LLM, uncomment the code and set OPENAI_API_KEY")


def example_multimodal_search():
    """Example 5: Image and Video Search."""
    print("=" * 60)
    print("Example 5: Multimodal Search (Images)")
    print("=" * 60)
    
    config = SearchConfig(
        backend='google',
        content_type='image',  # Will be auto-detected from query too
        num_results=5
    )
    
    tool = WebSearchTool(config)
    
    # Query with image intent
    results = tool.search("show me pictures of Mount Everest")
    
    print(f"Query: {results['query']}")
    print(f"Content type: {results['filters_applied'].get('searchType', 'web')}\n")
    
    for result in results['results']:
        print(f"• {result['title']}")
        print(f"  URL: {result['url']}")
        if result.get('image_url'):
            print(f"  Image: {result['image_url']}")
        print()


def example_news_search():
    """Example 6: News Search with Date Filtering."""
    print("=" * 60)
    print("Example 6: News Search with Freshness Filter")
    print("=" * 60)
    
    config = SearchConfig(
        backend='bing',
        date_range_days=7,  # Last week only
        num_results=5
    )
    
    tool = WebSearchTool(config)
    
    # News-related query (auto-detects news intent)
    results = tool.search("latest technology news")
    
    print(f"Query: {results['query']}")
    print(f"Date filter: last {config.date_range_days} days\n")
    
    for result in results['results']:
        print(f"• {result['title']}")
        print(f"  {result['snippet'][:100]}...\n")


def example_batch_search():
    """Example 7: Batch Search Multiple Queries."""
    print("=" * 60)
    print("Example 7: Batch Search")
    print("=" * 60)
    
    config = SearchConfig(num_results=2, enable_cache=True)
    tool = WebSearchTool(config)
    
    queries = [
        "renewable energy trends",
        "space exploration 2025",
        "quantum computing breakthroughs"
    ]
    
    results = tool.search_batch(queries)
    
    for i, (query, result) in enumerate(zip(queries, results), 1):
        print(f"\n{i}. Query: {query}")
        if 'error' in result:
            print(f"   Error: {result['error']}")
        else:
            print(f"   Results found: {len(result['results'])}")
            for r in result['results']:
                print(f"   - {r['title']}")


def example_rag_integration():
    """Example 8: RAG (Retrieval-Augmented Generation) Pattern."""
    print("=" * 60)
    print("Example 8: RAG Integration Pattern")
    print("=" * 60)
    
    # Simulate RAG pipeline
    query = "What is the capital of France?"
    
    # Step 1: Retrieve documents via web search
    config = SearchConfig(num_results=3)
    tool = WebSearchTool(config)
    search_results = tool.search(query)
    
    # Step 2: Format retrieved content for LLM context
    context_documents = []
    for result in search_results['results']:
        doc = f"Source: {result['url']}\nContent: {result['snippet']}"
        context_documents.append(doc)
    
    context = "\n\n".join(context_documents)
    
    # Step 3: Create prompt with retrieved context
    # In production, this would go to an actual LLM
    prompt = f"""Answer the following question using the provided context.
If the context doesn't contain the answer, say so.

Context:
{context}

Question: {query}

Answer:"""
    
    print("RAG Pipeline:")
    print(f"1. Retrieved {len(search_results['results'])} documents")
    print(f"2. Formatted context ({len(context)} chars)")
    print(f"3. Created prompt for LLM\n")
    print("Prompt preview (first 200 chars):")
    print(prompt[:200] + "...")
    
    # Step 4: Send to LLM (pseudo-code)
    # response = llm.invoke(prompt)
    # return response.content


def example_error_handling():
    """Example 9: Error Handling and Fallback."""
    print("=" * 60)
    print("Example 9: Error Handling")
    print("=" * 60)
    
    # Configure with invalid backend to demonstrate fallback
    config = SearchConfig(
        backend='google',
        google_api_key='invalid_key',  # This will fail
        google_engine_id='invalid_id'
    )
    
    tool = WebSearchTool(config)
    
    try:
        results = tool.search("test query")
        print("Search succeeded")
    except RuntimeError as e:
        print(f"Search failed (expected): {e}")
        print("\nIn production, you would:")
        print("  1. Log the error")
        print("  2. Try fallback backend")
        print("  3. Return cached result if available")
        print("  4. Inform user gracefully")


def example_caching():
    """Example 10: Caching Demonstration."""
    print("=" * 60)
    print("Example 10: Caching Behavior")
    print("=" * 60)
    
    config = SearchConfig(
        num_results=2,
        enable_cache=True,
        cache_ttl_seconds=3600
    )
    
    tool = WebSearchTool(config)
    
    query = "climate change effects"
    
    # First search (cache miss)
    print("First search (cache miss):")
    result1 = tool.search(query)
    stats1 = tool.get_stats()
    print(f"  Cache hits: {stats1['cache_hits']}, Misses: {stats1['cache_misses']}")
    
    # Second search (cache hit)
    print("\nSecond search (cache hit):")
    result2 = tool.search(query)
    stats2 = tool.get_stats()
    print(f"  Cache hits: {stats2['cache_hits']}, Misses: {stats2['cache_misses']}")
    
    # Clear cache
    tool.clear_cache()
    print("\nCache cleared")
    
    # Third search (cache miss again)
    print("Third search (cache cleared):")
    result3 = tool.search(query)
    stats3 = tool.get_stats()
    print(f"  Cache hits: {stats3['cache_hits']}, Misses: {stats3['cache_misses']}")


def example_multi_turn_context():
    """Example 11: Multi-turn Conversation Context."""
    print("=" * 60)
    print("Example 11: Multi-turn Context Integration")
    print("=" * 60)
    
    config = SearchConfig(num_results=3)
    tool = WebSearchTool(config)
    
    # First turn
    query1 = "Who invented the World Wide Web?"
    print(f"Turn 1: {query1}")
    result1 = tool.search(query1)
    
    if result1['results']:
        # Extract context from first result
        context = result1['results'][0]['snippet']
        print(f"Context extracted: {context[:80]}...\n")
        
        # Second turn with pronoun reference
        query2 = "When did he create it?"
        print(f"Turn 2: {query2}")
        result2 = tool.search(query2, context=context)
        print(f"Rewritten query includes context keywords\n")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("WebSearchTool for LangChain - Usage Examples")
    print("=" * 60 + "\n")
    
    # Run examples
    examples = [
        example_basic_search,
        example_custom_config,
        example_langchain_tool,
        example_langchain_agent,
        example_multimodal_search,
        example_news_search,
        example_batch_search,
        example_rag_integration,
        example_error_handling,
        example_caching,
        example_multi_turn_context,
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"Example {example.__name__} encountered error: {e}")
            print("(This is expected if API keys are not configured)\n")
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
