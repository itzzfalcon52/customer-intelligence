import csv
from io import StringIO
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.models.dataset import Dataset

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 250



class DatasetUploadError(ValueError):
    pass


class DatasetLimitError(DatasetUploadError):
    pass


def validate_csv(content: bytes) -> tuple[int, int]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetUploadError(
            "The CSV must use UTF-8 encoding."
        ) from exc

    if not text.strip():
        raise DatasetUploadError("The CSV is empty.")

    if "\x00" in text:
        raise DatasetUploadError("The CSV contains unsupported null characters.")

    reader = csv.reader(StringIO(text, newline=""), strict=True)

    try:
        headers = next(reader, None)

        if not headers:
            raise DatasetUploadError("The CSV must start with a header row.")

        if any(not header.strip() for header in headers):
            raise DatasetUploadError("Every column must have a name.")

        normalized_headers = [header.strip() for header in headers]

        if len(set(normalized_headers)) != len(normalized_headers):
            raise DatasetUploadError("Column names must be unique.")

        column_count = len(headers)

        if column_count > MAX_COLUMNS:
            raise DatasetLimitError(
                f"The CSV can contain at most {MAX_COLUMNS} columns."
            )

        row_count = 0

        for row in reader:
            if not row:
                continue

            if len(row) != column_count:
                raise DatasetUploadError(
                    f"CSV record ending at line {reader.line_num} has "
                    f"{len(row)} values; expected {column_count}."
                )

            row_count += 1

            if row_count > MAX_ROWS:
                raise DatasetLimitError(
                    f"The CSV can contain at most {MAX_ROWS:,} data rows."
                )

    except csv.Error as exc:
        raise DatasetUploadError(
            "The CSV is malformed or contains an excessively large field."
        ) from exc

    if row_count == 0:
        raise DatasetUploadError("The CSV must contain at least one data row.")

    return row_count, column_count


def save_dataset(
    *,
    source: BinaryIO,
    filename: str | None,
    settings: Settings,
    session: Session,
) -> Dataset:
    original_filename = Path((filename or "").replace("\\", "/")).name

    if not original_filename or Path(original_filename).suffix.lower() != ".csv":
        raise DatasetUploadError("Upload a file with a .csv extension.")

    if len(original_filename) > 255:
        raise DatasetUploadError("The filename must be at most 255 characters.")

    content = source.read(MAX_UPLOAD_BYTES + 1)

    if len(content) > MAX_UPLOAD_BYTES:
        raise DatasetLimitError("The CSV must be 10 MiB or smaller.")

    row_count, column_count = validate_csv(content)

    dataset_id = uuid4()
    storage_key = f"{dataset_id}.csv"

    dataset = Dataset(
        id=dataset_id,
        original_filename=original_filename,
        storage_key=storage_key,
        row_count=row_count,
        column_count=column_count,
    )

    destination = settings.data_directory / "uploads" / storage_key
    file_created = False

    try:
        with destination.open("xb") as output:
            file_created = True
            output.write(content)

        session.add(dataset)
        session.commit()

    except Exception:
        session.rollback()

        if file_created:
            destination.unlink(missing_ok=True)

        raise

    return dataset