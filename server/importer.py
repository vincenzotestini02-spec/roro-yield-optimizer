"""The planner's Excel file: a template to fill in and a reader that checks every row.

The file is read in memory and never stored. Formulas are not evaluated and macros never run:
openpyxl reads the cached cell values only.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field

from roro_yield.models import UNIT_LABELS, UNIT_TYPES

router = APIRouter(prefix="/api/planner")

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 500
MAX_SCAN_ROWS = 5000  # rows read at most, blank ones included
MAX_COLUMNS = 40
REQUIRED = ("booking_id", "customer", "unit_type", "length_m", "weight_t", "discharge_port")
OPTIONAL = ("segment", "is_reefer", "rate_per_m", "reefer_fee", "height_m", "axle_count", "on_board")
SEVERAL_PORTS = "Several discharge ports arrive in a later version: the plan treats them as one."
TRUE_WORDS = {"true", "yes", "y", "1", "x"}
FALSE_WORDS = {"false", "no", "n", "0", ""}


class PlannerBooking(BaseModel):
    booking_id: str = Field(min_length=1, max_length=32)
    customer: str = Field(min_length=1, max_length=80)
    unit_type: str
    length_m: float = Field(ge=1, le=25)
    weight_t: float = Field(ge=0.1, le=80)
    discharge_port: str = Field(min_length=1, max_length=40)
    segment: Literal["contract", "spot"] = "contract"
    is_reefer: bool = False
    rate_per_m: float | None = Field(default=None, ge=0, le=10_000)
    reefer_fee: float | None = Field(default=None, ge=0, le=10_000)
    height_m: float | None = Field(default=None, ge=0.5, le=6)
    axle_count: int | None = Field(default=None, ge=1, le=12)
    on_board: bool = False


@dataclass(frozen=True)
class RowError:
    row: int
    column: str
    message: str


def _unit_type(value: str) -> str | None:
    text = value.strip().lower()
    if text in UNIT_TYPES:
        return text
    by_label = {label.lower(): key for key, label in UNIT_LABELS.items()}
    return by_label.get(text)


def _number(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return float(str(value).strip().replace(",", "."))


def _flag(value) -> bool:
    if isinstance(value, bool):
        return value
    text = "" if value is None else str(value).strip().lower()
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    raise ValueError(f"'{value}' is not yes or no")


def template_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Bookings"
    ws.append(list(REQUIRED + OPTIONAL))
    ws.append(["B001", "Nordfreight", "semi_trailer", 13.6, 22, "Immingham", "contract", "no", 52, None, 4.0, 5, "no"])
    ws.append(["B002", "Spot haulier", "accompanied_truck", 16.5, 30, "Immingham", "spot", "yes", 95, 150, 4.0, 5, "no"])
    ws.append(["B003", "Baltic Logistics", "van", 6.5, 2.8, "Immingham", "contract", "no", None, None, None, None, "no"])
    notes = wb.create_sheet("Read me")
    notes.append(["Column", "Required", "Rule"])
    for column in REQUIRED:
        notes.append([column, "yes", ""])
    for column in OPTIONAL:
        notes.append([column, "no", ""])
    notes.append([])
    notes.append(["unit_type values", ", ".join(UNIT_TYPES)])
    notes.append(["length_m", "1 to 25 m"])
    notes.append(["weight_t", "0.1 to 80 t"])
    notes.append(["segment", "contract or spot; contract when empty"])
    notes.append(["is_reefer, on_board", "yes or no"])
    notes.append(["rate_per_m", "optional: without it revenue shows as n/a"])
    notes.append(["Rows", f"at most {MAX_ROWS}; every booking in the file is accepted and must be loaded"])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _file_error(message: str) -> tuple[list[PlannerBooking], list[RowError], list[str]]:
    return [], [RowError(0, "file", message)], []


def read_bookings(data: bytes) -> tuple[list[PlannerBooking], list[RowError], list[str]]:
    if len(data) > MAX_BYTES:
        return _file_error("The file is larger than 5 MB.")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        return _file_error("This is not an .xlsx file. Save the sheet as Excel workbook (.xlsx) and try again.")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        return _file_error("The .xlsx file cannot be read. Save it again from Excel and retry.")
    ws = wb["Bookings"] if "Bookings" in wb.sheetnames else wb.worksheets[0]
    # The sheet's stated size can be huge for a tiny file; never walk past these bounds.
    if (ws.max_row or 0) > MAX_SCAN_ROWS or (ws.max_column or 0) > MAX_COLUMNS * 25:
        return _file_error(f"The sheet is too large: keep it under {MAX_ROWS} bookings and {MAX_COLUMNS} columns.")
    rows = ws.iter_rows(max_row=MAX_SCAN_ROWS, max_col=MAX_COLUMNS, values_only=True)
    header = next(rows, None)
    if header is None:
        return _file_error("The sheet is empty.")
    names = [str(h).strip().lower() if h is not None else "" for h in header]
    missing = [c for c in REQUIRED if c not in names]
    if missing:
        return [], [RowError(1, ",".join(missing), f"Missing required column(s): {', '.join(missing)}.")], []
    index = {name: i for i, name in enumerate(names) if name in REQUIRED + OPTIONAL}

    body = []
    for number, row in enumerate(rows, start=2):
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        body.append((number, row))
        if len(body) > MAX_ROWS:
            return _file_error(f"The file has more than {MAX_ROWS} bookings.")

    bookings: list[PlannerBooking] = []
    errors: list[RowError] = []
    seen: set[str] = set()
    for number, row in body:
        cell = {name: (row[i] if i < len(row) else None) for name, i in index.items()}
        values: dict = {}
        row_errors: list[RowError] = []

        def fail(column: str, message: str) -> None:
            row_errors.append(RowError(number, column, message))

        for column in REQUIRED:
            if cell[column] is None or str(cell[column]).strip() == "":
                fail(column, "is empty")
        booking_id = str(cell["booking_id"]).strip() if cell["booking_id"] is not None else ""
        if booking_id and booking_id in seen:
            fail("booking_id", f"{booking_id} appears twice")
        values["booking_id"] = booking_id
        values["customer"] = str(cell["customer"] or "").strip()
        values["discharge_port"] = str(cell["discharge_port"] or "").strip()
        if cell["unit_type"] is not None and str(cell["unit_type"]).strip():
            unit = _unit_type(str(cell["unit_type"]))
            if unit is None:
                fail("unit_type", f"'{cell['unit_type']}' is not one of: {', '.join(UNIT_TYPES)}")
            values["unit_type"] = unit or ""
        for column in ("length_m", "weight_t", "rate_per_m", "reefer_fee", "height_m", "axle_count"):
            raw = cell.get(column)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                values[column] = _number(raw)
            except ValueError:
                fail(column, f"'{raw}' is not a number")
        for column in ("is_reefer", "on_board"):
            try:
                values[column] = _flag(cell.get(column))
            except ValueError as exc:
                fail(column, str(exc))
        segment = str(cell.get("segment") or "contract").strip().lower()
        if segment not in ("contract", "spot"):
            fail("segment", f"'{cell.get('segment')}' is not contract or spot")
        values["segment"] = segment
        if "axle_count" in values:
            values["axle_count"] = int(values["axle_count"])

        if not row_errors:
            try:
                bookings.append(PlannerBooking(**values))
            except Exception as exc:  # pydantic range checks
                for item in getattr(exc, "errors", lambda: [])():
                    fail(str(item["loc"][0]), item["msg"])
        errors.extend(row_errors)
        if booking_id:
            seen.add(booking_id)

    if errors:
        return [], errors, []
    warnings = [SEVERAL_PORTS] if len({b.discharge_port for b in bookings}) > 1 else []
    return bookings, [], warnings


@router.get("/template.xlsx")
def download_template() -> Response:
    return Response(template_xlsx(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="roro-bookings-template.xlsx"'})


@router.post("/import")
def import_bookings(file: UploadFile = File(...)) -> dict:
    # A plain def runs in the thread pool, so a slow file never blocks other visitors.
    data = file.file.read(MAX_BYTES + 1)
    bookings, errors, warnings = read_bookings(data)
    return {
        "bookings": [b.model_dump() for b in bookings],
        "errors": [e.__dict__ for e in errors],
        "warnings": warnings,
    }
