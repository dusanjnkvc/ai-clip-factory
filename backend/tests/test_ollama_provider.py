"""Local HTTP boundary tests. These doubles do not establish GPU/model readiness."""
import base64
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from app.services.media import ConfigurationError, PipelineError
from app.services.ollama_provider import InferenceCancelled, OllamaProvider


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    summary: str
    count: int


@pytest.fixture(autouse=True)
def clean_configuration(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("OLLAMA_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("FREE_MODE", "true")


def provider(handler=None, *, cancel=None, model=None, tags=None, capabilities=None):
    requests = []

    def route(request):
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": tags if tags is not None else [{"name": model or "qwen3-vl:4b", "size": 3000000000, "digest": "local-test-digest"}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": capabilities or ["completion", "vision"], "thinking": {"values": [False, True]}})
        if handler:
            return handler(request)
        return httpx.Response(200, text='{"message":{"content":"{\\"summary\\":\\"Measured source\\",\\"count\\":2}"},"done":true,"eval_count":12}\n')

    result = OllamaProvider(cancel, transport=httpx.MockTransport(route))
    return result, requests


def test_defaults_and_strict_json_schema_output_stay_local_without_keys():
    adapter, requests = provider()
    result = adapter.structured(Answer, "Analyze supplied evidence.", "Only the supplied source.")
    assert result == Answer(summary="Measured source", count=2)
    assert adapter.model == "qwen3-vl:4b" and adapter.context_size == 4096
    assert adapter.max_concurrency == 1
    assert all(request.url.host == "127.0.0.1" for request in requests)
    request = requests[-1]
    payload = json.loads(request.content)
    assert request.url.path == "/api/chat"
    assert payload["format"] == Answer.model_json_schema()
    assert payload["stream"] is True and payload["keep_alive"] == 0
    assert payload["think"] is False
    assert payload["options"]["num_ctx"] == 4096
    assert "authorization" not in request.headers
    assert adapter.usage[0]["cost_usd"] == 0
    assert adapter.usage[0]["model_digest"] == "local-test-digest"


def test_gpu_memory_error_retries_same_local_model_on_cpu():
    chats=[]
    def handler(request):
        if request.url.path=='/api/generate':return httpx.Response(200,json={'done':True})
        chats.append(json.loads(request.content))
        if len(chats)==1:return httpx.Response(500,json={'error':'CUDA out of memory'})
        return httpx.Response(200,text='{"message":{"content":"{\\"summary\\":\\"Actual retry contract\\",\\"count\\":1}"},"done":true}\n')
    adapter,_=provider(handler)
    answer=adapter.structured(Answer,'Analyze locally.','Bounded input.')
    assert answer.count==1 and chats[1]['options']['num_gpu']==0
    assert chats[0]['model']==chats[1]['model']
    assert adapter.usage[-1]['memory_recovery']=='same_local_model_on_cpu_after_gpu_memory_error'


@pytest.mark.parametrize("url", ["https://api.ollama.com", "http://192.168.1.2:11434", "http://127.0.0.1:11434/api", "http://user:password@localhost:11434", "http://localhost:11434?key=secret", "http://localhost:11434#fragment"])
def test_non_loopback_or_embedded_url_state_is_rejected_before_http(monkeypatch, url):
    monkeypatch.setenv("OLLAMA_BASE_URL", url)
    with pytest.raises(ConfigurationError, match="loopback"):
        OllamaProvider()


def test_settings_are_configurable_and_bounded(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "local-vision:4b")
    monkeypatch.setenv("OLLAMA_CONTEXT_SIZE", "8192")
    monkeypatch.setenv("OLLAMA_MAX_CONCURRENCY", "2")
    adapter = OllamaProvider()
    assert adapter.model == "local-vision:4b" and adapter.context_size == 8192 and adapter.max_concurrency == 2
    monkeypatch.setenv("OLLAMA_MAX_CONCURRENCY", "0")
    with pytest.raises(ConfigurationError, match="between"):
        OllamaProvider()


def test_missing_model_is_an_honest_unavailable_status_without_generation_or_pull():
    adapter, requests = provider(tags=[])
    assert adapter.status()["available"] is False
    with pytest.raises(ConfigurationError, match="not installed"):
        adapter.structured(Answer, "System", "Source")
    assert all(request.url.path == "/api/tags" for request in requests)


@pytest.mark.parametrize("entry", [{"name": "qwen3-vl:4b", "size": 0, "digest": "stub"}, {"name": "qwen3-vl:4b", "size": 2000, "digest": "remote", "remote_host": "https://ollama.com", "remote_model": "qwen3-vl"}])
def test_local_endpoint_cannot_silently_proxy_a_remote_model(entry):
    adapter, requests = provider(tags=[entry])
    with pytest.raises(ConfigurationError, match="Remote/cloud"):
        adapter.structured(Answer, "System", "Source")
    assert all(request.url.path == "/api/tags" for request in requests)


