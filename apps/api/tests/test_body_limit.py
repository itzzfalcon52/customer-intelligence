import asyncio

from customer_intelligence.core.body_limit import BodyLimitMiddleware


def run(scope: dict, messages: list[dict], limit: int) -> tuple[list[dict], dict]:
    state = {"called": False, "finished": False}
    sent: list[dict] = []
    chunks = iter(messages)

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        state["called"] = True
        while (await receive()).get("more_body"):
            pass
        state["finished"] = True

    asyncio.run(BodyLimitMiddleware(app, limit_for=lambda path: limit)(scope, receive, send))
    return sent, state


def test_chunked_body_is_stopped_once_it_passes_the_limit():
    sent, state = run(
        {"type": "http", "method": "POST", "path": "/api/v1/x", "headers": []},
        [
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"5678", "more_body": False},
        ],
        limit=6,
    )
    assert not state["finished"] and sent[0]["status"] == 413


def test_declared_length_over_the_limit_is_refused_before_reading():
    sent, state = run(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/x",
            "headers": [(b"content-length", b"100")],
        },
        [{"type": "http.request", "body": b"", "more_body": False}],
        limit=10,
    )
    assert not state["called"] and sent[0]["status"] == 413


def test_a_body_within_the_limit_reaches_the_app():
    sent, state = run(
        {"type": "http", "method": "POST", "path": "/api/v1/x", "headers": []},
        [{"type": "http.request", "body": b"1234", "more_body": False}],
        limit=6,
    )
    assert state["finished"] and sent == []
