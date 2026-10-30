from hashlib import sha256

from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.target import TargetCheckRequest
from customer_intelligence.schemas.task import TaskCreateRequest
from customer_intelligence.services.profiling import (
    DatasetProfileError,
    load_dataset_frame,
)
from customer_intelligence.services.targets import check_target


class TaskValidationError(ValueError):
    pass


def create_task(
    dataset: Dataset,
    request: TaskCreateRequest,
    settings: Settings,
    session: Session,
) -> Task:
    target = check_target(
        dataset,
        TargetCheckRequest(
            target_column=request.target_column,
            positive_label=request.positive_label,
        ),
        settings,
    )

    if not target.target_valid:
        raise TaskValidationError(" ".join(target.blockers))

    frame = load_dataset_frame(dataset, settings)
    features = request.feature_columns

    if len(features) != len(set(features)):
        raise TaskValidationError("Feature columns must be unique.")

    if request.target_column in features:
        raise TaskValidationError("The target cannot also be a model input.")

    if request.id_column is not None:
        if request.id_column == request.target_column:
            raise TaskValidationError("The identifier cannot be the target.")

        if request.id_column not in frame.columns:
            raise TaskValidationError("The selected identifier column does not exist.")

        if request.id_column in features:
            raise TaskValidationError("Exclude the identifier from model inputs.")

        identifiers = frame[request.id_column]

        if bool(identifiers.isna().any()) or bool(identifiers.duplicated().any()):
            raise TaskValidationError(
                "This workflow requires a non-missing, unique identifier per row."
            )

    if request.time_column is not None:
        if request.time_column not in frame.columns:
            raise TaskValidationError("The selected time column does not exist.")
        if request.time_column in features or request.time_column in {
            request.target_column,
            request.id_column,
        }:
            raise TaskValidationError("The time column cannot be the target, ID or an input.")
        import pandas as pd

        if bool(pd.to_datetime(frame[request.time_column], errors="coerce").isna().any()):
            raise TaskValidationError("Every row needs a valid date in the time column.")

    for name in features:
        if name not in frame.columns:
            raise TaskValidationError(f"Feature column '{name}' does not exist.")

        if frame[name].dropna().nunique() <= 1:
            raise TaskValidationError(f"Feature '{name}' is empty or constant. Exclude it.")

    path = settings.data_directory / "uploads" / dataset.storage_key

    try:
        with path.open("rb") as source:
            digest = sha256()
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise DatasetProfileError("The stored CSV could not be read.") from exc

    task = Task(
        dataset_id=dataset.id,
        target_column=request.target_column,
        positive_label=request.positive_label,
        id_column=request.id_column,
        feature_columns=list(features),
        label_mapping=target.label_mapping,
        features_available_at_prediction=request.features_available_at_prediction,
        dataset_sha256=digest.hexdigest(),
        time_column=request.time_column,
        evaluation_strategy="time_ordered" if request.time_column else "stratified_random",
    )

    try:
        session.add(task)
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(task)
    return task
