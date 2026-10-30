"""Server-sent events for long AI operations that report progress through a trace listener."""

import json
import logging
import queue
import threading
from collections.abc import Callable, Iterator
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from customer_intelligence.agent.tracing import Listener
from customer_intelligence.core.database import open_session
from customer_intelligence.core.errors import WorkflowError

logger = logging.getLogger(__name__)
# Comment lines keep proxies from closing a quiet stream while a tool runs.
KEEPALIVE_SECONDS = 15


def event_stream(
    http: Request, work: Callable[[Session, Listener], dict[str, Any]], name: str
) -> StreamingResponse:
    """Run `work` in a thread with its own workspace session and stream its trace events.

    The final event is `answer` (with `response`) or `error`. The operation completes even if the
    browser disconnects; callers must make `work` idempotent and bounded.
    """
    events: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def run() -> None:
        try:
            with open_session(http) as session:
                result = work(session, events.put)
            events.put({"type": "answer", "response": result})
        except WorkflowError as exc:
            events.put(
                {"type": "error", "code": exc.code, "message": str(exc), "status": exc.status_code}
            )
        except Exception:
            logger.exception("Streaming %s failed", name)
            events.put(
                {
                    "type": "error",
                    "code": "internal_error",
                    "message": f"The {name} failed unexpectedly. Your saved results are safe.",
                    "status": 500,
                }
            )
        finally:
            events.put(None)

    threading.Thread(target=run, name=f"{name}-stream", daemon=True).start()

    def stream() -> Iterator[str]:
        while True:
            try:
                item = events.get(timeout=KEEPALIVE_SECONDS)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if item is None:
                return
            yield f"event: {item['type']}\ndata: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
