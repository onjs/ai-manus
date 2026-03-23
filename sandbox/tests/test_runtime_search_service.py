import pytest

from app.services.runtime_search import RuntimeSearchService


@pytest.mark.asyncio
async def test_runtime_search_returns_results_list_on_error(monkeypatch):
    service = RuntimeSearchService()
    service._provider = "duckduckgo"  # noqa: SLF001

    async def _raise_error(_query: str):  # noqa: ANN001
        raise RuntimeError("network down")

    monkeypatch.setattr(service, "_search_duckduckgo", _raise_error)

    result = await service.search_web("hello world")

    assert result["success"] is False
    assert isinstance(result["data"], dict)
    assert result["data"]["results"] == []
    assert result["data"]["total_results"] == 0


@pytest.mark.asyncio
async def test_runtime_search_empty_query_includes_results_list():
    service = RuntimeSearchService()
    result = await service.search_web("")

    assert result["success"] is False
    assert isinstance(result["data"], dict)
    assert result["data"]["results"] == []
    assert result["data"]["total_results"] == 0


@pytest.mark.asyncio
async def test_runtime_search_bing_web_dispatch(monkeypatch):
    service = RuntimeSearchService()
    service._provider = "bing_web"  # noqa: SLF001

    async def _fake_bing_web(query: str, date_range: str | None):  # noqa: ANN001
        return {
            "success": True,
            "message": "ok",
            "data": {
                "query": query,
                "date_range": date_range,
                "total_results": 1,
                "results": [{"title": "t", "link": "l", "snippet": "s"}],
            },
        }

    monkeypatch.setattr(service, "_search_bing_web", _fake_bing_web)
    result = await service.search_web("hello", "past_day")

    assert result["success"] is True
    assert result["data"]["results"][0]["title"] == "t"
    assert result["data"]["total_results"] == 1
