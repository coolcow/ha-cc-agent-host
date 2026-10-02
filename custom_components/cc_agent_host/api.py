"""Client for the CC Agent Host job API."""
from __future__ import annotations

from typing import Any

import aiohttp


class AgentHostError(Exception):
    """API error with HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class AgentHostAuthError(AgentHostError):
    """Invalid API key."""


class AgentHostApi:
    """Thin async client; the add-on does all the work."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, api_key: str) -> None:
        self._session = session
        self._base = f"http://{host}:{port}"
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def _request(self, method: str, path: str, timeout: float, body: dict | None = None) -> dict[str, Any]:
        try:
            async with self._session.request(
                method, self._base + path, json=body, headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 401:
                    raise AgentHostAuthError(401, "invalid API key")
                if resp.status >= 400:
                    raise AgentHostError(resp.status, (data or {}).get("error", f"HTTP {resp.status}"))
                return data
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AgentHostError(0, f"add-on not reachable: {err}") from err

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/status", 15)

    async def usage(self) -> dict[str, Any]:
        return await self._request("GET", "/usage", 15)

    async def profiles(self) -> dict[str, Any]:
        return await self._request("GET", "/profiles", 15)

    async def run(self, profile: str, prompt: str, timeout: int | None) -> dict[str, Any]:
        body: dict[str, Any] = {"profile": profile, "prompt": prompt}
        if timeout:
            body["timeout"] = timeout
        # the add-on enforces the profile's limit; allow some slack for context preparation
        return await self._request("POST", "/run", (timeout or 1800) + 60, body)
