from app.services.supplier_search_service import SupplierSearchService


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "results": [{
                "title": "Example motor cooling fan",
                "url": "https://supplier.example/fan-1",
                "content": "Example source material only.",
                "score": 0.9,
            }],
        }


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def test_missing_tavily_credential_is_safe_and_does_not_call_network(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    client = FakeHttpClient()
    result = SupplierSearchService(
        api_key=None,
        enabled=True,
        http_client=client,
    ).search_parts(["motor fan"])

    assert result["status"] == "search_unavailable"
    assert result["results"] == []
    assert client.calls == []


def test_search_is_bounded_deduplicated_and_cached():
    client = FakeHttpClient()
    service = SupplierSearchService(
        api_key="test-key",
        enabled=True,
        http_client=client,
        max_searches=3,
        cache_ttl_seconds=60,
    )

    first = service.search_parts(["motor fan", "motor fan", "docs", "ignored"])
    second = service.search_parts(["motor fan", "docs"])

    assert first["status"] == "completed"
    assert len(first["results"]) == 1
    assert len(client.calls) == 3
    assert second["status"] == "completed"
    assert len(client.calls) == 3
    assert client.calls[0][1]["headers"]["Authorization"] == "Bearer test-key"
    assert client.calls[0][1]["json"]["max_results"] == 5


def test_disabled_research_is_structured_not_an_error():
    result = SupplierSearchService(
        api_key="test-key",
        enabled=False,
        http_client=FakeHttpClient(),
    ).search_parts(["motor fan"])

    assert result["status"] == "research_disabled"
    assert result["results"] == []
