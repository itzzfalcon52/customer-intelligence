"""Record live provider exchanges once, then replay them offline for free, repeatable evals.

Only response bodies and a small request fingerprint (tool names, message count) are stored.
Headers, API keys and request bodies are never written. Run-specific IDs become placeholders so a
fresh workspace can replay a cassette recorded in another workspace.
"""

import json
from pathlib import Path
from typing import Any

import httpx

CASSETTE_DIRECTORY = Path(__file__).resolve().parent / "cassettes"


class CassetteMismatch(RuntimeError):
    pass


def _fingerprint(body: dict[str, Any]) -> dict[str, Any]:
    tools = sorted(tool["function"]["name"] for tool in body.get("tools") or [])
    return {"tools": tools, "messages": len(body.get("messages", []))}


def _substitute(text: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


class Exchange:
    """Shared by both transports: keeps the decoded requests for graders."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []


class RecordingTransport(httpx.BaseTransport, Exchange):
    def __init__(self, inner: httpx.BaseTransport, identifiers: dict[str, str]) -> None:
        Exchange.__init__(self)
        self.inner = inner
        # actual ID -> placeholder
        self.identifiers = identifiers
        self.entries: list[dict[str, Any]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        response = self.inner.handle_request(request)
        content = response.read()
        entry: dict[str, Any] = {"request": _fingerprint(body), "status": response.status_code}
        try:
            entry["body"] = json.loads(_substitute(content.decode(), self.identifiers))
        except ValueError:
            entry["body"] = None
        self.entries.append(entry)
        # read() already decoded the body, so encoding/length headers no longer apply.
        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
        }
        return httpx.Response(response.status_code, content=content, headers=headers)

    def close(self) -> None:
        self.inner.close()

    def save(self, name: str) -> Path:
        CASSETTE_DIRECTORY.mkdir(exist_ok=True)
        path = CASSETTE_DIRECTORY / f"{name}.json"
        path.write_text(json.dumps(self.entries, indent=2, sort_keys=True) + "\n")
        return path


class ReplayTransport(httpx.BaseTransport, Exchange):
    def __init__(self, name: str, identifiers: dict[str, str]) -> None:
        Exchange.__init__(self)
        path = CASSETTE_DIRECTORY / f"{name}.json"
        if not path.exists():
            raise CassetteMismatch(
                f"No cassette for {name!r}. Record one with: pnpm eval:agent:record"
            )
        self.name = name
        self.entries = json.loads(path.read_text())
        # placeholder -> actual ID
        self.identifiers = {placeholder: actual for actual, placeholder in identifiers.items()}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        index = len(self.requests) - 1
        if index >= len(self.entries):
            raise CassetteMismatch(f"{self.name}: more provider calls than were recorded.")
        entry = self.entries[index]
        if entry["request"] != _fingerprint(body):
            raise CassetteMismatch(
                f"{self.name}: request {index + 1} differs from the recording "
                f"({entry['request']} != {_fingerprint(body)}). Re-record the cassette."
            )
        content = _substitute(json.dumps(entry["body"]), self.identifiers)
        return httpx.Response(
            entry["status"], content=content, headers={"content-type": "application/json"}
        )
