import json
from hashlib import sha256
from uuid import uuid4

import pandas as pd
import sklearn

from customer_intelligence.core.config import Settings
from customer_intelligence.ml.splitting import (
    SplitValidationError,
    make_partitions,
    make_time_partitions,
)
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.split import (
    PartitionSummary,
    SplitArtifact,
    SplitResponse,
)
from customer_intelligence.schemas.task import TaskResponse, fingerprint_payload
from customer_intelligence.services.profiling import load_dataset_frame


def prepare_split(
    task: Task,
    dataset: Dataset,
    settings: Settings,
) -> SplitResponse:
    if task.dataset_id != dataset.id:
        raise SplitValidationError("The task does not belong to this dataset.")

    if task.evaluation_strategy not in {"stratified_random", "time_ordered"}:
        raise SplitValidationError("Unsupported evaluation strategy.")

    frame = load_dataset_frame(
        dataset,
        settings,
        expected_sha256=task.dataset_sha256,
    )

    if bool(frame.duplicated().any()):
        raise SplitValidationError(
            "The dataset contains duplicate rows. Resolve their treatment before splitting."
        )

    mapped = frame[task.target_column].map(task.label_mapping)

    if bool(mapped.isna().any()):
        raise SplitValidationError("The target contains missing or unmapped labels.")

    labels = [int(value) for value in mapped]
    if task.evaluation_strategy == "time_ordered":
        if not task.time_column or task.time_column not in frame.columns:
            raise SplitValidationError("The time column for this task is missing.")
        partitions = make_time_partitions(labels, frame[task.time_column].tolist())
    else:
        partitions = make_partitions(labels, task.random_seed)
    summaries: dict[str, PartitionSummary] = {}

    for name, positions in partitions.items():
        counts = frame[task.target_column].iloc[pd.Index(positions)].value_counts()
        summaries[name] = PartitionSummary(
            row_count=len(positions),
            class_counts={str(label): int(count) for label, count in counts.items()},
        )

    summary = SplitResponse(
        task_id=task.id,
        dataset_id=dataset.id,
        dataset_sha256=task.dataset_sha256,
        random_seed=task.random_seed,
        strategy="time_ordered"
        if task.evaluation_strategy == "time_ordered"
        else "stratified_random",
        train=summaries["train"],
        validation=summaries["validation"],
        test=summaries["test"],
    )

    configuration = fingerprint_payload(TaskResponse.model_validate(task))
    fingerprint = sha256(json.dumps(configuration, sort_keys=True).encode("utf-8")).hexdigest()

    artifact = SplitArtifact(
        task_fingerprint=fingerprint,
        sklearn_version=sklearn.__version__,
        summary=summary,
        row_assignments=partitions,
    )

    directory = settings.data_directory / "splits"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{task.id}.json"

    if destination.exists():
        try:
            existing = SplitArtifact.model_validate_json(destination.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SplitValidationError("The saved split file is invalid.") from exc

        if existing != artifact:
            raise SplitValidationError(
                "The saved split differs from this configuration or library version. "
                "Create a new task to use different settings."
            )

        return existing.summary

    temporary = directory / f".{task.id}.{uuid4().hex}.tmp"

    try:
        temporary.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    return summary
