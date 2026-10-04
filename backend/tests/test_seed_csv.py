from types import SimpleNamespace

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


def test_development_prefers_official_data_when_both_files_exist(tmp_path, monkeypatch):
    official = tmp_path / "official"
    demo = tmp_path / "demo"
    official.mkdir()
    demo.mkdir()
    (official / "outlets.csv").touch()
    (official / "vehicles.csv").touch()
    monkeypatch.setattr(seed, "DATA_DIR", official)
    monkeypatch.setattr(seed, "DEMO_DATA_DIR", demo)
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(app_env="development"))

    assert seed.select_dataset() == (official, False)


def test_development_falls_back_to_demo_data_only_when_official_pair_is_absent(tmp_path, monkeypatch):
    official = tmp_path / "official"
    demo = tmp_path / "demo"
    official.mkdir()
    demo.mkdir()
    monkeypatch.setattr(seed, "DATA_DIR", official)
    monkeypatch.setattr(seed, "DEMO_DATA_DIR", demo)
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(app_env="development"))

    assert seed.select_dataset() == (demo, True)


def test_partial_official_data_fails_instead_of_mixing_with_demo(tmp_path, monkeypatch):
    official = tmp_path / "official"
    demo = tmp_path / "demo"
    official.mkdir()
    demo.mkdir()
    (official / "outlets.csv").touch()
    monkeypatch.setattr(seed, "DATA_DIR", official)
    monkeypatch.setattr(seed, "DEMO_DATA_DIR", demo)
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(app_env="development"))

    with pytest.raises(RuntimeError, match="incomplete"):
        seed.select_dataset()


def test_demo_data_is_disabled_outside_development(tmp_path, monkeypatch):
    official = tmp_path / "official"
    demo = tmp_path / "demo"
    official.mkdir()
    demo.mkdir()
    monkeypatch.setattr(seed, "DATA_DIR", official)
    monkeypatch.setattr(seed, "DEMO_DATA_DIR", demo)
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(app_env="production"))

    with pytest.raises(RuntimeError, match="disabled outside development"):
        seed.select_dataset()
