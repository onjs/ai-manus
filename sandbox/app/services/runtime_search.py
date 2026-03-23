from typing import Any

import httpx

from app.core.config import settings


class RuntimeSearchService:
    def __init__(self):
        self._provider = (settings.SEARCH_PROVIDER or "duckduckgo").strip().lower()
        self._bing_api_key = settings.BING_SEARCH_API_KEY
        self._google_api_key = settings.GOOGLE_SEARCH_API_KEY
        self._google_search_engine_id = settings.GOOGLE_SEARCH_ENGINE_ID
        self._tavily_api_key = settings.TAVILY_API_KEY

    async def search_web(self, query: str, date_range: str | None = None) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return {
                "success": False,
                "message": "query is required",
                "data": {"query": q, "date_range": date_range, "total_results": 0, "results": []},
            }

        try:
            if self._provider in {"tavily"} and self._tavily_api_key:
                return await self._search_tavily(q)
            if self._provider in {"bing", "bing_web"} and self._bing_api_key:
                return await self._search_bing(q)
            if self._provider in {"google"} and self._google_api_key and self._google_search_engine_id:
                return await self._search_google(q)
            return await self._search_duckduckgo(q)
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "data": {"query": q, "date_range": date_range, "total_results": 0, "results": []},
            }

    async def _search_tavily(self, query: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": self._tavily_api_key, "query": query, "search_depth": "advanced", "max_results": 8},
            )
            response.raise_for_status()
            payload = response.json()

        results = payload.get("results")
        normalized = []
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
        return {"success": True, "message": "ok", "data": {"query": query, "results": normalized}}

    async def _search_bing(self, query: str) -> dict[str, Any]:
        headers = {"Ocp-Apim-Subscription-Key": self._bing_api_key}
        params = {"q": query, "count": 10, "textDecorations": False, "textFormat": "Raw"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.get("https://api.bing.microsoft.com/v7.0/search", headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()

        web_pages = payload.get("webPages", {})
        values = web_pages.get("value") if isinstance(web_pages, dict) else []
        normalized = []
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
        return {"success": True, "message": "ok", "data": {"query": query, "results": normalized}}

    async def _search_google(self, query: str) -> dict[str, Any]:
        params = {
            "key": self._google_api_key,
            "cx": self._google_search_engine_id,
            "q": query,
            "num": 10,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
            response.raise_for_status()
            payload = response.json()

        items = payload.get("items")
        normalized = []
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
        return {"success": True, "message": "ok", "data": {"query": query, "results": normalized}}

    async def _search_duckduckgo(self, query: str) -> dict[str, Any]:
        params = {"q": query, "format": "json", "no_redirect": 1, "no_html": 1}
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.get("https://api.duckduckgo.com/", params=params)
            response.raise_for_status()
            payload = response.json()

        normalized = []
        abstract = payload.get("AbstractText")
        abstract_url = payload.get("AbstractURL")
        heading = payload.get("Heading")
        if isinstance(abstract, str) and abstract.strip():
            normalized.append(
                {
                    "title": str(heading or query),
                    "link": str(abstract_url or ""),
                    "snippet": abstract.strip(),
                }
            )

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

        return {"success": True, "message": "ok", "data": {"query": query, "results": normalized[:10]}}


runtime_search_service = RuntimeSearchService()
