import asyncio
from unittest.mock import AsyncMock, patch

from src.tools.builtin.web_tools import WebFetchTool, WebSearchTool


def test_web_search_maps_arguments_and_preserves_sources():
    response = "Title: Python\nURL: https://python.org\nHighlights: Official site"
    with patch(
        "src.tools.builtin.web_tools._call_exa", AsyncMock(return_value=response)
    ) as call:
        result = asyncio.run(
            WebSearchTool().execute("  Python language  ", num_results=20)
        )

    call.assert_awaited_once_with(
        "web_search_exa", {"query": "Python language", "numResults": 10}
    )
    assert "https://python.org" in result
    assert "not independently verified facts" in result


def test_web_search_reports_backend_failure_without_fake_results():
    with patch(
        "src.tools.builtin.web_tools._call_exa",
        AsyncMock(side_effect=RuntimeError("service unavailable")),
    ):
        result = asyncio.run(WebSearchTool().execute("current news"))

    assert result == "Error searching the web: service unavailable"
    assert "Search results" not in result


def test_web_fetch_maps_url_and_length():
    with patch(
        "src.tools.builtin.web_tools._call_exa", AsyncMock(return_value="page body")
    ) as call:
        result = asyncio.run(
            WebFetchTool().execute("example.com/article", max_length=1200)
        )

    call.assert_awaited_once_with(
        "web_fetch_exa",
        {"urls": ["https://example.com/article"], "maxCharacters": 1200},
    )
    assert result == "page body"
