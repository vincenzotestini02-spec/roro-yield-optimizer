import io

import pytest
from openpyxl import Workbook

from server.importer import read_bookings, template_xlsx

HEADERS = ["booking_id", "customer", "unit_type", "length_m", "weight_t", "discharge_port"]


def workbook(rows, headers=HEADERS) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Bookings"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


GOOD = ["B1", "Nordfreight", "semi_trailer", 13.6, 22, "Immingham"]


def test_template_round_trip():
    bookings, errors, _ = read_bookings(template_xlsx())
    assert errors == [] and len(bookings) == 3


def test_all_errors_are_reported_together():
    data = workbook([GOOD, ["B2", "X", "spaceship", 13.6, 22, "Imm"], ["B3", "X", "van", -1, 3, "Imm"],
                     ["B4", "X", "van", 6.5, "heavy", "Imm"]])
    bookings, errors, _ = read_bookings(data)
    assert bookings == [] and {e.row for e in errors} == {3, 4, 5}


def test_headers_ignore_case_and_spaces():
    bookings, errors, _ = read_bookings(workbook([GOOD], headers=[" Booking_ID ", "Customer", "UNIT_TYPE",
                                                                    "length_m", "weight_t", "Discharge_Port"]))
    assert errors == [] and bookings[0].booking_id == "B1"


def test_blank_rows_at_the_end_are_ignored():
    bookings, errors, _ = read_bookings(workbook([GOOD, [None] * 6, [None] * 6]))
    assert errors == [] and len(bookings) == 1


def test_numbers_written_as_text_with_comma():
    bookings, errors, _ = read_bookings(workbook([["B1", "X", "semi_trailer", "13,6", "22,5", "Imm"]]))
    assert errors == [] and bookings[0].length_m == pytest.approx(13.6) and bookings[0].weight_t == pytest.approx(22.5)


def test_duplicate_booking_id_is_an_error():
    _, errors, _ = read_bookings(workbook([GOOD, GOOD]))
    assert any(e.row == 3 and e.column == "booking_id" for e in errors)


def test_unknown_unit_type_lists_the_allowed_ones():
    _, errors, _ = read_bookings(workbook([["B1", "X", "spaceship", 13.6, 22, "Imm"]]))
    assert "semi_trailer" in errors[0].message


def test_unit_labels_are_accepted():
    bookings, errors, _ = read_bookings(workbook([["B1", "X", "semi-trailer", 13.6, 22, "Imm"]]))
    assert errors == [] and bookings[0].unit_type == "semi_trailer"


def test_missing_required_column_is_one_clear_error():
    _, errors, _ = read_bookings(workbook([["B1", "X", "van", 6.5, 3]], headers=HEADERS[:5]))
    assert len(errors) == 1 and errors[0].row == 1 and "discharge_port" in errors[0].message


def test_several_discharge_ports_give_a_warning():
    other = ["B2", "X", "van", 6.5, 3, "Rotterdam"]
    bookings, errors, warnings = read_bookings(workbook([GOOD, other]))
    assert errors == [] and len(bookings) == 2 and any("discharge ports" in w for w in warnings)


def test_optional_columns_are_read():
    headers = HEADERS + ["segment", "is_reefer", "rate_per_m", "on_board"]
    bookings, errors, _ = read_bookings(workbook([GOOD + ["spot", "yes", 95, "TRUE"]], headers=headers))
    b = bookings[0]
    assert errors == [] and (b.segment, b.is_reefer, b.rate_per_m, b.on_board) == ("spot", True, 95.0, True)


def test_prices_are_optional():
    bookings, _, _ = read_bookings(workbook([GOOD]))
    assert bookings[0].rate_per_m is None and bookings[0].segment == "contract"


def test_not_an_xlsx_file_is_rejected():
    _, errors, _ = read_bookings(b"booking_id,customer\nB1,X\n")
    assert len(errors) == 1 and errors[0].row == 0 and ".xlsx" in errors[0].message


def test_file_over_500_rows_is_rejected():
    rows = [[f"B{i}", "X", "van", 6.5, 3, "Imm"] for i in range(501)]
    _, errors, _ = read_bookings(workbook(rows))
    assert len(errors) == 1 and errors[0].row == 0 and "500" in errors[0].message


def test_import_endpoint_and_template_endpoint(client):
    template = client.get("/api/planner/template.xlsx")
    assert template.status_code == 200 and template.content[:2] == b"PK"
    r = client.post("/api/planner/import", files={"file": ("bookings.xlsx", template.content)})
    body = r.json()
    assert r.status_code == 200 and len(body["bookings"]) == 3 and body["errors"] == []


def test_import_endpoint_refuses_files_over_5_mb(client):
    r = client.post("/api/planner/import", files={"file": ("big.xlsx", b"0" * (5 * 1024 * 1024 + 1))})
    assert r.status_code == 200 and r.json()["errors"][0]["row"] == 0 and "5 MB" in r.json()["errors"][0]["message"]
