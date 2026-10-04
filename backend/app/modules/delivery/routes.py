"""Driver trip workflow and proof of delivery."""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.infrastructure.persistence import (
    AuditEvent, DeliveryEvent, IdempotencyRecord, ManifestCheck, ManifestVersion, Order,
    Outlet, PlanVersion, PlanningRun, ProofOfDelivery, Shortfall, Trip,
    TripStop, User, Vehicle,
)
from app.modules.identity.routes import Principal, api_error, require_roles

router = APIRouter(prefix="/api/v1/driver", tags=["driver delivery"])


class StopCompletion(BaseModel):
    outcome: str = Field(pattern="^(DELIVERED|FAILED)$")
    receiver_name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    occurred_at: datetime | None = None


class CommandTiming(BaseModel):
    occurred_at: datetime


def _event_time(provided: datetime | None, now: datetime) -> datetime:
    if provided is None:
        return now
    if provided.tzinfo is None or provided.utcoffset() is None:
        raise api_error(422, "TIMEZONE_REQUIRED", "The event timestamp must include its timezone.")
    occurred = provided.astimezone(UTC)
    if occurred > now + timedelta(minutes=5):
        raise api_error(422, "INVALID_EVENT_TIME", "The event timestamp cannot be in the future.")
    return occurred


def _trip_for_driver(db: Session, trip_id: UUID, principal: Principal) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None or trip.assigned_driver_id != principal.user.id:
        raise api_error(404, "TRIP_NOT_FOUND", "The assigned trip was not found.")
    plan = db.get(PlanVersion, trip.plan_version_id)
    run = db.get(PlanningRun, plan.planning_run_id) if plan else None
    current = db.scalar(select(PlanVersion).join(PlanningRun).where(PlanningRun.planning_date == run.planning_date, PlanVersion.status == "PUBLISHED").order_by(PlanVersion.published_at.desc(), PlanVersion.created_at.desc())) if run else None
    if not plan or plan.status != "PUBLISHED" or not current or current.id != plan.id:
        raise api_error(404, "TRIP_NOT_FOUND", "The assigned trip was not found.")
    return trip


def _manifest_ready(db: Session, trip: Trip) -> ManifestVersion | None:
    latest = db.scalar(select(ManifestVersion).where(ManifestVersion.trip_id == trip.id).order_by(ManifestVersion.version_number.desc()))
    if latest and latest.status == "CURRENT" and latest.acknowledged_at is not None:
        return latest
    return None


