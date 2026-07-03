"""FSAR web tools — web_search and web_fetch."""

from __future__ import annotations

import json
from typing import Optional
from urllib.parse import quote_plus

import httpx

from src.tools.registry import Tool
from src.utils.logger import logger


class WebSearchTool(Tool):
    """Search the web using DuckDuckGo."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for information. Returns search results with titles, URLs, and snippets."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "num_results": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of results to return (1-10)",
                },
            },
            "required": ["query"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, query: str, num_results: int = 5, **kwargs) -> str:
        """Search the web using DuckDuckGo HTML API."""
        num_results = min(max(num_results, 1), 10)

        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()

            # Parse HTML results (simple extraction)
            results = self._parse_results(resp.text, num_results)

            if not results:
                return f"No results found for: {query}"

            output = f"Search results for: {query}\n\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. {r['title']}\n"
                output += f"   URL: {r['url']}\n"
                if r.get("snippet"):
                    output += f"   {r['snippet']}\n"
                output += "\n"

            return output.strip()

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return f"Error searching: {e}"

    def _parse_results(self, html: str, num_results: int) -> list:
        """Parse DuckDuckGo HTML results."""
        results = []
        # Simple regex-based parsing for DuckDuckGo HTML
        import re

        # Find result blocks
        links = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html)
        snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html)

        for i, (url, title) in enumerate(links[:num_results]):
            # Clean HTML tags from title
            title = re.sub(r'<[^>]+>', '', title).strip()
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()

            # Decode DuckDuckGo redirect URL
            if "uddg=" in url:
                from urllib.parse import unquote, urlparse, parse_qs
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if "uddg" in params:
                    url = unquote(params["uddg"][0])

            results.append({
                "title": title,
                "url": url,
                "snippet": snippet,
            })

        return results


class WebFetchTool(Tool):
    """Fetch webpage content."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch and extract text content from a webpage URL."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "max_length": {
                    "type": "integer",
                    "default": 5000,
                    "description": "Maximum characters to return",
                },
            },
            "required": ["url"],
        }

    @property
    def risk_level(self) -> str:
        return "SAFE"

    async def execute(self, url: str, max_length: int = 5000, **kwargs) -> str:
        """Fetch webpage content."""
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")

            # For HTML, extract text
            if "html" in content_type:
                text = self._extract_text(resp.text)
            else:
                text = resp.text

            # Truncate if needed
            if len(text) > max_length:
                text = text[:max_length] + f"\n\n... (truncated at {max_length} chars)"

            return text if text else "(empty response)"

        except Exception as e:
            logger.error(f"Web fetch failed: {e}")
            return f"Error fetching: {e}"

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML."""
        import re

        # Remove script and style tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        # Decode HTML entities
        import html as html_module
        text = html_module.unescape(text)

        return text
