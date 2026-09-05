"""Small retrying HTTP client used by public data sources and Discord."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DataSourceError(RuntimeError):
    """Raised when a remote source cannot provide usable data."""


class HttpClient:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            # Never auto-retry a Discord POST: a retry could create two threads
            # if Discord accepted the first request but its response was lost.
            allowed_methods=frozenset({"GET"}),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {"User-Agent": "Ironbound-Power-Rankings/2.0 (+weekly Discord publication)"}
        )

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DataSourceError(f"GET failed for {safe_host(url)}: {exc}") from exc

    def post_multipart(
        self,
        url: str,
        *,
        data: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
    ) -> dict[str, Any]:
        try:
            response = self.session.post(
                url,
                data=data,
                files=files,
                timeout=self.timeout,
            )
            if response.status_code >= 300:
                detail = response.text[:500].replace("\n", " ")
                raise DataSourceError(
                    f"Discord rejected the post (HTTP {response.status_code}): {detail}"
                )
            return response.json() if response.content else {}
        except requests.RequestException as exc:
            raise DataSourceError(f"Discord post failed: {exc}") from exc


def safe_host(url: str) -> str:
    """Return a useful source label without ever logging URL secrets."""
    try:
        return urlsplit(url).netloc or "remote source"
    except ValueError:
        return "remote source"
