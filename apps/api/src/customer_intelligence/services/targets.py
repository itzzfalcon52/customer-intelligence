from customer_intelligence.core.config import Settings
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.schemas.target import TargetCheckRequest, TargetCheckResponse
from customer_intelligence.services.profiling import load_dataset_frame


class TargetCheckError(ValueError):
    pass


def check_target(
    dataset: Dataset,
    request: TargetCheckRequest,
    settings: Settings,
) -> TargetCheckResponse:
    frame = load_dataset_frame(dataset, settings)

    if request.target_column not in frame.columns:
        raise TargetCheckError("The selected target column does not exist.")

    values = frame[request.target_column]
    missing_count = int(values.isna().sum())
    counts = values.value_counts(dropna=True)
    class_count = len(counts)
    blockers: list[str] = []

    if missing_count:
        blockers.append(
            f"The target contains {missing_count} missing labels. "
            "Resolve them before training."
        )

    if class_count != 2:
        blockers.append(
            f"Binary classification requires exactly two classes; "
            f"this column has {class_count}."
        )

    if request.positive_label not in counts.index:
        blockers.append("The selected positive label does not occur in the target.")

    label_mapping: dict[str, int] = {}

    if not blockers:
        for label in counts.index:
            label_mapping[str(label)] = 1 if label == request.positive_label else 0

    return TargetCheckResponse(
        dataset_id=dataset.id,
        target_column=request.target_column,
        positive_label=request.positive_label,
        missing_label_count=missing_count,
        distinct_class_count=class_count,
        class_counts={
            str(label): int(count) for label, count in counts.head(20).items()
        },
        class_counts_truncated=class_count > 20,
        label_mapping=label_mapping,
        target_valid=not blockers,
        blockers=blockers,
    )