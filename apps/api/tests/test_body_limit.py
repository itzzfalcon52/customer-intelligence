import asyncio

from customer_intelligence.core.body_limit import BodyLimitMiddleware


def test_chunked_body_is_bounded_before_parsing():
    async def check():
        called = False
        sent = []
        chunks = iter(
            [
                {"type": "http.request", "body": b"1234", "more_body": True},
                {"type": "http.request", "body": b"5678", "more_body": False},
            ]
        )

        async def receive():
            return next(chunks)

        async def send(message):
            sent.append(message)

        async def app(scope, receive, send):
            nonlocal called
            called = True

        await BodyLimitMiddleware(app, max_bytes=6)(
            {"type": "http", "method": "POST"}, receive, send
        )
        assert not called and sent[0]["status"] == 413

    asyncio.run(check())
