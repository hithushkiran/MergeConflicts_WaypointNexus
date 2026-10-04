"""Load and validate the local Task 2B planning reference CSV bundle."""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


PLANNING_FILES = (
    "task2b_peak_day_scenarios.csv",
    "task2b_peak_day_fleet.csv",
    "calendar.csv",
    "district_travel.csv",
    "service_allowance.csv",
    "vehicles.csv",
)


@dataclass(frozen=True)
class PlanningReferenceData:
    scenario: str
    planning_date: date
    is_operating_day: bool
    orders: tuple[dict[str, Any], ...]
    vehicles: tuple[dict[str, Any], ...]
    availability: dict[str, bool]
    travel: dict[str, dict[str, float]]
    service_allowance: dict[tuple[str, str], int]


def load_planning_references_for_date(root: Path, planning_date: date) -> tuple[PlanningReferenceData, ...]:
    """Load every declared scenario for a planning date in stable order."""
    scenario_rows = _read_csv(root, "task2b_peak_day_scenarios.csv", {
        "scenario", "requested_delivery_date",
    })
    scenario_names = sorted({row["scenario"] for row in scenario_rows
                             if row["requested_delivery_date"] == planning_date.isoformat()})
    return tuple(load_planning_reference_data(root, name) for name in scenario_names)


def _read_csv(root: Path, name: str, required: set[str]) -> list[dict[str, str]]:
    path = root / name
    if not path.is_file():
        raise ValueError(f"planning reference file is missing: {name}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required <= set(reader.fieldnames):
            missing = sorted(required - set(reader.fieldnames or []))
            raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")
        return list(reader)


def load_planning_reference_data(root: Path, scenario: str) -> PlanningReferenceData:
    """Load one scenario and its entire master-data context without mixing bundles."""
    scenarios = _read_csv(root, "task2b_peak_day_scenarios.csv", {
        "scenario", "order_ref", "outlet_id", "requested_delivery_date", "depot", "brand",
        "district", "temp_requirement", "parking_constraint", "order_weight_kg",
        "order_volume_m3", "units", "dock_type", "window_open_time", "window_close_time",
        "prior_day_deferral",
    })
    fleet = _read_csv(root, "task2b_peak_day_fleet.csv", {"scenario", "vehicle_id", "status"})
    calendar = _read_csv(root, "calendar.csv", {"date", "is_operating"})
    vehicles = _read_csv(root, "vehicles.csv", {
        "vehicle_id", "type", "temp", "weight_cap_kg", "volume_cap_m3", "fuel_type",
        "km_per_l", "weekly_fuel_quota_l", "weekly_fuel_used_l", "depot",
    })
    travel_rows = _read_csv(root, "district_travel.csv", {
        "district", "depot_to_district_freeflow_min", "inter_stop_freeflow_min", "trip_route_km",
    })
    allowance_rows = _read_csv(root, "service_allowance.csv", {
        "brand", "dock_type", "service_allowance_min",
    })

    selected = [row for row in scenarios if row["scenario"] == scenario]
    if not selected:
        raise ValueError(f"planning scenario does not exist: {scenario}")
    refs = [row["order_ref"] for row in selected]
    if len(refs) != len(set(refs)):
        raise ValueError(f"scenario {scenario} has duplicate order_ref values")
    planning_dates = {date.fromisoformat(row["requested_delivery_date"]) for row in selected}
    if len(planning_dates) != 1:
        raise ValueError(f"scenario {scenario} spans multiple planning dates")
    planning_date = next(iter(planning_dates))
    operating_values = [row["is_operating"] for row in calendar if row["date"] == planning_date.isoformat()]
    if len(operating_values) != 1 or operating_values[0] not in {"0", "1"}:
        raise ValueError(f"calendar.csv must contain one 0/1 operating flag for {planning_date}")

    vehicle_map = {row["vehicle_id"]: row for row in vehicles}
    if len(vehicle_map) != len(vehicles):
        raise ValueError("vehicles.csv contains duplicate vehicle_id values")
    selected_fleet = [row for row in fleet if row["scenario"] == scenario]
    if len({row["vehicle_id"] for row in selected_fleet}) != len(selected_fleet):
        raise ValueError(f"scenario {scenario} has duplicate fleet availability rows")
    if any(row["vehicle_id"] not in vehicle_map for row in selected_fleet):
        raise ValueError(f"scenario {scenario} refers to a vehicle missing from vehicles.csv")
    statuses = {row["status"].strip().lower() for row in selected_fleet}
    if statuses - {"available", "workshop"}:
        raise ValueError(f"scenario {scenario} has invalid fleet status values: {sorted(statuses - {'available', 'workshop'})}")
    availability = {row["vehicle_id"]: row["status"].strip().lower() == "available"
                    for row in selected_fleet}

    parsed_orders: list[dict[str, Any]] = []
    for row in selected:
        try:
            parsed_orders.append({
                **row,
                "weight_kg": float(row["order_weight_kg"]),
                "volume_m3": float(row["order_volume_m3"]),
                "units": int(row["units"]),
                "prior_day_deferral": row["prior_day_deferral"] == "1",
            })
        except ValueError as exc:
            raise ValueError(f"scenario {scenario} has invalid numeric order data") from exc

    parsed_vehicles: list[dict[str, Any]] = []
    for row in vehicles:
        try:
            parsed_vehicles.append({
                **row,
                "weight_cap_kg": float(row["weight_cap_kg"]),
                "volume_cap_m3": float(row["volume_cap_m3"]),
                "km_per_l": float(row["km_per_l"]),
                "weekly_fuel_quota_l": float(row["weekly_fuel_quota_l"]),
                "weekly_fuel_used_l": float(row["weekly_fuel_used_l"]),
                "depot_code": row["depot"],
                "temperature_capability": row["temp"],
            })
        except ValueError as exc:
            raise ValueError("vehicles.csv has invalid numeric vehicle data") from exc

    travel: dict[str, dict[str, float]] = {}
    for row in travel_rows:
        try:
            travel[row["district"]] = {
                "depot_to_district_freeflow_min": float(row["depot_to_district_freeflow_min"]),
                "inter_stop_freeflow_min": float(row["inter_stop_freeflow_min"]),
                "trip_route_km": float(row["trip_route_km"]),
            }
        except ValueError as exc:
            raise ValueError(f"district_travel.csv has invalid values for {row['district']}") from exc
    if len(travel) != len(travel_rows):
        raise ValueError("district_travel.csv contains duplicate districts")

    allowance: dict[tuple[str, str], int] = {}
    for row in allowance_rows:
        try:
            key = (row["brand"], row["dock_type"])
            if key in allowance:
                raise ValueError("duplicate allowance key")
            allowance[key] = int(row["service_allowance_min"])
        except ValueError as exc:
            raise ValueError("service_allowance.csv has duplicate keys or invalid minutes") from exc

    unknown_districts = sorted({row["district"] for row in parsed_orders} - set(travel))
    unknown_allowances = sorted({(row["brand"], row["dock_type"]) for row in parsed_orders} - set(allowance))
    if unknown_districts or unknown_allowances:
        raise ValueError(f"planning references incomplete: districts={unknown_districts}, allowances={unknown_allowances}")

    return PlanningReferenceData(
        scenario=scenario,
        planning_date=planning_date,
        is_operating_day=operating_values[0] == "1",
        orders=tuple(sorted(parsed_orders, key=lambda row: row["order_ref"])),
        vehicles=tuple(sorted(parsed_vehicles, key=lambda row: row["vehicle_id"])),
        availability=availability,
        travel=travel,
        service_allowance=allowance,
    )
