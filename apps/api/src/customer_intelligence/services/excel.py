import csv
from datetime import date, datetime
from io import BytesIO, StringIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from openpyxl import load_workbook
from openpyxl.xml import DEFUSEDXML

from customer_intelligence.services.datasets import (
    MAX_COLUMNS,
    MAX_ROWS,
    DatasetLimitError,
    DatasetUploadError,
)


def excel_to_csv(content: bytes, sheet_name: str | None) -> bytes:
    if not DEFUSEDXML:
        raise DatasetUploadError(
            "Excel XML protection is unavailable; install backend dependencies."
        )
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(item.file_size for item in entries) > 50_000_000:
                raise DatasetLimitError("The expanded workbook exceeds the import budget.")
            if any("vbaproject" in item.filename.lower() for item in entries):
                raise DatasetUploadError("Macro-enabled workbooks are not supported.")
        workbook = load_workbook(
            BytesIO(content), read_only=True, data_only=False, keep_links=False
        )
    except (BadZipFile, ValueError, OSError, KeyError, ParseError, DefusedXmlException) as exc:
        raise DatasetUploadError("The workbook is invalid.") from exc
    try:
        if sheet_name is None:
            if len(workbook.sheetnames) != 1:
                raise DatasetUploadError(
                    "Choose sheet_name for a multi-sheet workbook: "
                    + ", ".join(workbook.sheetnames[:20])
                )
            sheet_name = workbook.sheetnames[0]
        if sheet_name not in workbook.sheetnames:
            raise DatasetUploadError("The requested workbook sheet does not exist.")
        output = StringIO(newline="")
        writer = csv.writer(output)
        sheet = workbook[sheet_name]
        if sheet.max_row and sheet.max_row > MAX_ROWS + 1:
            raise DatasetLimitError("The workbook has too many rows.")
        if sheet.max_column and sheet.max_column > MAX_COLUMNS:
            raise DatasetLimitError("The workbook has too many columns.")
        width = None
        count = 0
        for cells in sheet.iter_rows():
            values = []
            for cell in cells:
                if cell.data_type == "f":
                    raise DatasetUploadError(
                        "Formula cells are unsupported. Export their values before uploading."
                    )
                value = cell.value
                if isinstance(value, (date, datetime)):
                    value = value.isoformat()
                values.append("" if value is None else str(value))
            if not any(v.strip() for v in values):
                continue
            if width is None:
                while values and not values[-1]:
                    values.pop()
                width = len(values)
            if any(v.strip() for v in values[width:]):
                raise DatasetUploadError("Workbook data extends beyond its header columns.")
            writer.writerow(values[:width])
            count += 1
            if count > MAX_ROWS + 1 or output.tell() > 10_000_000:
                raise DatasetLimitError("The converted workbook exceeds the CSV import budget.")
        return output.getvalue().encode("utf-8")
    except (ParseError, DefusedXmlException, BadZipFile) as exc:
        raise DatasetUploadError("The workbook contains invalid XML.") from exc
    finally:
        workbook.close()
