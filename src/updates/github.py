# SPDX-License-Identifier: MIT
"""Minimal GitHub REST client pinned to this project's own public repository.

The host is a module constant rather than a caller-supplied URL so no code path
can turn this into an SSRF primitive.
"""

from __future__ import annotations

import httpx

GITHUB_API = "https://api.github.com"
REPO_SLUG = "sildo466/FSAR"
_TIMEOUT = 15.0


class GitHubError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        # Callers distinguish "absent" from "broken" without parsing the message.
        self.status = status


class GitHubClient:
    def __init__(self, config, *, timeout: float = _TIMEOUT, client=None) -> None:
        self.config = config
        self.timeout = timeout
        self._client = client

    def _headers(self, accept: str | None = None) -> dict[str, str]:
        headers = {"Accept": accept or "application/vnd.github+json"}
        token = str(self.config.get("github.token", "") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _guard(self, url: str) -> None:
        from src.skills.egress import enforce_url

        enforce_url(url, self.config)

    async def _get(self, url: str, *, accept: str | None = None) -> httpx.Response:
        self._guard(url)
        try:
            if self._client is not None:
                response = await self._client.get(url, headers=self._headers(accept))
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, headers=self._headers(accept))
        except httpx.HTTPError as exc:
            raise GitHubError(f"request failed: {exc!r}") from exc
        if response.status_code >= 400:
            raise GitHubError(
                f"HTTP {response.status_code} for {url}",
                status=response.status_code,
            )
        return response

    async def releases(self, *, per_page: int = 30) -> list[dict]:
        response = await self._get(
            f"{GITHUB_API}/repos/{REPO_SLUG}/releases?per_page={int(per_page)}"
        )
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def contents(self, path: str, *, ref: str = "main") -> list[dict]:
        clean = path.strip("/")
        response = await self._get(
            f"{GITHUB_API}/repos/{REPO_SLUG}/contents/{clean}?ref={ref}"
        )
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def contents_text(self, path: str, *, ref: str = "main") -> str:
        """A file's body, fetched from the pinned API host.

        Deliberately not the listing's `download_url`: that points at
        raw.githubusercontent.com, which is unreachable on networks where
        api.github.com works, and is absent from the egress allowlist.
        """
        clean = path.strip("/")
        response = await self._get(
            f"{GITHUB_API}/repos/{REPO_SLUG}/contents/{clean}?ref={ref}",
            accept="application/vnd.github.raw",
        )
        return response.text
