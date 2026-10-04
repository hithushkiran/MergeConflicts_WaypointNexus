"""Stable planning input snapshots and persistence helpers."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence import Depot, Order, Outlet, PlanningRun, Vehicle
from app.modules.planning.reference_data import load_planning_references_for_date


@dataclass(frozen=True)
class PlanningSnapshot:
    planning_date: date
    digest: str
    payload: dict[str, Any]


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def create_snapshot(
    planning_date: date,
    orders: list[dict[str, Any]],
    outlets: list[dict[str, Any]],
    vehicles: list[dict[str, Any]],
    depots: list[dict[str, Any]],
    planning_context: list[dict[str, Any]] | None = None,
) -> PlanningSnapshot:
    """Create a versioned, order-independent digest of planning inputs."""
    payload = {
        "schema_version": 1,
        "planning_date": planning_date.isoformat(),
        "orders": sorted(orders, key=lambda row: (row["reference"], row["id"])),
        "outlets": sorted(outlets, key=lambda row: row["outlet_id"]),
        "vehicles": sorted(vehicles, key=lambda row: row["vehicle_id"]),
        "depots": sorted(depots, key=lambda row: row["code"]),
        "planning_context": planning_context or [],
        "unavailable_inputs": [] if planning_context else [
            {"input": "vehicle_availability", "reason": "NO_AVAILABILITY_SCHEDULE"},
            {"input": "operating_calendar", "reason": "NO_OPERATING_DAY_FLAG"},
            {"input": "weekly_fuel_used", "reason": "NO_WEEKLY_FUEL_USAGE"},
            {"input": "travel_service_data", "reason": "NO_DISTANCE_OR_SERVICE_TIME_DATA"},
        ],
    }
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return PlanningSnapshot(planning_date=planning_date, digest=digest, payload=payload)


def build_planning_snapshot(db: Session, planning_date: date) -> PlanningSnapshot:
    """Read confirmed orders for a date and the master data they depend on."""
    order_rows = db.execute(
        select(Order, Outlet)
        .join(Outlet, Outlet.outlet_id == Order.outlet_id)
        .where(Order.requested_delivery_date == planning_date, Order.status == "CONFIRMED")
        .order_by(Order.reference, Order.id)
    ).all()
    orders = [
        {
            "id": str(order.id),
            "reference": order.reference,
            "outlet_id": order.outlet_id,
            "requested_delivery_date": order.requested_delivery_date.isoformat(),
            "status": order.status,
            "temperature_requirement": order.temperature_requirement,
            "units": order.units,
            "weight_kg": order.weight_kg,
            "volume_m3": order.volume_m3,
        }
        for order, _outlet in order_rows
    ]
    outlet_ids = sorted({order.outlet_id for order, _outlet in order_rows})
    outlet_rows = db.scalars(select(Outlet).where(Outlet.outlet_id.in_(outlet_ids))).all() if outlet_ids else []
    outlets = [
        {
            "outlet_id": outlet.outlet_id,
            "brand": outlet.brand,
            "district": outlet.district,
            "depot_code": outlet.depot_code,
            "dock_type": outlet.dock_type,
            "parking_constraint": outlet.parking_constraint,
            "mall_window": outlet.mall_window,
            "window_open_time": outlet.window_open_time,
            "window_close_time": outlet.window_close_time,
        }
        for outlet in outlet_rows
    ]
    vehicles = [
        {
            "vehicle_id": vehicle.vehicle_id,
            "type": vehicle.type,
            "temperature_capability": vehicle.temp,
            "depot_code": vehicle.depot_code,
            "weight_cap_kg": vehicle.weight_cap_kg,
            "volume_cap_m3": vehicle.volume_cap_m3,
            "fuel_type": vehicle.fuel_type,
            "km_per_l": vehicle.km_per_l,
            "weekly_fuel_quota_l": vehicle.weekly_fuel_quota_l,
        }
        for vehicle in db.scalars(select(Vehicle).order_by(Vehicle.vehicle_id)).all()
    ]
    depots = [
        {"code": depot.code, "name": depot.name}
        for depot in db.scalars(select(Depot).order_by(Depot.code)).all()
    ]
    local_dir = Path(os.getenv("PLANNING_DATA_DIR", "/app/local-data"))
    demo_dir = Path(__file__).parents[3] / "demo-data"
    required = {
        "task2b_peak_day_scenarios.csv", "task2b_peak_day_fleet.csv", "calendar.csv",
        "district_travel.csv", "service_allowance.csv", "vehicles.csv",
    }
    present = {name for name in required if (local_dir / name).is_file()}
    has_local_master_data = any((local_dir / name).is_file() for name in ("outlets.csv", "vehicles.csv"))
    if present and present != required:
        raise ValueError(f"planning reference bundle is incomplete in {local_dir}: missing {sorted(required - present)}")
    if present:
        reference_dir = local_dir
    elif has_local_master_data:
        # An official master-data pair must never be combined with demo planning inputs.
        reference_dir = None
    elif os.getenv("APP_ENV", "development").lower() == "development":
        reference_dir = demo_dir
    else:
        reference_dir = None
    context: list[dict[str, Any]] = []
    if reference_dir is not None:
        references = load_planning_references_for_date(reference_dir, planning_date)
        context = [{
            "scenario": ref.scenario,
            "planning_date": ref.planning_date.isoformat(),
            "is_operating_day": ref.is_operating_day,
            "orders": list(ref.orders),
            "vehicle_availability": ref.availability,
            "vehicles": list(ref.vehicles),
            "travel": ref.travel,
            "service_allowance": [
                {"brand": brand, "dock_type": dock, "minutes": minutes}
                for (brand, dock), minutes in sorted(ref.service_allowance.items())
            ],
        } for ref in references]
    return create_snapshot(planning_date, orders, outlets, vehicles, depots, context)


def persist_planning_snapshot(db: Session, snapshot: PlanningSnapshot) -> PlanningRun:
    """Persist a snapshot once; repeating identical inputs returns its run."""
    existing = db.scalar(
        select(PlanningRun).where(
            PlanningRun.planning_date == snapshot.planning_date,
            PlanningRun.snapshot_hash == snapshot.digest,
        )
    )
    if existing is not None:
        return existing

    run = PlanningRun(
        planning_date=snapshot.planning_date,
        snapshot_hash=snapshot.digest,
        status="SNAPSHOT",
        runtime_metadata=snapshot.payload,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
