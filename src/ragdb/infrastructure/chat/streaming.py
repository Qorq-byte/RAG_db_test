"""Bounded streaming readers shared by chat adapters."""

import json
from collections.abc import Callable, Iterator

import httpx


class ChatCancelled(RuntimeError):
    def __init__(self):
        super().__init__("已停止生成，未完成的回答不会加入历史。")


class StreamingUnsupported(RuntimeError):
    def __init__(self):
        super().__init__("服务不支持流式回答，可选择“非流式重试”。")


def check_cancel(should_cancel):
    if should_cancel and should_cancel():
        raise ChatCancelled()


def stream_chat(client, url, payload, *, headers=None, timeout=60, ollama=False,
                should_cancel: Callable[[], bool] | None = None) -> Iterator[str]:
    """Require a protocol completion marker; never accept a truncated answer."""
    check_cancel(should_cancel)
    content_seen = False
    try:
        with client.stream("POST", url, json={**payload, "stream": True}, headers=headers,
                           timeout=httpx.Timeout(min(timeout, 30), connect=min(timeout, 10))) as response:
            # Only explicit protocol rejection permits a user-selected fallback.
            if response.status_code in (400, 422, 501):
                response.read()
                try:
                    error = response.json()
                    detail = json.dumps(error).lower()
                except ValueError:
                    detail = ""
                if "stream" in detail and any(word in detail for word in ("unsupported", "not support", "not implemented")):
                    raise StreamingUnsupported()
            response.raise_for_status()
            events = _json_lines(response.iter_lines(), should_cancel) if ollama else _sse_events(response.iter_lines(), should_cancel)
            for raw in events:
                check_cancel(should_cancel)
                if raw == "[DONE]" and not ollama:
                    if not content_seen:
                        raise RuntimeError("模型未返回有效回答。")
                    return
                try:
                    data = json.loads(raw)
                    if not isinstance(data, dict) or data.get("error"):
                        raise ValueError("provider error")
                    if ollama:
                        text = data.get("message", {}).get("content", "")
                        done = data.get("done") is True
                        if done and data.get("done_reason") not in (None, "stop"):
                            raise RuntimeError("回答未完整生成，请重试或缩短问题。")
                    else:
                        choices = data.get("choices", [])
                        if not choices:  # Usage-only terminal metadata.
                            continue
                        choice = choices[0]
                        if choice.get("finish_reason") not in (None, "stop"):
                            raise RuntimeError("回答未完整生成（长度限制或服务中断），请重试或缩短问题。")
                        text = (choice.get("delta") or {}).get("content") or ""
                        done = False  # SSE requires [DONE], including after finish_reason.
                    if not isinstance(text, str):
                        raise ValueError("invalid content")
                except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
                    raise RuntimeError("模型流式响应格式错误，未保存未完成回答。") from None
                if text:
                    content_seen = content_seen or bool(text.strip())
                    yield text
                if done:
                    if not content_seen:
                        raise RuntimeError("模型未返回有效回答。")
                    return
            check_cancel(should_cancel)
            raise RuntimeError("连接提前结束，回答不完整，请重试。")
    except httpx.HTTPStatusError as exc:
        if ollama and exc.response.status_code == 404:
            raise RuntimeError("本地问答模型或接口不存在。请在模型设置中选择已安装的问答模型，或保存云端配置。") from None
        raise RuntimeError(f"模型请求失败（HTTP {exc.response.status_code}），请检查模型设置与服务权限。") from None
    except httpx.HTTPError:
        check_cancel(should_cancel)
        raise RuntimeError("模型连接中断或等待超时，请检查服务后重试。") from None


def _json_lines(lines, should_cancel):
    for line in lines:
        check_cancel(should_cancel)
        if line.strip():
            yield line


def _sse_events(lines, should_cancel):
    data = []
    for line in lines:
        check_cancel(should_cancel)
        if not line:
            if data:
                yield "\n".join(data)
                data.clear()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield "\n".join(data)
