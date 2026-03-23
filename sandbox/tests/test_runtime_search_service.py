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
