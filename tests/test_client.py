from mtg_microsoft_auth.client import GraphClient


class StubResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def json(self) -> dict:
        return self.payload


def test_get_all_stops_at_max_items(monkeypatch):
    client = GraphClient(auth_session=None)
    responses = iter(
        [
            StubResponse(
                {
                    "value": [{"id": "1"}, {"id": "2"}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
                }
            ),
            StubResponse(
                {
                    "value": [{"id": "3"}, {"id": "4"}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/unneeded",
                }
            ),
        ]
    )
    calls = []

    def request(method, url, params=None):
        calls.append((method, url, params))
        return next(responses)

    monkeypatch.setattr(client, "_request_with_retry", request)

    payload = client.get_all("/messages", params={"$top": 2}, max_items=3)

    assert payload == {"value": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}
    assert calls == [
        ("GET", "https://graph.microsoft.com/v1.0/messages", {"$top": 2}),
        ("GET", "https://graph.microsoft.com/v1.0/next", None),
    ]


def test_get_all_without_limit_preserves_existing_behavior(monkeypatch):
    client = GraphClient(auth_session=None)
    responses = iter(
        [
            StubResponse(
                {
                    "value": [{"id": "1"}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
                }
            ),
            StubResponse({"value": [{"id": "2"}]}),
        ]
    )
    monkeypatch.setattr(client, "_request_with_retry", lambda *args, **kwargs: next(responses))

    assert client.get_all("/messages") == {"value": [{"id": "1"}, {"id": "2"}]}


def test_get_all_zero_limit_skips_graph(monkeypatch):
    client = GraphClient(auth_session=None)
    monkeypatch.setattr(
        client,
        "_request_with_retry",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Graph should not be called")),
    )

    assert client.get_all("/messages", max_items=0) == {"value": []}
