# SPDX-License-Identifier: MIT
from __future__ import annotations

import httpx
import pytest

from src.skills.egress import EgressDenied
from src.updates.github import GITHUB_API, GitHubClient, GitHubError


class _Config:
    def __init__(self, token="", egress=False, allow=None):
        self._values = {
            "github.token": token,
            "security.egress.enabled": egress,
            "security.egress.mode": "deny",
            "security.egress.allowlist": allow or [],
            "security.egress.blocklist": [],
        }

    def get(self, key, default=None):
        return self._values.get(key, default)


class _Transport(httpx.AsyncBaseTransport):
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        status, payload = self._responses.pop(0)
        if isinstance(payload, str):
            return httpx.Response(status, text=payload, request=request)
        return httpx.Response(status, json=payload, request=request)


def _client(config, responses):
    transport = _Transport(responses)
    http = httpx.AsyncClient(transport=transport, timeout=5.0)
    return GitHubClient(config, client=http), transport


async def test_releases_hits_the_pinned_endpoint():
    client, transport = _client(_Config(), [(200, [{"tag_name": "v0.7.0"}])])
    rows = await client.releases()
    assert rows == [{"tag_name": "v0.7.0"}]
    assert str(transport.requests[0].url) == f"{GITHUB_API}/repos/sildo466/FSAR/releases?per_page=30"


async def test_token_is_sent_as_bearer_when_configured():
    client, transport = _client(_Config(token="ghp_secret"), [(200, [])])
    await client.releases()
    assert transport.requests[0].headers["authorization"] == "Bearer ghp_secret"


async def test_no_authorization_header_without_token():
    client, transport = _client(_Config(), [(200, [])])
    await client.releases()
    assert "authorization" not in {k.lower() for k in transport.requests[0].headers}


async def test_contents_pins_ref_and_path():
    client, transport = _client(_Config(), [(200, [])])
    await client.contents("announcements")
    assert str(transport.requests[0].url) == (
        f"{GITHUB_API}/repos/sildo466/FSAR/contents/announcements?ref=main"
    )


async def test_http_error_becomes_github_error():
    client, _ = _client(_Config(), [(403, {"message": "rate limited"})])
    with pytest.raises(GitHubError) as excinfo:
        await client.releases()
    assert "403" in str(excinfo.value)


async def test_network_failure_becomes_github_error():
    class _Boom(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("no route", request=request)

    client = GitHubClient(_Config(), client=httpx.AsyncClient(transport=_Boom()))
    with pytest.raises(GitHubError):
        await client.releases()


async def test_egress_denial_blocks_the_request(monkeypatch):
    # Pin DNS so the unit test never touches the network.
    monkeypatch.setattr(
        "src.skills.egress._resolve_addresses", lambda host, port: {"203.0.113.1"}
    )
    config = _Config(egress=True, allow=["example.com:443"])
    client, transport = _client(config, [(200, [])])
    with pytest.raises(EgressDenied):
        await client.releases()
    assert transport.requests == []


async def test_egress_allowlist_permits_api_github_com(monkeypatch):
    monkeypatch.setattr(
        "src.skills.egress._resolve_addresses", lambda host, port: {"203.0.113.1"}
    )
    config = _Config(egress=True, allow=["api.github.com:443"])
    client, transport = _client(config, [(200, [])])
    await client.releases()
    assert len(transport.requests) == 1


async def test_contents_text_uses_the_pinned_host_and_raw_media_type():
    """Not the listing's `download_url`: raw.githubusercontent.com is
    unreachable where api.github.com works, and is not in the egress allowlist."""
    client, transport = _client(_Config(), [(200, "# hello")])
    body = await client.contents_text("announcements/a.md")
    assert body == "# hello"
    request = transport.requests[0]
    assert str(request.url) == (
        f"{GITHUB_API}/repos/sildo466/FSAR/contents/announcements/a.md?ref=main"
    )
    assert request.headers["accept"] == "application/vnd.github.raw"


async def test_network_failure_message_names_the_exception_type():
    """A bare `str(exc)` is empty for httpx.ReadTimeout, which made the reported
    error read 'request failed: ' with no clue what went wrong."""
    class _Timeout(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ReadTimeout("", request=request)

    client = GitHubClient(_Config(), client=httpx.AsyncClient(transport=_Timeout()))
    with pytest.raises(GitHubError) as excinfo:
        await client.releases()
    assert "ReadTimeout" in str(excinfo.value)
