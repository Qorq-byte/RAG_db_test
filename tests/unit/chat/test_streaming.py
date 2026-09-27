import json
from threading import Event

import httpx
import pytest

from ragdb.infrastructure.chat.streaming import ChatCancelled, StreamingUnsupported, stream_chat


class Fragments(httpx.SyncByteStream):
    def __init__(self, content):
        self.content = content
        self.closed = False

    def __iter__(self):
        for index in range(0, len(self.content), 2):
            yield self.content[index:index + 2]

    def close(self):
        self.closed = True


@pytest.mark.parametrize("ollama", [False, True])
def test_split_utf8_stream_emits_incrementally_and_closes(ollama):
    if ollama:
        body = '\n'.join(json.dumps(x, ensure_ascii=False) for x in [
            {"message": {"content": "你好"}, "done": False},
            {"message": {"content": "世界"}, "done": True},
        ])
    else:
        body = ': heartbeat\n\n' + ''.join('data: ' + json.dumps({"choices": [{"delta": {"content": t}}]}, ensure_ascii=False) + '\n\n' for t in ["你好", "世界"]) + 'data: [DONE]\n\n'
    fragments = Fragments(body.encode())
    def response(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, stream=fragments)
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        chunks = stream_chat(client, 'http://test/chat', {}, ollama=ollama)
        assert next(chunks) == '你好'
        assert not fragments.closed
        assert list(chunks) == ['世界']
    assert fragments.closed


@pytest.mark.parametrize("body", [
    'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
    'data: broken\n\n',
    'data: {"error":{"message":"private-key"}}\n\n',
    'data: [DONE]\n\n',
    'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":"length"}]}\n\n',
])
def test_invalid_or_truncated_stream_is_never_success(body):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))) as client:
        with pytest.raises(RuntimeError) as error:
            list(stream_chat(client, 'http://test/chat', {}))
        assert 'private-key' not in str(error.value)


def test_cancel_closes_response_without_consuming_remainder():
    cancelled = Event()
    fragments = Fragments(b'data: {"choices":[{"delta":{"content":"a"}}]}\n\ndata: [DONE]\n\n')
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=fragments))) as client:
        chunks = stream_chat(client, 'http://test/chat', {}, should_cancel=cancelled.is_set)
        assert next(chunks) == 'a'
        cancelled.set()
        with pytest.raises(ChatCancelled):
            next(chunks)
    assert fragments.closed


@pytest.mark.parametrize('status,body,kind', [
    (400, {'error': 'stream is not supported'}, StreamingUnsupported),
    (401, {'error': 'private-key'}, RuntimeError),
    (429, {'error': 'limit'}, RuntimeError),
])
def test_http_errors_do_not_retry_or_expose_body(status, body, kind):
    requests = []
    def response(request):
        requests.append(request)
        return httpx.Response(status, json=body)
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(kind) as error:
            list(stream_chat(client, 'http://test/chat', {}))
    assert len(requests) == 1
    assert 'private-key' not in str(error.value)
