"""Loader manifest checks and dispatcher shortfall recovery."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.infrastructure.persistence import (
    AuditEvent, Deferral, ManifestCheck, ManifestVersion, Order, PlanVersion, PlanningRun,
    Shortfall, Trip, TripStop, Vehicle,
)
from app.modules.identity.routes import Principal, api_error, require_roles
from app.modules.planning.allocation import allocate_scenario, persist_scenario_allocation
from app.modules.planning.reference_data import PlanningReferenceData


loader = APIRouter(prefix="/api/v1/loader", tags=["loading"])
dispatcher = APIRouter(prefix="/api/v1/dispatcher", tags=["shortfalls"])
driver = APIRouter(prefix="/api/v1/driver", tags=["departure"])


class CheckLine(BaseModel):
    order_id: UUID
    status: Literal["LOADED", "MISSING", "DAMAGED", "SUBSTITUTE"]
    quantity: int = Field(ge=0)
    notes: str | None = Field(default=None, max_length=500)


class CheckRequest(BaseModel):
    manifest_version: int = Field(ge=1)
    lines: list[CheckLine] = Field(min_length=1)


class ResolveRequest(BaseModel):
    action: Literal["PARTIAL_FULFILLMENT", "SUBSTITUTE", "RELOAD_FOUND", "DEFER", "REALLOCATION"]
    reason: str = Field(min_length=1, max_length=500)
    quantity: int | None = Field(default=None, ge=0)
    substitute_reference: str | None = Field(default=None, max_length=120)
    target_trip_id: UUID | None = None


def _reference_data_from_snapshot(run: PlanningRun) -> PlanningReferenceData:
    snapshot = run.runtime_metadata or {}
    contexts = snapshot.get("planning_context") or []
    if len(contexts) != 1:
        raise api_error(422, "REALLOCATION_CONTEXT_UNAVAILABLE", "This plan has no single saved reference snapshot to replan safely.")
    context = contexts[0]
    allowances = {(row["brand"], row["dock_type"]): int(row["minutes"]) for row in context["service_allowance"]}
    return PlanningReferenceData(
        scenario=context["scenario"], planning_date=datetime.fromisoformat(context["planning_date"]).date(),
        is_operating_day=bool(context["is_operating_day"]), orders=tuple(context["orders"]),
        vehicles=tuple(context["vehicles"]), availability=context["vehicle_availability"],
        travel=context["travel"], service_allowance=allowances,
    )


def _depot_trip(db: Session, trip_id: UUID, principal: Principal) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise api_error(404, "TRIP_NOT_FOUND", "The trip was not found.")
    vehicle = db.get(Vehicle, trip.vehicle_id)
    plan = db.get(PlanVersion, trip.plan_version_id)
    if not vehicle or vehicle.depot_code != principal.user.depot_code or not plan or plan.status != "PUBLISHED":
        raise api_error(404, "TRIP_NOT_FOUND", "The published trip is not available in this depot.")
    return trip


def _current_manifest(db: Session, trip: Trip, actor_id: UUID | None = None) -> ManifestVersion:
    version = db.scalar(select(ManifestVersion).where(ManifestVersion.trip_id == trip.id).order_by(ManifestVersion.version_number.desc()))
    if version:
        return version
    version = ManifestVersion(trip_id=trip.id, version_number=1, created_by_id=actor_id, status="CURRENT")
    db.add(version)
    db.flush()
    stops = db.execute(select(TripStop, Order).join(Order, Order.id == TripStop.order_id).where(TripStop.trip_id == trip.id).order_by(TripStop.sequence_number)).all()
    for stop, order in stops:
        db.add(ManifestCheck(trip_id=trip.id, order_id=order.id, expected_quantity=order.units, loaded_quantity=0,
                             status="PENDING", manifest_version_id=version.id, load_sequence=stop.sequence_number))
    db.flush()
    return version


def _manifest_read(db: Session, version: ManifestVersion) -> dict:
    lines = db.execute(select(ManifestCheck, Order, TripStop).join(Order, Order.id == ManifestCheck.order_id)
                       .join(TripStop, (TripStop.trip_id == ManifestCheck.trip_id) & (TripStop.order_id == ManifestCheck.order_id))
                       .where(ManifestCheck.manifest_version_id == version.id).order_by(ManifestCheck.load_sequence)).all()
    return {"id": str(version.id), "version_number": version.version_number, "status": version.status,
            "acknowledged_at": version.acknowledged_at, "lines": [{
                "order_id": str(check.order_id), "order_ref": order.reference, "outlet_id": order.outlet_id,
                "load_sequence": check.load_sequence, "expected_quantity": check.expected_quantity,
                "loaded_quantity": check.loaded_quantity, "status": check.status, "notes": check.notes,
            } for check, order, _ in lines]}


def _create_reallocation_candidate(db: Session, shortfall: Shortfall, target_trip_id: UUID, reason: str, actor_id: UUID) -> PlanVersion:
    source_trip = db.get(Trip, shortfall.trip_id) if shortfall.trip_id else None
    if source_trip is None:
        raise api_error(409, "SHORTFALL_TRIP_MISSING", "The affected trip is unavailable.")
    source_plan = db.get(PlanVersion, source_trip.plan_version_id)
    target_trip = db.get(Trip, target_trip_id)
    if source_plan is None or source_plan.status != "PUBLISHED" or target_trip is None or target_trip.plan_version_id != source_plan.id:
        raise api_error(422, "INVALID_REALLOCATION_TARGET", "Choose a different trip from the currently published plan.")
    if target_trip.id == source_trip.id or target_trip.status != "PLANNED":
        raise api_error(422, "INVALID_REALLOCATION_TARGET", "The target must be another trip that is not on hold.")
    order = db.get(Order, shortfall.order_id)
    outlet_brand_district = db.execute(select(TripStop, Order).join(Order, Order.id == TripStop.order_id)
                                       .where(TripStop.trip_id == target_trip.id).limit(1)).first()
    if order is None or outlet_brand_district is None:
        raise api_error(422, "INVALID_REALLOCATION_TARGET", "The target trip must contain a compatible route group.")
    target_order = outlet_brand_district[1]
    from app.infrastructure.persistence import Outlet
    target_outlet = db.get(Outlet, target_order.outlet_id)
    order_outlet = db.get(Outlet, order.outlet_id)
    if not target_outlet or not order_outlet or (target_outlet.brand, target_outlet.district) != (order_outlet.brand, order_outlet.district):
        raise api_error(422, "REALLOCATION_ROUTE_MISMATCH", "The order and target trip must share the same brand and district.")
    run = db.get(PlanningRun, source_plan.planning_run_id)
    if run is None:
        raise api_error(422, "REALLOCATION_CONTEXT_UNAVAILABLE", "The saved planning snapshot is unavailable.")
    data = _reference_data_from_snapshot(run)
    try:
        allocation = allocate_scenario(data, forced_assignments={order.reference: (target_trip.vehicle_id, target_trip.trip_number)})
        if allocation.status not in {"OPTIMAL", "FEASIBLE"} or any(not trip["metrics"].get("time_windows_valid", False) for trip in allocation.trips):
            raise api_error(422, "REALLOCATION_INFEASIBLE", "The target fails vehicle, capacity, fuel, or time-window checks. No plan was changed.")
        selected = next((row for row in allocation.rows if row["order_ref"] == order.reference), None)
        if selected is None or selected["decision"] != "served" or (selected["vehicle_id"], selected["trip_id"]) != (target_trip.vehicle_id, target_trip.trip_number):
            raise api_error(422, "REALLOCATION_INFEASIBLE", "The target fails planning constraints. No plan was changed.")
        candidate = persist_scenario_allocation(db, run, allocation, revises_plan_version_id=source_plan.id)
    except ValueError as error:
        raise api_error(422, "REALLOCATION_INFEASIBLE", str(error)) from error
    candidate.created_by_id = actor_id
    db.add(AuditEvent(aggregate_type="PLAN_VERSION", aggregate_id=str(candidate.id), action="REALLOCATION_CANDIDATE_CREATED",
                      actor_id=actor_id, old_state={"plan_version_id": str(source_plan.id)},
                      new_state={"plan_version_id": str(candidate.id), "order_id": str(order.id), "target_trip_id": str(target_trip.id)},
                      reason=reason.strip()))
    shortfall.status = "RESOLUTION_PENDING"
    shortfall.resolution = f"REALLOCATION: {reason.strip()}"
    shortfall.resolution_plan_version_id = candidate.id
    db.commit()
    return candidate


@loader.get("/trips")
def list_loader_trips(principal: Principal = Depends(require_roles("LOADER")), db: Session = Depends(get_db_session)) -> dict:
    trips = db.execute(select(Trip, Vehicle, PlanVersion).join(Vehicle, Vehicle.vehicle_id == Trip.vehicle_id)
                       .join(PlanVersion, PlanVersion.id == Trip.plan_version_id)
                       .where(Vehicle.depot_code == principal.user.depot_code, PlanVersion.status == "PUBLISHED")
                       .order_by(Trip.id)).all()
    result = []
    for trip, vehicle, plan in trips:
        manifest = _current_manifest(db, trip, principal.user.id)
        result.append({"id": str(trip.id), "vehicle_id": vehicle.vehicle_id, "driver": None,
                       "departure": (plan.published_at.isoformat() if plan.published_at else None),
                       "plan_version": plan.version_number, "trip_number": trip.trip_number,
                       "status": trip.status, "manifest": _manifest_read(db, manifest)})
    db.commit()
    return {"items": result}


@loader.get("/trips/{trip_id}/manifest")
def get_manifest(trip_id: UUID, principal: Principal = Depends(require_roles("LOADER")), db: Session = Depends(get_db_session)) -> dict:
    trip = _depot_trip(db, trip_id, principal)
    manifest = _current_manifest(db, trip, principal.user.id)
    db.commit()
    return {"manifest": _manifest_read(db, manifest)}


@loader.get("/trips/{trip_id}/manifests")
def list_manifest_versions(trip_id: UUID, principal: Principal = Depends(require_roles("LOADER")), db: Session = Depends(get_db_session)) -> dict:
    trip = _depot_trip(db, trip_id, principal)
    _current_manifest(db, trip, principal.user.id)
    versions = db.scalars(select(ManifestVersion).where(ManifestVersion.trip_id == trip.id).order_by(ManifestVersion.version_number)).all()
    db.commit()
    return {"items": [_manifest_read(db, item) for item in versions]}


@loader.post("/trips/{trip_id}/checks")
def submit_checks(trip_id: UUID, payload: CheckRequest, principal: Principal = Depends(require_roles("LOADER")), db: Session = Depends(get_db_session)) -> dict:
    trip = _depot_trip(db, trip_id, principal)
    version = _current_manifest(db, trip, principal.user.id)
    if version.version_number != payload.manifest_version or version.status != "CURRENT":
        raise api_error(409, "STALE_MANIFEST", "This manifest has been replaced. Refresh and acknowledge the current version.")
    checks = db.scalars(select(ManifestCheck).where(ManifestCheck.manifest_version_id == version.id)).all()
    by_order = {line.order_id: line for line in checks}
    if len({line.order_id for line in payload.lines}) != len(payload.lines) or any(line.order_id not in by_order for line in payload.lines):
        raise api_error(422, "INVALID_MANIFEST_LINE", "Each checked order must appear once on this manifest.")
    now = datetime.now(UTC)
    trip.status = "LOADING"
    for item in payload.lines:
        check = by_order[item.order_id]
        if item.quantity > check.expected_quantity:
            raise api_error(422, "QUANTITY_EXCEEDS_EXPECTED", "Loaded quantity cannot exceed the manifest quantity.")
        if item.status in {"LOADED", "SUBSTITUTE"} and item.quantity != check.expected_quantity:
            raise api_error(422, "QUANTITY_STATUS_MISMATCH", "Loaded or substitute quantity must match the manifest quantity.")
        loaded_quantity = check.expected_quantity - item.quantity if item.status in {"MISSING", "DAMAGED"} else item.quantity
        if item.status in {"MISSING", "DAMAGED"} and item.quantity == 0:
            raise api_error(422, "SHORTFALL_QUANTITY_REQUIRED", "Enter the number of missing or damaged units.")
        check.status, check.loaded_quantity, check.notes = item.status, loaded_quantity, item.notes
        check.checked_by_id, check.checked_at = principal.user.id, now
        if item.status in {"MISSING", "DAMAGED"}:
            db.add(Shortfall(trip_id=trip.id, order_id=item.order_id, reason=item.status, quantity=item.quantity,
                             blocking=True, status="OPEN", manifest_check_id=check.id, created_by_id=principal.user.id))
            trip.status = "DISPATCH_HOLD"
        elif item.status == "SUBSTITUTE" and item.quantity == check.expected_quantity:
            check.status = "SUBSTITUTE"
    open_blocking = db.scalar(select(Shortfall.id).where(Shortfall.trip_id == trip.id, Shortfall.status == "OPEN", Shortfall.blocking.is_(True)).limit(1))
    if not open_blocking and version.acknowledged_at and all(
        line.loaded_quantity >= line.expected_quantity or line.status == "SUBSTITUTE" for line in checks
    ):
        trip.status = "READY"
    db.add(AuditEvent(aggregate_type="TRIP", aggregate_id=str(trip.id), action="LOADING_CHECKED", actor_id=principal.user.id,
                      old_state=None, new_state={"manifest_version": version.version_number, "trip_status": trip.status},
                      metadata_={"line_count": len(payload.lines)}))
    db.commit()
    return {"manifest": _manifest_read(db, version), "trip_status": trip.status}


@loader.post("/manifests/{manifest_id}/acknowledge")
def acknowledge_manifest(manifest_id: UUID, principal: Principal = Depends(require_roles("LOADER")), db: Session = Depends(get_db_session)) -> dict:
    version = db.get(ManifestVersion, manifest_id)
    if version is None:
        raise api_error(404, "MANIFEST_NOT_FOUND", "The manifest was not found.")
    trip = _depot_trip(db, version.trip_id, principal)
    current = _current_manifest(db, trip, principal.user.id)
    if current.id != version.id or version.status != "CURRENT":
        raise api_error(409, "STALE_MANIFEST", "Only the current manifest can be acknowledged.")
    version.acknowledged_by_id, version.acknowledged_at = principal.user.id, datetime.now(UTC)
    open_blocking = db.scalar(select(Shortfall.id).where(Shortfall.trip_id == trip.id, Shortfall.status == "OPEN", Shortfall.blocking.is_(True)).limit(1))
    lines = db.scalars(select(ManifestCheck).where(ManifestCheck.manifest_version_id == version.id)).all()
    if not open_blocking and all(line.loaded_quantity >= line.expected_quantity or line.status == "SUBSTITUTE" for line in lines):
        trip.status = "READY"
    db.add(AuditEvent(aggregate_type="MANIFEST", aggregate_id=str(version.id), action="ACKNOWLEDGED", actor_id=principal.user.id,
                      old_state=None, new_state={"version_number": version.version_number, "trip_status": trip.status}))
    db.commit()
    return {"manifest": _manifest_read(db, version), "trip_status": trip.status}


@dispatcher.get("/shortfalls")
def list_shortfalls(principal: Principal = Depends(require_roles("DISPATCHER")), db: Session = Depends(get_db_session)) -> dict:
    rows = db.execute(select(Shortfall, Order).join(Order, Order.id == Shortfall.order_id)
                      .where(Shortfall.status.in_(("OPEN", "RESOLUTION_PENDING"))).order_by(Shortfall.created_at)).all()
    return {"items": [{"id": str(item.id), "trip_id": str(item.trip_id) if item.trip_id else None,
                       "order_id": str(order.id), "order_ref": order.reference, "quantity": item.quantity,
                       "reason": item.reason, "blocking": item.blocking, "status": item.status,
                       "resolution_plan_version_id": str(item.resolution_plan_version_id) if item.resolution_plan_version_id else None} for item, order in rows]}


@dispatcher.post("/shortfalls/{shortfall_id}/resolve")
def resolve_shortfall(shortfall_id: UUID, payload: ResolveRequest, principal: Principal = Depends(require_roles("DISPATCHER")), db: Session = Depends(get_db_session)) -> dict:
    item = db.get(Shortfall, shortfall_id)
    if item is None:
        raise api_error(404, "SHORTFALL_NOT_FOUND", "The shortfall was not found.")
    if item.status == "RESOLUTION_PENDING" and item.resolution_plan_version_id:
        candidate = db.get(PlanVersion, item.resolution_plan_version_id)
        if candidate:
            return {"shortfall_id": str(item.id), "status": item.status, "candidate_plan_id": str(candidate.id),
                    "candidate_version": candidate.version_number}
    if item.status != "OPEN":
        raise api_error(409, "SHORTFALL_ALREADY_RESOLVED", "This shortfall is already resolved.")
    if payload.action == "REALLOCATION":
        if payload.target_trip_id is None:
            raise api_error(422, "REALLOCATION_TARGET_REQUIRED", "Choose a target trip from the published plan.")
        candidate = _create_reallocation_candidate(db, item, payload.target_trip_id, payload.reason, principal.user.id)
        return {"shortfall_id": str(item.id), "status": item.status, "candidate_plan_id": str(candidate.id),
                "candidate_version": candidate.version_number}
    trip = db.get(Trip, item.trip_id) if item.trip_id else None
    if trip is None:
        raise api_error(409, "SHORTFALL_TRIP_MISSING", "The affected trip is unavailable.")
    old = _current_manifest(db, trip)
    old.status = "SUPERSEDED"
    item.status = "RESOLVED"
    item.resolution = f"{payload.action}: {payload.reason.strip()}"
    check = db.get(ManifestCheck, item.manifest_check_id) if item.manifest_check_id else None
    if check is None:
        raise api_error(409, "MANIFEST_CHECK_MISSING", "The loading check for this shortfall is unavailable.")
    new = ManifestVersion(trip_id=trip.id, version_number=old.version_number + 1, created_by_id=principal.user.id, status="CURRENT")
    db.add(new)
    db.flush()
    old_lines = db.scalars(select(ManifestCheck).where(ManifestCheck.manifest_version_id == old.id)).all()
    for previous in old_lines:
        qty, state = previous.expected_quantity, previous.status
        if previous.id == check.id:
            if payload.action == "PARTIAL_FULFILLMENT":
                if payload.quantity is None or payload.quantity > previous.expected_quantity:
                    raise api_error(422, "INVALID_RESOLUTION_QUANTITY", "Accepted partial quantity must be provided and cannot exceed the manifest quantity.")
                qty, state = payload.quantity, "LOADED"
            elif payload.action == "SUBSTITUTE":
                if not payload.substitute_reference:
                    raise api_error(422, "SUBSTITUTE_REQUIRED", "Provide the substitute item reference.")
                state = "SUBSTITUTE"
            elif payload.action == "RELOAD_FOUND":
                qty, state = previous.expected_quantity, "LOADED"
            elif payload.action == "DEFER":
                db.add(Deferral(order_id=previous.order_id, plan_version_id=trip.plan_version_id, reason="SHORTFALL_DEFERRED", notes=payload.reason))
                db.get(Order, previous.order_id).status = "DEFERRED"
                continue
        db.add(ManifestCheck(trip_id=trip.id, order_id=previous.order_id, expected_quantity=qty,
                             loaded_quantity=qty if state in {"LOADED", "SUBSTITUTE"} else previous.loaded_quantity,
                             status=state, manifest_version_id=new.id, load_sequence=previous.load_sequence,
                             notes=payload.substitute_reference if previous.id == check.id and payload.action == "SUBSTITUTE" else previous.notes))
    db.add(AuditEvent(aggregate_type="SHORTFALL", aggregate_id=str(item.id), action="RESOLVED", actor_id=principal.user.id,
                      old_state={"status": "OPEN"}, new_state={"action": payload.action, "manifest_version": new.version_number}, reason=payload.reason.strip()))
    db.flush()
    if not db.scalar(select(Shortfall.id).where(Shortfall.trip_id == trip.id, Shortfall.status == "OPEN", Shortfall.blocking.is_(True)).limit(1)):
        trip.status = "LOADING"
    db.commit()
    return {"shortfall_id": str(item.id), "status": item.status, "manifest": _manifest_read(db, new), "trip_status": trip.status}


@driver.post("/trips/{trip_id}/depart")
def depart_trip(trip_id: UUID, principal: Principal = Depends(require_roles("DRIVER")), db: Session = Depends(get_db_session)) -> dict:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise api_error(404, "TRIP_NOT_FOUND", "The trip was not found.")
    if trip.status == "DISPATCH_HOLD":
        raise api_error(409, "DEPARTURE_BLOCKED", "This trip is on dispatch hold until the loading exception is resolved.")
    raise api_error(409, "TRIP_NOT_READY", "This trip is not assigned and ready for departure.")