def _trip_read(db: Session, trip: Trip) -> dict:
    driver = db.get(User, trip.assigned_driver_id)
    vehicle = db.get(Vehicle, trip.vehicle_id)
    plan = db.get(PlanVersion, trip.plan_version_id)
    manifest = _manifest_ready(db, trip)
    rows = db.execute(select(TripStop, Order, Outlet).join(Order, Order.id == TripStop.order_id).join(Outlet, Outlet.outlet_id == Order.outlet_id).where(TripStop.trip_id == trip.id).order_by(TripStop.sequence_number)).all()
    manifest_order_ids = set(db.scalars(select(ManifestCheck.order_id).where(ManifestCheck.manifest_version_id == manifest.id)).all()) if manifest else set()
    manifest_lines = db.execute(
        select(ManifestCheck, Order, TripStop)
        .join(Order, Order.id == ManifestCheck.order_id)
        .join(TripStop, (TripStop.trip_id == ManifestCheck.trip_id) & (TripStop.order_id == ManifestCheck.order_id))
        .where(ManifestCheck.manifest_version_id == manifest.id)
        .order_by(ManifestCheck.load_sequence)
    ).all() if manifest else []
    return {
        "id": str(trip.id), "vehicle_id": trip.vehicle_id, "vehicle_type": vehicle.type if vehicle else None,
        "depot_code": vehicle.depot_code if vehicle else None, "driver_name": driver.display_name if driver else None,
        "trip_number": trip.trip_number, "brand": trip.brand, "district": trip.district, "status": trip.status,
        "plan_version": plan.version_number if plan else None,
        "manifest_version": manifest.version_number if manifest else None,
        "manifest": {"version_number": manifest.version_number, "lines": [{
            "order_id": str(check.order_id), "order_ref": order.reference, "outlet_id": order.outlet_id,
            "sequence_number": stop.sequence_number, "expected_quantity": check.expected_quantity,
            "loaded_quantity": check.loaded_quantity, "status": check.status, "notes": check.notes,
        } for check, order, stop in manifest_lines]} if manifest else None,
        "stops": [{"id": str(stop.id), "sequence_number": stop.sequence_number, "order_id": str(order.id),
                   "order_ref": order.reference, "outlet_id": outlet.outlet_id, "brand": outlet.brand,
                   "district": outlet.district, "window_open_time": outlet.window_open_time,
                   "window_close_time": outlet.window_close_time, "instructions": order.notes,
                   "planned_arrival": stop.planned_arrival.isoformat() if stop.planned_arrival else None,
                   "planned_service_minutes": stop.planned_service_minutes, "status": stop.status,
                   "arrived_at": stop.arrived_at.isoformat() if stop.arrived_at else None,
                   "completed_at": stop.completed_at.isoformat() if stop.completed_at else None}
                  for stop, order, outlet in rows if stop.order_id in manifest_order_ids],
    }


@router.get("/trips")
def list_my_trips(principal: Principal = Depends(require_roles("DRIVER")), db: Session = Depends(get_db_session)) -> dict:
    trips = db.scalars(select(Trip).where(Trip.assigned_driver_id == principal.user.id, Trip.status.in_(["READY", "IN_PROGRESS"])).order_by(Trip.id)).all()
    eligible = [trip for trip in trips if _manifest_ready(db, trip)]
    return {"items": [_trip_read(db, trip) for trip in eligible]}


@router.get("/trips/{trip_id}")
def get_my_trip(trip_id: UUID, principal: Principal = Depends(require_roles("DRIVER")), db: Session = Depends(get_db_session)) -> dict:
    trip = _trip_for_driver(db, trip_id, principal)
    return _trip_read(db, trip)


def _idempotent_replay(db: Session, key: str, command: str, aggregate: str, payload: dict, actor: UUID, command_id: str | None = None) -> dict | None:
    request_metadata = {"payload": payload, "actor_id": str(actor), "command_id": command_id}
    record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
    if record is None:
        db.add(IdempotencyRecord(key=key, command_type=command, aggregate_id=aggregate,
                                 request_metadata=request_metadata,
                                 result_metadata={"accepted": True, "command_id": command_id}, status="COMPLETED"))
        db.flush()
        return None
    if record.command_type != command or record.aggregate_id != aggregate or record.request_metadata != request_metadata:
        raise api_error(409, "IDEMPOTENCY_CONFLICT", "This command key was already used for a different request.")
    return {"replayed": True, "command_id": (record.request_metadata or {}).get("command_id")}


