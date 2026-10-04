from pathlib import Path
import shutil

import pytest

from app.modules.planning.reference_data import load_planning_reference_data


DEMO_DATA = Path(__file__).parents[1] / "demo-data"


def test_demo_task2b_bundle_has_operating_day_and_all_reference_inputs():
    data = load_planning_reference_data(DEMO_DATA, "PEAK-DAY-01")
    assert data.planning_date.isoformat() == "2026-03-16"
    assert data.is_operating_day is True
    assert len(data.orders) == 7
    assert len(data.vehicles) == 4
    assert data.availability["DEMO-VEH004"] is False
    assert data.travel["Gampaha"]["trip_route_km"] == 36


def test_planning_reference_bundle_does_not_silently_mix_missing_files(tmp_path):
    for path in DEMO_DATA.glob("*.csv"):
        shutil.copy(path, tmp_path / path.name)
    (tmp_path / "calendar.csv").unlink()
    with pytest.raises(ValueError, match="calendar.csv"):
        load_planning_reference_data(tmp_path, "PEAK-DAY-01")


def test_scenario_rejects_duplicate_order_references(tmp_path):
    for path in DEMO_DATA.glob("*.csv"):
        shutil.copy(path, tmp_path / path.name)
    scenario_path = tmp_path / "task2b_peak_day_scenarios.csv"
    lines = scenario_path.read_text(encoding="utf-8").splitlines()
    scenario_path.write_text("\n".join([*lines, lines[1]]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate order_ref"):
        load_planning_reference_data(tmp_path, "PEAK-DAY-01")


def test_scenario_rejects_unknown_fleet_status(tmp_path):
    for path in DEMO_DATA.glob("*.csv"):
        shutil.copy(path, tmp_path / path.name)
    fleet_path = tmp_path / "task2b_peak_day_fleet.csv"
    fleet_path.write_text(fleet_path.read_text(encoding="utf-8").replace("available", "maybe", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        load_planning_reference_data(tmp_path, "PEAK-DAY-01")
