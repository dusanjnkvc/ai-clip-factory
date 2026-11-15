import asyncio

from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient

from app.request_limits import RequestBodyLimitMiddleware, RequestBodyTooLarge


def run_request(app, bodies, *, headers=None, path="/api/sources"):
    sent = []
    consumed = []
    iterator = iter(bodies)

    async def receive():
        value = next(iterator)
        consumed.append(value)
        return value

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": path, "headers": headers or []}
    asyncio.run(app(scope, receive, send))
    return sent, consumed


async def consuming_app(scope, receive, send):
    while True:
        message = await receive()
        if not message.get("more_body", False):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_oversized_declared_body_rejected_before_application_or_receive():
    messages, consumed = run_request(RequestBodyLimitMiddleware(consuming_app, 10), [], headers=[(b"content-length", b"11")])
    assert messages[0]["status"] == 413
    assert consumed == []


def test_chunked_body_is_bounded_even_without_content_length():
    bodies = [
        {"type": "http.request", "body": b"123456", "more_body": True},
        {"type": "http.request", "body": b"78901", "more_body": True},
        {"type": "http.request", "body": b"never-read", "more_body": False},
    ]
    messages, consumed = run_request(RequestBodyLimitMiddleware(consuming_app, 10), bodies)
    assert messages[0]["status"] == 413
    assert len(consumed) == 2


def test_small_body_reaches_application_without_buffering_or_modification():
    bodies = [{"type": "http.request", "body": b"12345", "more_body": False}]
    messages, consumed = run_request(RequestBodyLimitMiddleware(consuming_app, 5), bodies)
    assert messages[0]["status"] == 200
    assert consumed == bodies


def test_application_catching_read_error_cannot_return_success():
    async def app(scope, receive, send):
        try:
            await receive()
        except RequestBodyTooLarge:
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"must not escape"})

    messages, _ = run_request(RequestBodyLimitMiddleware(app, 3), [{"type": "http.request", "body": b"1234"}])
    assert [message.get("status") for message in messages if message["type"] == "http.response.start"] == [413]
    assert b"must not escape" not in b"".join(message.get("body", b"") for message in messages)


def test_fastapi_multipart_is_rejected_before_endpoint_runs():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=100)
    entered = []

    @app.post("/api/sources")
    async def upload(file: UploadFile = File(...)):
        entered.append(True)
        return {"size": len(await file.read())}

    with TestClient(app) as client:
        response = client.post("/api/sources", files={"file": ("large.mp4", b"x" * 101, "video/mp4")})
    assert response.status_code == 413
    assert entered == []


def test_non_http_scope_passes_through():
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    async def unused():
        raise AssertionError("Should not consume non-HTTP input")

    asyncio.run(RequestBodyLimitMiddleware(app, 1)({"type": "lifespan"}, unused, unused))
    assert seen == ["lifespan"]