@router.post("/trips/{trip_id}/depart")
def depart_trip(trip_id: UUID, idempotency_key: str = Header(min_length=1, max_length=128, alias="Idempotency-Key"), command_id: str | None = Header(default=None, max_length=128, alias="X-Command-Id"), payload: CommandTiming | None = Body(default=None), principal: Principal = Depends(require_roles("DRIVER")), db: Session = Depends(get_db_session)) -> dict:
    trip = _trip_for_driver(db, trip_id, principal)
    now = datetime.now(UTC)
    occurred_at = _event_time(payload.occurred_at if payload else None, now)
    command_payload = {"occurred_at": payload.occurred_at.isoformat()} if payload else {}
    replay = _idempotent_replay(db, idempotency_key, "TRIP_DEPART", str(trip.id), command_payload, principal.user.id, command_id)
    if replay:
        db.rollback()
        return {"trip_id": str(trip.id), "status": trip.status, **replay}
    if trip.status == "DISPATCH_HOLD" or db.scalar(select(Shortfall.id).where(Shortfall.trip_id == trip.id, Shortfall.status == "OPEN", Shortfall.blocking.is_(True)).limit(1)):
        db.rollback()
        raise api_error(409, "DEPARTURE_BLOCKED", "This trip is on hold until the loading exception is resolved.")
    if trip.status != "READY" or _manifest_ready(db, trip) is None:
        db.rollback()
        raise api_error(409, "TRIP_NOT_READY", "The trip needs a current acknowledged manifest before departure.")
    trip.status, trip.started_at = "IN_PROGRESS", occurred_at
    db.add(AuditEvent(aggregate_type="TRIP", aggregate_id=str(trip.id), action="DEPARTED", actor_id=principal.user.id, new_state={"status": trip.status, "started_at": occurred_at.isoformat()}, correlation_id=idempotency_key))
    db.commit()
    return {"trip_id": str(trip.id), "status": trip.status, "command_id": command_id}


def _owned_stop(db: Session, stop_id: UUID, principal: Principal) -> tuple[TripStop, Trip, Order]:
    result = db.execute(select(TripStop, Trip, Order).join(Trip, Trip.id == TripStop.trip_id).join(Order, Order.id == TripStop.order_id).where(TripStop.id == stop_id)).first()
    if not result or result[1].assigned_driver_id != principal.user.id:
        raise api_error(404, "STOP_NOT_FOUND", "The assigned stop was not found.")
    trip = _trip_for_driver(db, result[1].id, principal)
    return result[0], trip, result[2]


@router.post("/stops/{stop_id}/arrive")
def arrive(stop_id: UUID, idempotency_key: str = Header(min_length=1, max_length=128, alias="Idempotency-Key"), command_id: str | None = Header(default=None, max_length=128, alias="X-Command-Id"), payload: CommandTiming | None = Body(default=None), principal: Principal = Depends(require_roles("DRIVER")), db: Session = Depends(get_db_session)) -> dict:
    stop, trip, _ = _owned_stop(db, stop_id, principal)
    now = datetime.now(UTC)
    occurred_at = _event_time(payload.occurred_at if payload else None, now)
    command_payload = {"occurred_at": payload.occurred_at.isoformat()} if payload else {}
    replay = _idempotent_replay(db, idempotency_key, "STOP_ARRIVE", str(stop.id), command_payload, principal.user.id, command_id)
    if replay:
        db.rollback()
        return {"stop_id": str(stop.id), "status": stop.status, **replay}
    if trip.status != "IN_PROGRESS" or stop.status != "PENDING":
        db.rollback()
        raise api_error(409, "STOP_NOT_READY", "The trip must be underway and this stop must still be pending.")
    prior = db.scalar(select(TripStop.id).where(TripStop.trip_id == trip.id, TripStop.sequence_number < stop.sequence_number, TripStop.status.not_in(["DELIVERED", "FAILED"])).limit(1))
    if prior:
        db.rollback()
        raise api_error(409, "STOP_ORDER_REQUIRED", "Complete the previous stop before arriving here.")
    stop.status, stop.arrived_at = "ARRIVED", occurred_at
    db.add(DeliveryEvent(trip_stop_id=stop.id, event_type="ARRIVED", occurred_at=occurred_at, command_ref=idempotency_key, actor_id=principal.user.id))
    db.add(AuditEvent(aggregate_type="TRIP_STOP", aggregate_id=str(stop.id), action="ARRIVED", actor_id=principal.user.id, new_state={"status": stop.status, "arrived_at": occurred_at.isoformat()}, correlation_id=idempotency_key))
    db.commit()
    return {"stop_id": str(stop.id), "status": stop.status, "arrived_at": occurred_at.isoformat(), "command_id": command_id}


