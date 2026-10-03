import pytest

from app import seed


def test_rows_rejects_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "DATA_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="missing"):
        seed.rows("outlets.csv", {"outlet_id"})


def test_rows_rejects_missing_columns(tmp_path, monkeypatch):
    (tmp_path / "outlets.csv").write_text("outlet_id\nOUT001\n", encoding="utf-8")
    monkeypatch.setattr(seed, "DATA_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="required columns"):
        seed.rows("outlets.csv", {"outlet_id", "brand"})


def test_rows_rejects_duplicate_identifier(tmp_path, monkeypatch):
    (tmp_path / "outlets.csv").write_text("outlet_id,brand\nOUT001,Fresh\nOUT001,Fresh\n", encoding="utf-8")
    monkeypatch.setattr(seed, "DATA_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="duplicate"):
        seed.rows("outlets.csv", {"outlet_id", "brand"})


def test_rows_parses_valid_csv(tmp_path, monkeypatch):
    (tmp_path / "vehicles.csv").write_text("vehicle_id,type,weight_cap_kg,volume_cap_m3,km_per_l,weekly_fuel_quota_l\nVEH001,truck,1,2,3,4\n", encoding="utf-8")
    monkeypatch.setattr(seed, "DATA_DIR", tmp_path)
    assert seed.rows("vehicles.csv", {"vehicle_id", "type"})[0]["vehicle_id"] == "VEH001"


def test_rows_rejects_invalid_vehicle_numeric_value(tmp_path, monkeypatch):
    (tmp_path / "vehicles.csv").write_text("vehicle_id,weight_cap_kg,volume_cap_m3,km_per_l,weekly_fuel_quota_l\nVEH001,nope,1,2,3\n", encoding="utf-8")
    monkeypatch.setattr(seed, "DATA_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="invalid numeric"):
        seed.rows("vehicles.csv", {"vehicle_id", "weight_cap_kg", "volume_cap_m3", "km_per_l", "weekly_fuel_quota_l"})
