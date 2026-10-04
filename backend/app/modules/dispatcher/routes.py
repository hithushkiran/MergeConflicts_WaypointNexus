"""Role-guarded dispatcher order review and plan publication endpoints."""

import os
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.infrastructure.persistence import (
    AuditEvent,
    Deferral,
    IdempotencyRecord,
    ManifestCheck,
    ManifestVersion,
    Order,
    Outlet,
    PlanVersion,
    PlanningRun,
    Shortfall,
    Trip,
    TripStop,
)
from app.modules.dispatcher.schemas import (
    DispatcherOrderList,
    DispatcherOrderRead,
    PlanCandidateResponse,
    PlanCreate,
    PlanPublish,
    PlanPublishResponse,
    PlanVersionList,
    PlanVersionRead,
)
from app.modules.identity.routes import Principal, api_error, require_roles
from app.modules.planning.allocation import allocate_scenario, persist_scenario_allocation
from app.modules.planning.reference_data import load_planning_references_for_date
from app.modules.planning.snapshot import build_planning_snapshot, persist_planning_snapshot


router = APIRouter(prefix="/api/v1/dispatcher", tags=["dispatcher"])


def _order_read(order: Order, outlet: Outlet, prior_day_deferral: bool) -> DispatcherOrderRead:
    return DispatcherOrderRead(
        id=str(order.id),
        reference=order.reference,
        outlet_id=outlet.outlet_id,
        brand=outlet.brand,
        district=outlet.district,
        depot_code=outlet.depot_code,
        dock_type=outlet.dock_type,
        parking_constraint=outlet.parking_constraint,
        window_open_time=outlet.window_open_time,
        window_close_time=outlet.window_close_time,
        requested_delivery_date=order.requested_delivery_date,
        temperature_requirement=order.temperature_requirement,
        units=order.units,
        weight_kg=order.weight_kg,
        volume_m3=order.volume_m3,
        status=order.status,
        prior_day_deferral=prior_day_deferral,
    )


def _plan_read(db: Session, version: PlanVersion, diagnostics: list[str] | None = None) -> PlanVersionRead:
    run = db.get(PlanningRun, version.planning_run_id)
    if run is None:
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "PLAN_SNAPSHOT_MISSING", "The plan snapshot is unavailable.")
    trip_rows = db.scalars(
        select(Trip).where(Trip.plan_version_id == version.id).order_by(Trip.vehicle_id, Trip.trip_number)
    ).all()
    trip_output = []
    order_output = []
    for trip in trip_rows:
        stops = db.execute(
            select(TripStop, Order, Outlet)
            .join(Order, Order.id == TripStop.order_id)
            .join(Outlet, Outlet.outlet_id == Order.outlet_id)
            .where(TripStop.trip_id == trip.id)
            .order_by(TripStop.sequence_number)
        ).all()
        trip_output.append({
            "id": str(trip.id),
            "vehicle_id": trip.vehicle_id,
            "trip_number": trip.trip_number,
            "brand": trip.brand,
            "district": trip.district,
            "status": trip.status,
            "metrics": trip.metrics or {},
            "stops": [{
                "sequence_number": stop.sequence_number,
                "order_id": str(order.id),
                "order_ref": order.reference,
                "outlet_id": outlet.outlet_id,
                "planned_arrival": stop.planned_arrival.isoformat() if stop.planned_arrival else None,
                "planned_service_minutes": stop.planned_service_minutes,
            } for stop, order, outlet in stops],
        })
        for stop, order, outlet in stops:
            order_output.append({
                "order_id": str(order.id),
                "order_ref": order.reference,
                "decision": "served",
                "vehicle_id": trip.vehicle_id,
                "trip_number": trip.trip_number,
                "outlet_id": outlet.outlet_id,
                "district": outlet.district,
                "brand": outlet.brand,
            })
    deferrals = db.execute(
        select(Deferral, Order).join(Order, Order.id == Deferral.order_id)
        .where(Deferral.plan_version_id == version.id).order_by(Order.reference)
    ).all()
    order_output.extend({
        "order_id": str(order.id),
        "order_ref": order.reference,
        "decision": "deferred",
        "vehicle_id": None,
        "trip_number": None,
        "reason": deferral.reason,
        "notes": deferral.notes,
    } for deferral, order in deferrals)
    if diagnostics is None:
        created_event = db.scalar(select(AuditEvent).where(
            AuditEvent.aggregate_type == "PLAN_VERSION",
            AuditEvent.aggregate_id == str(version.id),
            AuditEvent.action == "CANDIDATE_CREATED",
        ))
        diagnostics = (created_event.new_state or {}).get("diagnostics", []) if created_event else []
    return PlanVersionRead(
        id=str(version.id),
        planning_run_id=str(version.planning_run_id),
        planning_date=run.planning_date,
        version_number=version.version_number,
        status=version.status,
        created_at=version.created_at,
        published_at=version.published_at,
        orders=order_output,
        trips=trip_output,
        diagnostics=diagnostics or [],
    )