@router.post("/stops/{stop_id}/complete")
def complete_stop(stop_id: UUID, payload: StopCompletion, idempotency_key: str = Header(min_length=1, max_length=128, alias="Idempotency-Key"), command_id: str | None = Header(default=None, max_length=128, alias="X-Command-Id"), principal: Principal = Depends(require_roles("DRIVER")), db: Session = Depends(get_db_session)) -> dict:
    stop, trip, order = _owned_stop(db, stop_id, principal)
    body = payload.model_dump()
    if payload.occurred_at is not None:
        body["occurred_at"] = payload.occurred_at.isoformat()
    replay = _idempotent_replay(db, idempotency_key, "STOP_COMPLETE", str(stop.id), body, principal.user.id, command_id)
    if replay:
        db.rollback()
        return {"stop_id": str(stop.id), "status": stop.status, **replay}
    if trip.status != "IN_PROGRESS" or stop.status != "ARRIVED":
        db.rollback()
        raise api_error(409, "STOP_NOT_ARRIVED", "Record arrival before completing delivery.")
    if payload.outcome == "DELIVERED" and not (payload.receiver_name or "").strip():
        db.rollback()
        raise api_error(422, "RECEIVER_REQUIRED", "Enter the name of the person who received the order.")
    if payload.outcome == "FAILED" and not (payload.notes or "").strip():
        db.rollback()
        raise api_error(422, "FAILURE_REASON_REQUIRED", "Enter a reason for the failed delivery.")
    now = datetime.now(UTC)
    occurred_at = _event_time(payload.occurred_at, now)
    manifest = _manifest_ready(db, trip)
    line = db.scalar(select(ManifestCheck).where(
        ManifestCheck.manifest_version_id == manifest.id, ManifestCheck.order_id == order.id
    )) if manifest else None
    if line is None:
        db.rollback()
        raise api_error(409, "DELIVERY_MANIFEST_UNAVAILABLE", "The acknowledged manifest must contain this order.")
    manifest_snapshot = {"id": str(manifest.id), "version_number": manifest.version_number,
                         "dispatched_quantity": line.loaded_quantity}
    stop.status, stop.completed_at = payload.outcome, occurred_at
    order.status = "DELIVERED" if payload.outcome == "DELIVERED" else "DELIVERY_FAILED"
    event = DeliveryEvent(trip_stop_id=stop.id, event_type=payload.outcome, occurred_at=occurred_at, command_ref=idempotency_key, actor_id=principal.user.id,
                          metadata_={"receiver_name": payload.receiver_name, "notes": payload.notes,
                                     "manifest": manifest_snapshot})
    db.add(event)
    db.flush()
    db.add(ProofOfDelivery(trip_stop_id=stop.id, delivery_event_id=event.id, receiver_name=payload.receiver_name,
                           outcome=payload.outcome, notes=payload.notes, created_at=occurred_at))
    db.add(AuditEvent(aggregate_type="TRIP_STOP", aggregate_id=str(stop.id), action=payload.outcome, actor_id=principal.user.id, old_state={"status": "ARRIVED"}, new_state={"status": stop.status, "order_status": order.status, "completed_at": occurred_at.isoformat()}, reason=payload.notes, correlation_id=idempotency_key))
    outstanding = db.scalar(select(TripStop.id).where(TripStop.trip_id == trip.id, TripStop.status.not_in(["DELIVERED", "FAILED"])).limit(1))
    if outstanding is None:
        trip.status, trip.completed_at = "COMPLETED", occurred_at
        db.add(AuditEvent(aggregate_type="TRIP", aggregate_id=str(trip.id), action="COMPLETED", actor_id=principal.user.id, new_state={"status": "COMPLETED", "completed_at": occurred_at.isoformat()}))
    db.commit()
    return {"stop_id": str(stop.id), "status": stop.status, "trip_status": trip.status, "proof_recorded": True, "command_id": command_id}