def test_cloud_model_name_is_rejected(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3-vl:cloud")
    with pytest.raises(ConfigurationError, match="cloud model"):
        OllamaProvider()


def test_frame_data_and_timestamps_are_sent_as_local_base64_not_urls():
    adapter, requests = provider()
    encoded = base64.b64encode(b"local-sampled-image").decode()
    adapter.structured(Answer, "System", "Source", [{"timestamp": 3.25, "data_url": "data:image/jpeg;base64," + encoded}])
    message = json.loads(requests[-1].content)["messages"][-1]
    assert message["images"] == [encoded] and "3.25 seconds" in message["content"]
    with pytest.raises(PipelineError, match="remote URLs"):
        adapter.structured(Answer, "System", "Source", [{"data_url": "https://example.com/frame.jpg"}])


def test_vision_capability_is_required_for_frames():
    adapter, requests = provider(capabilities=["completion"])
    with pytest.raises(ConfigurationError, match="capabilities"):
        adapter.structured(Answer, "System", "Source", [{"timestamp": 0, "data_url": "data:image/jpeg;base64,eA=="}])
    assert not any(request.url.path == "/api/chat" for request in requests)


@pytest.mark.parametrize("content", ['{"summary":"Source","count":"2"}', '{"summary":"Source","count":2,"invented":"field"}', 'not json'])
def test_output_schema_rejects_coercion_unknown_fields_and_invalid_json(content):
    adapter, _ = provider(lambda request: httpx.Response(200, text=json.dumps({"message": {"content": content}, "done": True}) + "\n"))
    with pytest.raises(PipelineError, match="strict schema"):
        adapter.structured(Answer, "System", "Source")
    assert adapter.usage == []


def test_partial_or_error_stream_is_not_a_success():
    for response in [{"message": {"content": '{"summary":"Source","count":2}'}}, {"error": "out of memory"}]:
        adapter, _ = provider(lambda request: httpx.Response(200, text=json.dumps(response) + "\n"))
        with pytest.raises(PipelineError):
            adapter.structured(Answer, "System", "Source")


def test_provider_forbids_unknown_output_fields_even_for_a_legacy_schema():
    class LegacyAnswer(BaseModel):
        summary: str
    adapter, _ = provider(lambda request: httpx.Response(200, text=json.dumps({"message": {"content": '{"summary":"Source","invented":"field"}'}, "done": True}) + "\n"))
    with pytest.raises(PipelineError, match="strict schema"):
        adapter.structured(LegacyAnswer, "System", "Source")


def test_retry_is_bounded_for_busy_server(monkeypatch):
    count = 0
    def busy(request):
        nonlocal count
        count += 1
        return httpx.Response(503)
    adapter, _ = provider(busy)
    with pytest.raises(PipelineError, match="disconnected"):
        adapter.structured(Answer, "System", "Source")
    assert count == 2


def test_cancelled_job_never_reaches_http():
    event = threading.Event(); event.set()
    adapter, requests = provider(cancel=event)
    with pytest.raises(InferenceCancelled):
        adapter.structured(Answer, "System", "Source")
    assert requests == []


def test_cancellation_during_stream_releases_the_slot():
    event = threading.Event()
    class CancelStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"message":{"content":"{"},"done":false}\n'
            event.set()
            yield b'{"message":{"content":"}"},"done":true}\n'
    adapter, _ = provider(lambda request: httpx.Response(200, stream=CancelStream()), cancel=event)
    with pytest.raises(InferenceCancelled):
        adapter.structured(Answer, "System", "Source")
    assert adapter._limiter.active == 0


def test_default_single_inference_slot_is_shared_between_provider_instances():
    active, maximum = 0, 0
    lock = threading.Lock()
    def slow(request):
        nonlocal active, maximum
        with lock:
            active += 1; maximum = max(maximum, active)
        time.sleep(.08)
        with lock:
            active -= 1
        return httpx.Response(200, text=json.dumps({"message": {"content": '{"summary":"Source","count":2}'}, "done": True}) + "\n")
    first, _ = provider(slow); second, _ = provider(slow)
    with ThreadPoolExecutor(2) as executor:
        futures = [executor.submit(adapter.structured, Answer, "System", "Source") for adapter in [first, second]]
        assert all(future.result().count == 2 for future in futures)
    assert maximum == 1


def test_unload_requests_zero_residency_without_generation():
    adapter, requests = provider(lambda request: httpx.Response(200, json={"done": True}))
    adapter.unload()
    assert requests[-1].url.path == "/api/generate"
    assert json.loads(requests[-1].content) == {"model": "qwen3-vl:4b", "keep_alive": 0, "stream": False}
