import csv
from hashlib import sha256
from io import StringIO
from math import isfinite
from typing import Literal

import pandas as pd

from customer_intelligence.core.config import Settings
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.schemas.profile import (
    ColumnProfile,
    DatasetProfileResponse,
    NumericSummary,
)
from customer_intelligence.services.datasets import (
    MAX_UPLOAD_BYTES,
    DatasetUploadError,
    validate_csv,
)


class DatasetProfileError(ValueError):
    pass


class DatasetChangedError(DatasetProfileError):
    pass


def finite_number(value: float) -> float | None:
    return value if isfinite(value) else None


def build_profile(
    frame: pd.DataFrame,
    dataset: Dataset,
) -> DatasetProfileResponse:
    frame = frame.replace(r"^\s*$", pd.NA, regex=True)
    row_count, column_count = frame.shape

    columns: list[ColumnProfile] = []
    warnings: list[str] = []

    for name in frame.columns:
        values = frame[name]
        missing_count = int(values.isna().sum())
        non_missing = values.dropna()
        unique_count = int(non_missing.nunique())
        numeric_summary = None
        inferred_type: Literal["numeric", "string", "empty"] = "string"

        if non_missing.empty:
            inferred_type = "empty"
            warnings.append(f"{name}: every value is missing.")
        else:
            numeric_values = pd.to_numeric(non_missing, errors="coerce")

            if bool(numeric_values.notna().all()) and all(
                isfinite(float(value)) for value in numeric_values
            ):
                inferred_type = "numeric"
                numeric_summary = NumericSummary(
                    minimum=finite_number(float(numeric_values.min())),
                    maximum=finite_number(float(numeric_values.max())),
                    mean=finite_number(float(numeric_values.mean())),
                    median=finite_number(float(numeric_values.median())),
                )

            if unique_count == 1:
                warnings.append(f"{name}: only one distinct non-missing value.")

            if row_count > 1 and unique_count == row_count:
                warnings.append(
                    f"{name}: every row has a distinct value; check whether "
                    "this is an identifier before training."
                )

        columns.append(
            ColumnProfile(
                name=str(name),
                inferred_type=inferred_type,
                missing_count=missing_count,
                missing_percentage=round(missing_count / row_count * 100, 2),
                unique_count=unique_count,
                numeric_summary=numeric_summary,
            )
        )

    preview: list[dict[str, str | None]] = []

    for _, row in frame.head(5).iterrows():
        preview.append(
            {
                str(name): None if pd.isna(value) else str(value)
                for name, value in row.items()
            }
        )

    return DatasetProfileResponse(
        dataset_id=dataset.id,
        original_filename=dataset.original_filename,
        row_count=row_count,
        column_count=column_count,
        duplicate_row_count=int(frame.duplicated().sum()),
        columns=columns,
        preview=preview,
        warnings=warnings,
    )


def load_dataset_frame(
    dataset: Dataset,
    settings: Settings,
    *,
    expected_sha256: str | None = None,
) -> pd.DataFrame:
    if dataset.storage_key != f"{dataset.id}.csv":
        raise DatasetProfileError("The stored dataset reference is invalid.")

    path = settings.data_directory / "uploads" / dataset.storage_key

    try:
        with path.open("rb") as source:
            content = source.read(MAX_UPLOAD_BYTES + 1)

        if len(content) > MAX_UPLOAD_BYTES:
            raise DatasetProfileError("The stored dataset exceeds the size limit.")
        

        if expected_sha256 is not None and sha256(content).hexdigest() != expected_sha256:
            raise DatasetChangedError(
                "The CSV changed after task creation. Upload it again and create a new task."
            )

        dimensions = validate_csv(content)

        if dimensions != (dataset.row_count, dataset.column_count):
            raise DatasetProfileError("The stored CSV dimensions have changed.")

        reader = csv.reader(
            StringIO(content.decode("utf-8-sig"), newline=""),
            strict=True,
        )
        headers = next(reader)
        rows = [row for row in reader if row]
        frame = pd.DataFrame(rows, columns=headers, dtype="string")

    except (OSError, DatasetUploadError, csv.Error) as exc:
        raise DatasetProfileError(
            "The stored CSV could not be read or validated."
        ) from exc

    return frame.replace(r"^\s*$", pd.NA, regex=True)


def profile_dataset(
    dataset: Dataset,
    settings: Settings,
) -> DatasetProfileResponse:
    frame = load_dataset_frame(dataset, settings)
    return build_profile(frame, dataset)