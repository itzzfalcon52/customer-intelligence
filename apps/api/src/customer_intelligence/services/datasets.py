import csv
import io
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.models.dataset import Dataset

CHUNK = 1024 * 1024
# A stored file was checked against the limits when it was uploaded. Re-reading it later does not
# apply today's limits again, so lowering a limit never breaks existing datasets and models.
NO_LIMIT = 10**12


class DatasetUploadError(ValueError):
    pass


class DatasetLimitError(DatasetUploadError):
    pass


def validate_csv(
    content: bytes, max_rows: int = NO_LIMIT, max_columns: int = NO_LIMIT
) -> tuple[int, int]:
    return validate_csv_stream(io.BytesIO(content), max_rows, max_columns)


def validate_csv_stream(
    raw: BinaryIO, max_rows: int = NO_LIMIT, max_columns: int = NO_LIMIT
) -> tuple[int, int]:
    """Check a CSV row by row without holding the whole file in memory."""
    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
    try:
        first = text.read(1)
    except UnicodeDecodeError as exc:
        raise DatasetUploadError("The CSV must use UTF-8 encoding.") from exc
    if not first:
        raise DatasetUploadError("The CSV is empty.")
    text.seek(0)

    def lines() -> Iterator[str]:
        try:
            for line in text:
                if "\x00" in line:
                    raise DatasetUploadError("The CSV contains unsupported null characters.")
                yield line
        except UnicodeDecodeError as exc:
            raise DatasetUploadError("The CSV must use UTF-8 encoding.") from exc

    reader = csv.reader(lines(), strict=True)

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

        if column_count > max_columns:
            raise DatasetLimitError(f"The CSV can contain at most {max_columns:,} columns.")

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

            if row_count > max_rows:
                raise DatasetLimitError(f"The CSV can contain at most {max_rows:,} data rows.")

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
    sheet_name: str | None = None,
) -> Dataset:
    original_filename = Path((filename or "").replace("\\", "/")).name

    if not original_filename or Path(original_filename).suffix.lower() not in {".csv", ".xlsx"}:
        raise DatasetUploadError("Upload a .csv or .xlsx file.")

    if len(original_filename) > 255:
        raise DatasetUploadError("The filename must be at most 255 characters.")

    excel = Path(original_filename).suffix.lower() == ".xlsx"
    limit_mb = settings.max_excel_mb if excel else settings.max_upload_mb
    uploads = settings.data_directory / "uploads"
    dataset_id = uuid4()
    storage_key = f"{dataset_id}.csv"
    destination = uploads / storage_key
    partial = uploads / f".{dataset_id}.part"
    try:
        # Stream to disk in chunks, stopping as soon as the size limit is passed.
        written = 0
        with partial.open("xb") as output:
            while chunk := source.read(CHUNK):
                written += len(chunk)
                if written > limit_mb * 1024 * 1024:
                    raise DatasetLimitError(
                        f"{'Excel files' if excel else 'CSV files'} must be "
                        f"{limit_mb} MB or smaller."
                    )
                output.write(chunk)
        if excel:
            from customer_intelligence.services.excel import excel_to_csv

            converted = excel_to_csv(
                partial.read_bytes(),
                sheet_name,
                max_rows=settings.max_rows,
                max_columns=settings.max_columns,
                max_bytes=settings.max_upload_mb * 1024 * 1024,
            )
            partial.write_bytes(converted)
        with partial.open("rb") as stored:
            row_count, column_count = validate_csv_stream(
                stored, settings.max_rows, settings.max_columns
            )
        dataset = Dataset(
            id=dataset_id,
            original_filename=original_filename,
            storage_key=storage_key,
            row_count=row_count,
            column_count=column_count,
        )
        partial.rename(destination)
        session.add(dataset)
        session.commit()
    except Exception:
        session.rollback()
        partial.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise

    return dataset
