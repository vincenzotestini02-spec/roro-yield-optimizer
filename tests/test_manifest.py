import io

import pandas as pd

from roro_yield.manifest import MANIFEST_COLUMNS, manifest_csv, manifest_dataframe
from roro_yield.models import Booking, Lane, Plan, Scenario, Slot, Vessel


def scenario():
    bookings = tuple(
        Booking(f"B{i}", i, "spot", f"H{i}", "semi_trailer", 13.6, 20.0, i == 2, 100.0, 150.0, 110.0)
        for i in range(4)
    )
    vessel = Vessel("V", "A → B", (Lane("L1", 30.0), Lane("L2", 30.0)), 1000.0, 5, 0.5)
    return Scenario(vessel, bookings, 0.0, 200.0)


def test_manifest_rows_columns_and_order():
    plan = Plan("x", {"B0": Slot("L2", 1), "B1": Slot("L1", 0), "B2": Slot("L1", 2)}, ["B3"])
    df = manifest_dataframe(scenario(), plan)
    assert list(df.columns) == MANIFEST_COLUMNS == [
        "lane", "zone", "position", "booking_id", "customer", "segment", "unit_type", "length_m", "weight_t", "reefer",
    ]
    assert len(df) == 3
    assert list(df["booking_id"]) == ["B1", "B2", "B0"]
    assert list(df["position"]) == [1, 2, 1]
    assert list(df["reefer"]) == [False, True, False]
    assert list(df["zone"]) == [0, 2, 1]


def test_manifest_csv_round_trips():
    plan = Plan("x", {"B0": Slot("L1", 0)}, [])
    data = manifest_csv(scenario(), plan)
    df = pd.read_csv(io.BytesIO(data))
    assert list(df.columns)[0] == "lane"
    assert df.loc[0, "booking_id"] == "B0"


def test_empty_manifest_has_header():
    df = manifest_dataframe(scenario(), Plan("x", {}, []))
    assert list(df.columns) == MANIFEST_COLUMNS
    assert len(df) == 0


def test_manifest_has_zone_and_ballast_rows():
    b = Booking("B0", 0, "spot", "H", "semi_trailer", 13.6, 60.0, False, 100.0, 150.0, 110.0)
    s = Scenario(Vessel("V", "A → B", (Lane("L1", 120.0, 9.0),), 1000.0, 5, 0.5), (b,), 0.0, 200.0)
    df = manifest_dataframe(s, Plan("x", {"B0": Slot("L1", 0)}, []))
    assert list(df.columns) == MANIFEST_COLUMNS
    assert df.loc[0, "zone"] == 0
    ballast = df[df["lane"] == "BALLAST"]
    assert list(ballast["unit_type"]) == ["port tank"]
    assert ballast["weight_t"].iloc[0] > 0
    assert df.iloc[-1]["lane"] == "BALLAST"


def test_manifest_zone_and_position_are_integers_with_ballast_rows():
    b = Booking("B0", 0, "spot", "H", "semi_trailer", 13.6, 60.0, False, 100.0, 150.0, 110.0)
    s = Scenario(Vessel("V", "A → B", (Lane("L1", 120.0, 9.0),), 1000.0, 5, 0.5), (b,), 0.0, 200.0)
    plan = Plan("x", {"B0": Slot("L1", 0)}, [])
    df = manifest_dataframe(s, plan)
    assert str(df["zone"].dtype) == "Int64" and str(df["position"].dtype) == "Int64"
    text = manifest_csv(s, plan).decode("utf-8").splitlines()
    assert text[1].startswith("L1,0,1,B0")
