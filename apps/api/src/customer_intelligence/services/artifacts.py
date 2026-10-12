import json
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from customer_intelligence.core.errors import WorkflowError


def read_json(path: Path, limit: int = 20_000_000) -> dict | list:
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except FileNotFoundError as exc:
        raise WorkflowError("Artifact not found.", 404) from exc
    if len(data) > limit:
        raise WorkflowError("Artifact exceeds the size limit.", 409)
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise WorkflowError("Artifact JSON is invalid.", 409) from exc


def publish_json(directory: Path, documents: dict[str, dict | list], artifact_id: UUID) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    staging = directory / f".{artifact_id}.{uuid4().hex}.tmp"
    staging.mkdir()
    destination = directory / str(artifact_id)
    try:
        for name, payload in documents.items():
            (staging / name).write_text(
                json.dumps(payload, allow_nan=False, ensure_ascii=False), encoding="utf-8"
            )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
