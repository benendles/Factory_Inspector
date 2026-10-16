"""Bounded Tavily research adapter for supplier-source discovery.

Tavily results are treated as untrusted web-search material.  This adapter
never interprets a result as a live quote, stock confirmation, or compatibility
claim.  It is deliberately synchronous because repair planning is currently a
synchronous operation performed only after the audited identity gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from threading import Lock
from typing import Any

import httpx


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env_number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class SupplierSearchService:
    """Retrieve a small, cached set of supplier search observations.

    Live research is opt-in through ``TAVILY_RESEARCH_ENABLED=true``.  This
    protects the workflow from unexpected paid requests during automated tests
    and ordinary local development, even if a key is present in ``.env``.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        enabled: bool | None = None,
        http_client: Any | None = None,
        max_searches: int | None = None,
        max_results: int = 5,
        timeout_seconds: float | None = None,
        max_attempts: int = 2,
        cache_ttl_seconds: int | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv(
            "TAVILY_API_KEY"
        )
        self._enabled = (
            _env_flag("TAVILY_RESEARCH_ENABLED")
            if enabled is None
            else enabled
        )
        self._http_client = http_client or httpx.Client()
        configured_max_searches = (
            _env_number("TAVILY_MAX_SEARCHES", 3)
            if max_searches is None else max_searches
        )
        configured_timeout = (
            _env_number("TAVILY_SEARCH_TIMEOUT_SECONDS", 8.0)
            if timeout_seconds is None else timeout_seconds
        )
        configured_ttl = (
            _env_number("TAVILY_CACHE_TTL_SECONDS", 900)
            if cache_ttl_seconds is None else cache_ttl_seconds
        )
        self._max_searches = max(1, min(int(configured_max_searches), 3))
        self._max_results = max(1, min(int(max_results), 5))
        self._timeout_seconds = max(float(configured_timeout), 0.1)
        self._max_attempts = max(1, min(int(max_attempts), 2))
        self._cache_ttl = timedelta(seconds=max(int(configured_ttl), 0))
        self._cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._lock = Lock()

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _clean_text(value: Any, maximum: int = 2_000) -> str | None:
        if not isinstance(value, str):
            return None
        text = " ".join(value.split())
        return text[:maximum] or None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _cached(self, query: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._cache.get(query)
            if item is None:
                return None
            expires_at, result = item
            if expires_at < self._now():
                self._cache.pop(query, None)
                return None
            return {**result, "cached": True}

    def _cache_result(self, query: str, result: dict[str, Any]) -> None:
        if self._cache_ttl.total_seconds() <= 0:
            return
        with self._lock:
            self._cache[query] = (
                self._now() + self._cache_ttl,
                dict(result),
            )

    def _search_query(self, query: str) -> dict[str, Any]:
        cached = self._cached(query)
        if cached is not None:
            return cached

        request_data = {
            "query": query,
            "search_depth": "basic",
            "max_results": self._max_results,
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_usage": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        last_error = "Tavily search request failed."

        for attempt in range(self._max_attempts):
            try:
                response = self._http_client.post(
                    TAVILY_SEARCH_URL,
                    headers=headers,
                    json=request_data,
                    timeout=self._timeout_seconds,
                )
            except (httpx.HTTPError, OSError, ValueError):
                if attempt + 1 < self._max_attempts:
                    continue
                break

            status_code = getattr(response, "status_code", 500)
            if status_code in {429, 500, 502, 503, 504}:
                last_error = "Tavily search provider is temporarily unavailable."
                if attempt + 1 < self._max_attempts:
                    continue
                break

            if status_code < 200 or status_code >= 300:
                last_error = "Tavily search request was not accepted."
                break

            try:
                payload = response.json()
            except (TypeError, ValueError):
                last_error = "Tavily search returned an invalid response."
                break

            results: list[dict[str, Any]] = []
            for source in self._as_dict(payload).get("results", []):
                source_data = self._as_dict(source)
                url = self._clean_text(source_data.get("url"), 2_048)
                title = self._clean_text(source_data.get("title"), 500)
                content = self._clean_text(source_data.get("content"))
                if not url or not title:
                    continue
                results.append({
                    "query": query,
                    "title": title,
                    "url": url,
                    "content": content,
                    "score": source_data.get("score"),
                    "retrieved_at": self._now().isoformat(),
                    "source_type": "tavily_search_result",
                    "trusted": False,
                })

            result = {
                "status": "completed" if results else "no_results",
                "query": query,
                "results": results,
                "cached": False,
                "error": None,
            }
            self._cache_result(query, result)
            return result

        return {
            "status": "search_unavailable",
            "query": query,
            "results": [],
            "cached": False,
            "error": last_error,
        }

    def search_parts(self, queries: list[str]) -> dict[str, Any]:
        """Search a maximum of three unique, non-empty research queries."""

        normalized_queries: list[str] = []
        for value in queries:
            query = self._clean_text(value, 500)
            if query and query not in normalized_queries:
                normalized_queries.append(query)
            if len(normalized_queries) == self._max_searches:
                break

        if not normalized_queries:
            return {
                "status": "no_results",
                "queries": [],
                "results": [],
                "searches": [],
                "limitations": [
                    "No bounded supplier query could be formed from the verified equipment data."
                ],
            }

        if not self._enabled:
            return {
                "status": "research_disabled",
                "queries": normalized_queries,
                "results": [],
                "searches": [],
                "limitations": [
                    "Live supplier research is disabled. Set "
                    "TAVILY_RESEARCH_ENABLED=true to enable it."
                ],
            }

        if not self._api_key:
            return {
                "status": "search_unavailable",
                "queries": normalized_queries,
                "results": [],
                "searches": [],
                "limitations": ["TAVILY_API_KEY is not configured."],
            }

        searches = [self._search_query(query) for query in normalized_queries]
        seen_urls: set[str] = set()
        results: list[dict[str, Any]] = []
        for search in searches:
            for result in search["results"]:
                url = result["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append(result)

        statuses = {search["status"] for search in searches}
        if results:
            status = "completed" if "search_unavailable" not in statuses else "partial"
        elif statuses == {"no_results"}:
            status = "no_results"
        else:
            status = "search_unavailable"

        limitations = [
            "Supplier search results are untrusted discovery material and "
            "do not establish compatibility, stock, a quotation, or a "
            "purchase price."
        ]
        if "search_unavailable" in statuses:
            limitations.append(
                "At least one supplier search was unavailable; research is incomplete."
            )

        return {
            "status": status,
            "queries": normalized_queries,
            "results": results,
            "searches": searches,
            "limitations": limitations,
        }
