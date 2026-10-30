"""The workspace's own customer-success playbooks, chunked for cited retrieval.

Playbooks are plain text or Markdown the user uploads. Each is split into heading-aware passages
and searched with BM25 (lexical, deterministic, no provider call). Search results carry a citation
ID (`P<n>`) and an evidence path, so recommendations can quote the passage they rely on. Playbook
text is untrusted data: it is returned to the assistant as evidence, never as instructions.
"""

import json
import math
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.services.artifacts import read_json

MAX_BYTES = 1024 * 1024
MAX_PLAYBOOKS = 50
CHUNK_CHARS = 900
SUFFIXES = (".md", ".markdown", ".txt")
WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have how i if in is it its of on or our so that the "
    "their them then there this to was we what when which who will with you your".split()
)


def _root(settings: Settings) -> Path:
    return settings.data_directory / "playbooks"


def tokens(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 1]


def chunk(text: str) -> list[dict]:
    """Split on Markdown headings and blank lines; passages keep their nearest heading."""
    passages: list[dict] = []
    heading = ""
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        buffer.clear()
        if body:
            passages.append({"heading": heading, "text": body})

    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        block = block.strip()
        if not block:
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", block.splitlines()[0])
        if match:
            flush()
            heading = match.group(2)
            block = "\n".join(block.splitlines()[1:]).strip()
            if not block:
                continue
        if buffer and sum(len(b) for b in buffer) + len(block) > CHUNK_CHARS:
            flush()
        while len(block) > CHUNK_CHARS:
            cut = block.rfind(" ", 0, CHUNK_CHARS)
            cut = cut if cut > CHUNK_CHARS // 2 else CHUNK_CHARS
            buffer.append(block[:cut])
            flush()
            block = block[cut:].strip()
        buffer.append(block)
    flush()
    return passages


def create(settings: Settings, filename: str, title: str | None, content: bytes) -> dict:
    if not filename.lower().endswith(SUFFIXES):
        raise WorkflowError("Upload a Markdown (.md) or plain text (.txt) playbook.")
    if len(content) > MAX_BYTES:
        raise WorkflowError("Playbooks are limited to 1 MB of text.", 413)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkflowError("The playbook must be UTF-8 text.") from exc
    passages = chunk(text)
    if not passages:
        raise WorkflowError("The playbook has no text.")
    if len(list_playbooks(settings)) >= MAX_PLAYBOOKS:
        raise WorkflowError(f"A workspace can hold at most {MAX_PLAYBOOKS} playbooks.", 409)
    playbook_id = uuid4()
    directory = _root(settings) / str(playbook_id)
    directory.mkdir(parents=True)
    name = (title or "").strip() or Path(filename).stem.replace("_", " ").replace("-", " ")
    manifest = {
        "id": str(playbook_id),
        "title": name[:120],
        "filename": Path(filename).name[:200],
        "created_at": datetime.now(UTC).isoformat(),
        "characters": len(text),
        "passages": len(passages),
    }
    (directory / "passages.json").write_text(json.dumps(passages))
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _manifest(settings: Settings, playbook_id: UUID) -> dict:
    path = _root(settings) / str(playbook_id) / "manifest.json"
    if not path.exists():
        raise WorkflowError("Playbook not found.", 404)
    manifest = read_json(path)
    if not isinstance(manifest, dict) or manifest.get("id") != str(playbook_id):
        raise WorkflowError("Invalid playbook manifest.", 409)
    return manifest


def _passages(settings: Settings, playbook_id: UUID) -> list[dict]:
    passages = read_json(_root(settings) / str(playbook_id) / "passages.json")
    if not isinstance(passages, list):
        raise WorkflowError("Invalid playbook passages.", 409)
    return passages


def read_playbook(settings: Settings, playbook_id: UUID) -> dict:
    return {**_manifest(settings, playbook_id), "content": _passages(settings, playbook_id)}


def list_playbooks(settings: Settings) -> list[dict]:
    root = _root(settings)
    if not root.exists():
        return []
    out = []
    for path in root.iterdir():
        try:
            out.append(_manifest(settings, UUID(path.name)))
        except (ValueError, WorkflowError):
            continue
    return sorted(out, key=lambda m: m["created_at"], reverse=True)


def delete(settings: Settings, playbook_id: UUID) -> None:
    _manifest(settings, playbook_id)
    directory = _root(settings) / str(playbook_id)
    for path in directory.iterdir():
        path.unlink()
    directory.rmdir()


def search(settings: Settings, query: str, limit: int = 4) -> dict:
    """BM25 over every passage in the workspace; returns cited passages, best first."""
    corpus: list[tuple[dict, int, dict, list[str]]] = []
    for manifest in list_playbooks(settings):
        for index, passage in enumerate(_passages(settings, UUID(manifest["id"]))):
            words = tokens(f"{passage['heading']} {passage['text']}")
            corpus.append((manifest, index, passage, words))
    terms = list(dict.fromkeys(tokens(query)))
    if not corpus or not terms:
        return {"query": query, "results": [], "note": "No playbook passages matched."}
    average = sum(len(w) for *_, w in corpus) / len(corpus)
    frequency = Counter(t for *_, words in corpus for t in set(words))
    k1, b = 1.5, 0.75
    scored = []
    for manifest, index, passage, words in corpus:
        counts = Counter(words)
        score = 0.0
        for term in terms:
            if term not in counts:
                continue
            idf = math.log(1 + (len(corpus) - frequency[term] + 0.5) / (frequency[term] + 0.5))
            tf = counts[term]
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(words) / average))
        if score > 0:
            scored.append((score, manifest, index, passage))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = [
        {
            "citation": f"P{rank}",
            "playbook_id": manifest["id"],
            "playbook": manifest["title"],
            "passage": index,
            "heading": passage["heading"],
            "text": passage["text"],
            "evidence_path": f"/api/v1/playbooks/{manifest['id']}#passage-{index}",
        }
        for rank, (_, manifest, index, passage) in enumerate(scored[:limit], start=1)
    ]
    return {
        "query": query,
        "results": results,
        "note": "Passages from the user's own playbooks, ranked by keyword relevance. Cite them "
        "by citation ID; they describe intended practice, not measured outcomes.",
    }
