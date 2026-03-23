import base64
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.core.config import settings


def _decode_bing_redirect(url: str) -> str:
    """Extract real destination URL from Bing /ck/a redirect."""
    try:
        parsed = urlparse(url)
        u_values = parse_qs(parsed.query).get("u", [])
        if u_values and u_values[0].startswith("a1"):
            encoded = u_values[0][2:]
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += "=" * padding
            return base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception:
        pass
    return url


class RuntimeSearchService:
    def __init__(self):
        self._provider = (settings.SEARCH_PROVIDER or "bing_web").strip().lower()
        self._bing_api_key = settings.BING_SEARCH_API_KEY
        self._google_api_key = settings.GOOGLE_SEARCH_API_KEY
        self._google_search_engine_id = settings.GOOGLE_SEARCH_ENGINE_ID
        self._tavily_api_key = settings.TAVILY_API_KEY

    @staticmethod
    def _error_result(query: str, date_range: str | None, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "message": message,
            "data": {"query": query, "date_range": date_range, "total_results": 0, "results": []},
        }

    @staticmethod
    def _ok_result(query: str, date_range: str | None, results: list[dict[str, str]], total_results: int) -> dict[str, Any]:
        return {
            "success": True,
            "message": "ok",
            "data": {
                "query": query,
                "date_range": date_range,
                "total_results": total_results,
                "results": results,
            },
        }

    async def search_web(self, query: str, date_range: str | None = None) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return self._error_result(q, date_range, "query is required")

        try:
            if self._provider == "bing_web":
                return await self._search_bing_web(q, date_range)
            if self._provider == "bing":
                if not self._bing_api_key:
                    return self._error_result(q, date_range, "BING_SEARCH_API_KEY is required when SEARCH_PROVIDER=bing")
                return await self._search_bing(q, date_range)
            if self._provider == "google":
                if not self._google_api_key or not self._google_search_engine_id:
                    return self._error_result(
                        q,
                        date_range,
                        "GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID are required when SEARCH_PROVIDER=google",
                    )
                return await self._search_google(q, date_range)
            if self._provider == "tavily":
                if not self._tavily_api_key:
                    return self._error_result(q, date_range, "TAVILY_API_KEY is required when SEARCH_PROVIDER=tavily")
                return await self._search_tavily(q, date_range)
            if self._provider == "duckduckgo":
                return await self._search_duckduckgo(q, date_range)
            return self._error_result(q, date_range, f"Unsupported SEARCH_PROVIDER={self._provider}")
        except Exception as e:
            return self._error_result(q, date_range, str(e))

    async def _search_tavily(self, query: str, date_range: str | None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": self._tavily_api_key, "query": query, "search_depth": "advanced", "max_results": 10},
            )
            response.raise_for_status()
            payload = response.json()

        results = payload.get("results")
        normalized: list[dict[str, str]] = []
        if isinstance(results, list):
            for item in results[:10]:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "title": str(item.get("title") or ""),
                        "link": str(item.get("url") or ""),
                        "snippet": str(item.get("content") or ""),
                    }
                )
        return self._ok_result(query, date_range, normalized, len(normalized))

    async def _search_bing(self, query: str, date_range: str | None) -> dict[str, Any]:
        headers = {"Ocp-Apim-Subscription-Key": self._bing_api_key}
        params = {"q": query, "count": 10, "textDecorations": False, "textFormat": "Raw"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get("https://api.bing.microsoft.com/v7.0/search", headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()

        web_pages = payload.get("webPages", {})
        values = web_pages.get("value") if isinstance(web_pages, dict) else []
        normalized: list[dict[str, str]] = []
        if isinstance(values, list):
            for item in values[:10]:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "title": str(item.get("name") or ""),
                        "link": str(item.get("url") or ""),
                        "snippet": str(item.get("snippet") or ""),
                    }
                )

        total_results = 0
        if isinstance(web_pages, dict):
            raw_total = web_pages.get("totalEstimatedMatches")
            if isinstance(raw_total, int):
                total_results = raw_total
        return self._ok_result(query, date_range, normalized, total_results or len(normalized))

    async def _search_google(self, query: str, date_range: str | None) -> dict[str, Any]:
        params = {
            "key": self._google_api_key,
            "cx": self._google_search_engine_id,
            "q": query,
            "num": 10,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
            response.raise_for_status()
            payload = response.json()

        items = payload.get("items")
        normalized: list[dict[str, str]] = []
        if isinstance(items, list):
            for item in items[:10]:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "title": str(item.get("title") or ""),
                        "link": str(item.get("link") or ""),
                        "snippet": str(item.get("snippet") or ""),
                    }
                )
        return self._ok_result(query, date_range, normalized, len(normalized))

    async def _search_bing_web(self, query: str, date_range: str | None) -> dict[str, Any]:
        params: dict[str, str] = {"q": query, "count": "20"}
        if date_range and date_range != "all":
            freshness_filters = {
                "past_hour": 'ex1:"ez1"',
                "past_day": 'ex1:"ez2"',
                "past_week": 'ex1:"ez3"',
                "past_month": 'ex1:"ez4"',
                "past_year": 'ex1:"ez5"',
            }
            f = freshness_filters.get(date_range)
            if f:
                params["filters"] = f

        async with AsyncSession(impersonate="chrome") as session:
            response = await session.get("https://www.bing.com/search", params=params, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

        normalized: list[dict[str, str]] = []
        for item in soup.find_all("li", class_="b_algo"):
            try:
                h2 = item.find("h2")
                if not h2:
                    continue
                a = h2.find("a")
                if not a:
                    continue
                title = a.get_text(strip=True)
                link = str(a.get("href", "")).strip()
                if not title or not link:
                    continue
                if "/ck/a?" in link:
                    link = _decode_bing_redirect(link)

                snippet = ""
                for tag in item.find_all(["p", "div"], class_=re.compile(r"b_lineclamp|b_descript|b_caption|b_paractl")):
                    text = tag.get_text(strip=True)
                    if len(text) > 20:
                        snippet = text
                        break
                if not snippet:
                    for p in item.find_all("p"):
                        text = p.get_text(strip=True)
                        if len(text) > 20:
                            snippet = text
                            break

                normalized.append({"title": title, "link": link, "snippet": snippet})
            except Exception:
                continue
            if len(normalized) >= 10:
                break

        total_results = 0
        for elem in soup.find_all(["span", "div"], class_=re.compile(r"sb_count|b_focusTextMedium")):
            m = re.search(r"([\d,]+)\s*results?", elem.get_text())
            if m:
                try:
                    total_results = int(m.group(1).replace(",", ""))
                    break
                except ValueError:
                    continue

        return self._ok_result(query, date_range, normalized, total_results or len(normalized))

    async def _search_duckduckgo(self, query: str, date_range: str | None) -> dict[str, Any]:
        params = {"q": query, "format": "json", "no_redirect": 1, "no_html": 1}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get("https://api.duckduckgo.com/", params=params)
            response.raise_for_status()
            payload = response.json()

        normalized: list[dict[str, str]] = []
        abstract = payload.get("AbstractText")
        abstract_url = payload.get("AbstractURL")
        heading = payload.get("Heading")
        if isinstance(abstract, str) and abstract.strip():
            normalized.append({"title": str(heading or query), "link": str(abstract_url or ""), "snippet": abstract.strip()})

        related = payload.get("RelatedTopics")
        if isinstance(related, list):
            for item in related:
                if not isinstance(item, dict):
                    continue
                if "Text" in item and "FirstURL" in item:
                    normalized.append(
                        {
                            "title": str(item.get("Text") or query),
                            "link": str(item.get("FirstURL") or ""),
                            "snippet": str(item.get("Text") or ""),
                        }
                    )
                topics = item.get("Topics")
                if isinstance(topics, list):
                    for sub in topics:
                        if not isinstance(sub, dict):
                            continue
                        if "Text" in sub and "FirstURL" in sub:
                            normalized.append(
                                {
                                    "title": str(sub.get("Text") or query),
                                    "link": str(sub.get("FirstURL") or ""),
                                    "snippet": str(sub.get("Text") or ""),
                                }
                            )
                if len(normalized) >= 10:
                    break

        return self._ok_result(query, date_range, normalized[:10], len(normalized[:10]))


runtime_search_service = RuntimeSearchService()