@router.get("/orders", response_model=DispatcherOrderList)
def list_dispatcher_orders(
    planning_date: date | None = None,
    depot: str | None = None,
    brand: str | None = None,
    district: str | None = None,
    temperature: str | None = Query(default=None, pattern="^(AMBIENT|CHILLED|FROZEN)$"),
    access: str | None = None,
    delivery_window: str | None = Query(default=None, pattern="^(restricted|none)$"),
    prior_deferral: bool | None = None,
    principal: Principal = Depends(require_roles("DISPATCHER")),
    db: Session = Depends(get_db_session),
) -> DispatcherOrderList:
    del principal
    query = (
        select(Order, Outlet)
        .join(Outlet, Outlet.outlet_id == Order.outlet_id)
        .where(Order.status == "CONFIRMED")
        .order_by(Order.requested_delivery_date, Outlet.depot_code, Outlet.brand, Outlet.district, Order.reference)
    )
    if planning_date is not None:
        query = query.where(Order.requested_delivery_date == planning_date)
    if depot:
        query = query.where(Outlet.depot_code == depot)
    if brand:
        query = query.where(Outlet.brand.ilike(brand))
    if district:
        query = query.where(Outlet.district.ilike( district))
    if temperature:
        query = query.where(Order.temperature_requirement == temperature)
    if access:
        query = query.where(Outlet.parking_constraint.ilike(access))
    if delivery_window == "restricted":
        query = query.where(
            Outlet.window_open_time.is_not(None), Outlet.window_open_time != "",
            Outlet.window_close_time.is_not(None), Outlet.window_close_time != "",
        )
    elif delivery_window == "none":
        query = query.where(
            or_(Outlet.window_open_time.is_(None), Outlet.window_open_time == ""),
            or_(Outlet.window_close_time.is_(None), Outlet.window_close_time == ""),
        )
    deferred_before = exists(
        select(Deferral.id)
        .join(PlanVersion, PlanVersion.id == Deferral.plan_version_id)
        .join(PlanningRun, PlanningRun.id == PlanVersion.planning_run_id)
        .where(Deferral.order_id == Order.id, PlanningRun.planning_date < Order.requested_delivery_date)
    )
    if prior_deferral is True:
        query = query.where(deferred_before)
    elif prior_deferral is False:
        query = query.where(~deferred_before)
    results = db.execute(query).all()
    items = []
    for order, outlet in results:
        was_deferred = db.scalar(select(deferred_before.where(Deferral.order_id == order.id)))
        items.append(_order_read(order, outlet, bool(was_deferred)))
    return DispatcherOrderList(items=items)


