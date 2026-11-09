"""Find web pages for a query. Local work uses a stand-in; real use asks Tavily."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

import httpx

from app.config import settings

TAVILY_URL = "https://api.tavily.com/search"


class WebSearchError(Exception):
    """The web search service rejected the request or could not be reached."""


@dataclass
class WebResult:
    title: str
    url: str
    snippet: str

    @property
    def domain(self) -> str:
        host = urlsplit(self.url).hostname or ""
        return host.removeprefix("www.")


class WebSearch(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 8) -> list[WebResult]: ...


class FakeWebSearch(WebSearch):
    """Local stand-in. It returns made-up addresses, so use real links to try the full flow."""

    def search(self, query: str, max_results: int = 8) -> list[WebResult]:
        return [
            WebResult(
                title=f"Example policy {n} for: {query[:60]}",
                url=f"https://example{n}.org/policy",
                snippet="(local stand-in result, not a real page)",
            )
            for n in range(1, min(max_results, 3) + 1)
        ]


class TavilySearch(WebSearch):
    def __init__(self, api_key: str, transport=None):
        self._api_key = api_key
        self._transport = transport

    def search(self, query: str, max_results: int = 8) -> list[WebResult]:
        body = {
            "query": query[:400],
            "max_results": max(1, min(max_results, 20)),
            "search_depth": "basic",  # 1 credit per search
            "include_answer": False,
        }
        try:
            with httpx.Client(timeout=15.0, transport=self._transport, trust_env=False) as client:
                response = client.post(
                    TAVILY_URL, json=body, headers={"Authorization": f"Bearer {self._api_key}"}
                )
        except httpx.HTTPError:
            raise WebSearchError("The web search service could not be reached.") from None
        if response.status_code in (401, 403):
            raise WebSearchError("The web search service rejected the API key.")
        if response.status_code == 429:
            raise WebSearchError("The web search limit was reached. Try again later.")
        if response.status_code >= 400:
            raise WebSearchError(f"The web search service returned an error ({response.status_code}).")
        try:
            items = response.json().get("results") or []
        except ValueError:
            raise WebSearchError("The web search service sent an unreadable reply.") from None
        results: list[WebResult] = []
        for item in items:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            results.append(
                WebResult(
                    title=str(item.get("title") or url).strip()[:200],
                    url=url,
                    snippet=" ".join(str(item.get("content") or "").split())[:300],
                )
            )
        return results


@lru_cache
def get_web_search() -> WebSearch:
    if settings.web_search_backend == "tavily":
        if not settings.tavily_api_key:
            raise RuntimeError("WEB_SEARCH_BACKEND=tavily but TAVILY_API_KEY is empty")
        return TavilySearch(settings.tavily_api_key)
    return FakeWebSearch()
