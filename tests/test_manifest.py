import io

import pandas as pd

from roro_yield.manifest import MANIFEST_COLUMNS, manifest_csv, manifest_dataframe
from roro_yield.models import Booking, Lane, Plan, Scenario, Vessel


def scenario():
    bookings = tuple(
        Booking(f"B{i}", i, "spot", f"H{i}", "semi_trailer", 13.6, 20.0, i == 2, 100.0, 150.0, 110.0)
        for i in range(4)
    )
    vessel = Vessel("V", "A → B", (Lane("L1", 30.0), Lane("L2", 30.0)), 1000.0, 5, 0.5)
    return Scenario(vessel, bookings, 0.0, 200.0)


def test_manifest_rows_columns_and_order():
    plan = Plan("x", {"B0": "L2", "B1": "L1", "B2": "L1"}, ["B3"])
    df = manifest_dataframe(scenario(), plan)
    assert list(df.columns) == MANIFEST_COLUMNS == [
        "lane", "position", "booking_id", "customer", "segment", "unit_type", "length_m", "weight_t", "reefer",
    ]
    assert len(df) == 3
    assert list(df["booking_id"]) == ["B1", "B2", "B0"]
    assert list(df["position"]) == [1, 2, 1]
    assert list(df["reefer"]) == [False, True, False]


def test_manifest_csv_round_trips():
    plan = Plan("x", {"B0": "L1"}, [])
    data = manifest_csv(scenario(), plan)
    df = pd.read_csv(io.BytesIO(data))
    assert list(df.columns)[0] == "lane"
    assert df.loc[0, "booking_id"] == "B0"


def test_empty_manifest_has_header():
    df = manifest_dataframe(scenario(), Plan("x", {}, []))
    assert list(df.columns) == MANIFEST_COLUMNS
    assert len(df) == 0