@router.post("/plans", response_model=PlanCandidateResponse, status_code=status.HTTP_201_CREATED)
def create_plan_candidate(
    payload: PlanCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    principal: Principal = Depends(require_roles("DISPATCHER")),
    db: Session = Depends(get_db_session),
) -> PlanCandidateResponse:
    key = idempotency_key.strip()
    if not key:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", "Idempotency-Key cannot be blank.")
    command = {"actor_id": str(principal.user.id), "planning_date": payload.planning_date.isoformat()}
    prior = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
    if prior:
        if prior.command_type != "CREATE_PLAN_CANDIDATE" or prior.request_metadata != command:
            raise api_error(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUSED", "This idempotency key was already used for a different command.")
        if prior.result_metadata is None:
            raise api_error(status.HTTP_409_CONFLICT, "COMMAND_IN_PROGRESS", "The plan creation request is still processing.")
        version_id = UUID(prior.result_metadata["plan_version_id"])
        existing_version = db.get(PlanVersion, version_id)
        if existing_version is None:
            raise api_error(status.HTTP_409_CONFLICT, "PLAN_VERSION_MISSING", "The saved result for this request is unavailable.")
        return PlanCandidateResponse(plan=_plan_read(db, existing_version))

    local_dir = Path(os.getenv("PLANNING_DATA_DIR", "/app/local-data"))
    demo_dir = Path(__file__).parents[3] / "demo-data"
    required = {
        "task2b_peak_day_scenarios.csv", "task2b_peak_day_fleet.csv", "calendar.csv",
        "district_travel.csv", "service_allowance.csv", "vehicles.csv",
    }
    local_present = {name for name in required if (local_dir / name).is_file()}
    if local_present:
        if local_present != required:
            missing = sorted(required - local_present)
            raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "PLANNING_INPUTS_INCOMPLETE", f"Planning inputs are missing: {', '.join(missing)}.")
        reference_dir = local_dir
    elif os.getenv("APP_ENV", "development").lower() == "development":
        reference_dir = demo_dir
    else:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "PLANNING_INPUTS_UNAVAILABLE", "Planning reference data is not configured.")
    try:
        scenarios = load_planning_references_for_date(reference_dir, payload.planning_date)
    except IntegrityError:
        db.rollback()
        existing_command = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
        if existing_command and existing_command.command_type == "CREATE_PLAN_CANDIDATE" and existing_command.request_metadata == command and existing_command.result_metadata:
            existing_version = db.get(PlanVersion, UUID(existing_command.result_metadata["plan_version_id"]))
            if existing_version is not None:
                return PlanCandidateResponse(plan=_plan_read(db, existing_version))
        raise api_error(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUSED", "This idempotency key conflicts with another request.")
    except ValueError as error:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "PLANNING_INPUTS_INVALID", str(error)) from error
    if len(scenarios) != 1:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "PLANNING_SCENARIO_UNAVAILABLE", "Exactly one configured planning scenario is required for this date.")
    reference_data = scenarios[0]
    confirmed_refs = set(db.scalars(select(Order.reference).where(
        Order.requested_delivery_date == payload.planning_date,
        Order.status == "CONFIRMED",
    )).all())
    scenario_refs = {order["order_ref"] for order in reference_data.orders}
    if not scenario_refs or scenario_refs != confirmed_refs:
        missing = sorted(scenario_refs - confirmed_refs)
        extra = sorted(confirmed_refs - scenario_refs)
        detail = []
        if missing:
            detail.append(f"not confirmed: {', '.join(missing[:5])}")
        if extra:
            detail.append(f"not represented in the configured scenario: {', '.join(extra[:5])}")
        raise api_error(status.HTTP_409_CONFLICT, "SCENARIO_ORDER_COVERAGE_MISMATCH", "The planning scenario must account for every confirmed order on the selected date (" + "; ".join(detail) + ").")
    try:
        snapshot = build_planning_snapshot(db, payload.planning_date)
        planning_run = persist_planning_snapshot(db, snapshot)
        result = allocate_scenario(reference_data)
        version = persist_scenario_allocation(db, planning_run, result)
        version.created_by_id = principal.user.id
        db.add(AuditEvent(
            aggregate_type="PLAN_VERSION",
            aggregate_id=str(version.id),
            action="CANDIDATE_CREATED",
            actor_id=principal.user.id,
            new_state={"status": "DRAFT", "version_number": version.version_number,
                       "planning_date": payload.planning_date.isoformat(),
                       "snapshot_hash": planning_run.snapshot_hash,
                       "diagnostics": list(result.diagnostics)},
        ))
        db.add(IdempotencyRecord(
            key=key,
            command_type="CREATE_PLAN_CANDIDATE",
            aggregate_id=str(version.id),
            request_metadata=command,
            result_metadata={"plan_version_id": str(version.id)},
            status="COMPLETED",
        ))
        db.commit()
        db.refresh(version)
    except ValueError as error:
        db.rollback()
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "PLAN_VALIDATION_FAILED", str(error)) from error
    return PlanCandidateResponse(plan=_plan_read(db, version, list(result.diagnostics)))


@router.get("/plans/{plan_version_id}", response_model=PlanCandidateResponse)
def get_plan_candidate(
    plan_version_id: UUID,
    principal: Principal = Depends(require_roles("DISPATCHER")),
    db: Session = Depends(get_db_session),
) -> PlanCandidateResponse:
    del principal
    version = db.get(PlanVersion, plan_version_id)
    if version is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "PLAN_NOT_FOUND", "Plan version was not found.")
    return PlanCandidateResponse(plan=_plan_read(db, version))


@router.get("/plans", response_model=PlanVersionList)
def list_plan_versions(
    planning_date: date | None = None,
    principal: Principal = Depends(require_roles("DISPATCHER")),
    db: Session = Depends(get_db_session),
) -> PlanVersionList:
    del principal
    query = select(PlanVersion).join(PlanningRun, PlanningRun.id == PlanVersion.planning_run_id)
    if planning_date is not None:
        query = query.where(PlanningRun.planning_date == planning_date)
    versions = db.scalars(query.order_by(PlanVersion.created_at.desc(), PlanVersion.version_number.desc()).limit(50)).all()
    return PlanVersionList(items=[_plan_read(db, version) for version in versions])


@router.post("/plans/{plan_version_id}/publish", response_model=PlanPublishResponse)
def publish_plan(
    plan_version_id: UUID,
    payload: PlanPublish,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    principal: Principal = Depends(require_roles("DISPATCHER")),
    db: Session = Depends(get_db_session),
) -> PlanPublishResponse:
    key = idempotency_key.strip()
    if not key:
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", "Idempotency-Key cannot be blank.")
    command = {"actor_id": str(principal.user.id), "plan_version_id": str(plan_version_id),
               "reason": (payload.reason or "").strip() or None}
    prior = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
    if prior:
        if prior.command_type != "PUBLISH_PLAN_VERSION" or prior.request_metadata != command:
            raise api_error(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUSED", "This idempotency key was already used for a different command.")
        if prior.result_metadata is None:
            raise api_error(status.HTTP_409_CONFLICT, "COMMAND_IN_PROGRESS", "The publication request is still processing.")
        return PlanPublishResponse(**prior.result_metadata, replayed=True)

    version = db.scalar(select(PlanVersion).where(PlanVersion.id == plan_version_id).with_for_update())
    if version is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "PLAN_NOT_FOUND", "Plan version was not found.")
    if version.status != "DRAFT":
        raise api_error(status.HTTP_409_CONFLICT, "PLAN_NOT_DRAFT", "Only a draft plan version can be published.")
    trip_rows = db.scalars(select(Trip).where(Trip.plan_version_id == version.id)).all()
    if any(not trip.metrics or not trip.metrics.get("time_windows_valid", False) for trip in trip_rows):
        raise api_error(status.HTTP_409_CONFLICT, "PLAN_VALIDATION_FAILED", "The plan has a trip with an invalid delivery window.")
    stop_rows = db.execute(
        select(TripStop, Order).join(Order, Order.id == TripStop.order_id)
        .join(Trip, Trip.id == TripStop.trip_id).where(Trip.plan_version_id == version.id)
    ).all()
    deferral_rows = db.execute(
        select(Deferral, Order).join(Order, Order.id == Deferral.order_id)
        .where(Deferral.plan_version_id == version.id)
    ).all()
    decisions = [order for _stop, order in stop_rows] + [order for _deferral, order in deferral_rows]
    decision_ids = [order.id for order in decisions]
    if len(decision_ids) != len(set(decision_ids)) or not decisions:
        raise api_error(status.HTTP_409_CONFLICT, "PLAN_COVERAGE_INVALID", "Every planned order must have exactly one served or deferred decision.")
    predecessor = None
    if version.revises_plan_version_id:
        predecessor = db.get(PlanVersion, version.revises_plan_version_id)
        if predecessor is None or predecessor.status != "PUBLISHED":
            raise api_error(status.HTTP_409_CONFLICT, "PLAN_REVISION_STALE", "The published plan this candidate revises is no longer current.")
        old_stops = db.scalars(select(TripStop).join(Trip, Trip.id == TripStop.trip_id).where(Trip.plan_version_id == predecessor.id)).all()
        old_deferrals = db.scalars(select(Deferral).where(Deferral.plan_version_id == predecessor.id)).all()
        if {stop.order_id for stop in old_stops} | {defer.order_id for defer in old_deferrals} != set(decision_ids):
            raise api_error(status.HTTP_409_CONFLICT, "PLAN_COVERAGE_INVALID", "A revised plan must cover exactly the orders from the plan it replaces.")
        if any(order.status not in {"PLANNED", "DEFERRED"} for order in decisions):
            raise api_error(status.HTTP_409_CONFLICT, "ORDER_STATE_CHANGED", "One or more orders changed after this plan was generated.")
    elif any(order.status != "CONFIRMED" for order in decisions):
        raise api_error(status.HTTP_409_CONFLICT, "ORDER_STATE_CHANGED", "One or more orders changed after this plan was created.")

    now = datetime.now(UTC)
    if predecessor:
        predecessor.status = "SUPERSEDED"
        old_trips = db.scalars(select(Trip).where(Trip.plan_version_id == predecessor.id)).all()
        old_trip_ids = [trip.id for trip in old_trips]
        for old_trip in old_trips:
            old_trip.status = "SUPERSEDED"
        db.flush()
        blocking_issues = db.scalars(select(Shortfall).where(
            Shortfall.trip_id.in_(old_trip_ids), Shortfall.status.in_(("OPEN", "RESOLUTION_PENDING")),
            Shortfall.blocking.is_(True),
            or_(Shortfall.resolution_plan_version_id.is_(None), Shortfall.resolution_plan_version_id != version.id),
        )).all() if old_trip_ids else []
        if blocking_issues:
            raise api_error(status.HTTP_409_CONFLICT, "OTHER_OPEN_SHORTFALLS", "Resolve all other loading exceptions on the old plan before publishing this reallocation.")
        reallocation_issue = db.scalar(select(Shortfall).where(Shortfall.resolution_plan_version_id == version.id, Shortfall.status == "RESOLUTION_PENDING"))
        if reallocation_issue is None:
            raise api_error(status.HTTP_409_CONFLICT, "REALLOCATION_SHORTFALL_MISSING", "This revised plan is not linked to an open reallocation.")
        reallocation_issue.status = "RESOLVED"
        reallocation_issue.resolution += f" (published as plan V{version.version_number})"
        db.add(AuditEvent(aggregate_type="SHORTFALL", aggregate_id=str(reallocation_issue.id), action="RESOLVED_BY_REALLOCATION",
                          actor_id=principal.user.id, old_state={"status": "RESOLUTION_PENDING"},
                          new_state={"status": "RESOLVED", "plan_version_id": str(version.id)}, reason=reallocation_issue.resolution))
        for old_trip in old_trips:
            old_manifests = db.scalars(select(ManifestVersion).where(ManifestVersion.trip_id == old_trip.id)).all()
            prior_number = max((manifest.version_number for manifest in old_manifests), default=0)
            for old_manifest in old_manifests:
                old_manifest.status = "SUPERSEDED"
            revised_trip = next((trip for trip in trip_rows if trip.vehicle_id == old_trip.vehicle_id and trip.trip_number == old_trip.trip_number), None)
            if revised_trip is None:
                continue
            revised_manifest = ManifestVersion(trip_id=revised_trip.id, version_number=prior_number + 1,
                                               created_by_id=principal.user.id, status="CURRENT")
            db.add(revised_manifest)
            db.flush()
            revised_stops = db.execute(select(TripStop, Order).join(Order, Order.id == TripStop.order_id)
                                       .where(TripStop.trip_id == revised_trip.id).order_by(TripStop.sequence_number)).all()
            for revised_stop, revised_order in revised_stops:
                db.add(ManifestCheck(trip_id=revised_trip.id, order_id=revised_order.id,
                                     expected_quantity=revised_order.units, loaded_quantity=0, status="PENDING",
                                     manifest_version_id=revised_manifest.id, load_sequence=revised_stop.sequence_number))
    for _stop, order in stop_rows:
        order.status = "PLANNED"
    for _deferral, order in deferral_rows:
        order.status = "DEFERRED"
    for trip in trip_rows:
        trip.status = "PLANNED"
    version.status = "PUBLISHED"
    version.published_at = now
    db.add(AuditEvent(
        aggregate_type="PLAN_VERSION",
        aggregate_id=str(version.id),
        action="PUBLISHED",
        actor_id=principal.user.id,
        old_state={"status": "DRAFT"},
        new_state={"status": "PUBLISHED", "version_number": version.version_number,
                   "served_orders": len(stop_rows), "deferred_orders": len(deferral_rows),
                   "revises_plan_version_id": str(predecessor.id) if predecessor else None},
        reason=command["reason"],
    ))
    response_data = {
        "plan_version_id": str(version.id),
        "version_number": version.version_number,
        "status": "PUBLISHED",
        "published_at": now.isoformat(),
        "served_orders": len(stop_rows),
        "deferred_orders": len(deferral_rows),
    }
    db.add(IdempotencyRecord(
        key=key,
        command_type="PUBLISH_PLAN_VERSION",
        aggregate_id=str(version.id),
        request_metadata=command,
        result_metadata=response_data,
        status="COMPLETED",
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
        if existing and existing.command_type == "PUBLISH_PLAN_VERSION" and existing.request_metadata == command and existing.result_metadata:
            return PlanPublishResponse(**existing.result_metadata, replayed=True)
        raise
    return PlanPublishResponse(**response_data)
