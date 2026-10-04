"""Authoritative receipt/issue facts, scoped reads and atomic receiving commands."""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.persistence import (
    AuditEvent, DeliveryEvent, DeliveryIssue, IdempotencyRecord, ManifestCheck,
    ManifestVersion, Order, Outlet, ProofOfDelivery, Receipt, Trip, TripStop, User, Vehicle,
)
from app.modules.identity.routes import Principal, api_error
from app.modules.orders.routes import require_store_outlet
from app.modules.receipt.schemas import IssueCreate, IssueReview, ReceiptCreate


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)).isoformat()


def scoped_order(db: Session, order_id: UUID, principal: Principal, lock: bool = False) -> Order:
    query = select(Order).where(Order.id == order_id)
    if principal.role == "STORE":
        query = query.where(Order.outlet_id == require_store_outlet(principal))
    elif principal.user.depot_code:
        query = query.join(Outlet).where(Outlet.depot_code == principal.user.depot_code)
    if lock:
        query = query.with_for_update(of=Order)
    order = db.scalar(query.execution_options(populate_existing=True))
    if order is None:
        raise api_error(404, "ORDER_NOT_FOUND", "The order was not found.")
    return order


def receipt_read(receipt: Receipt) -> dict:
    return {"id": str(receipt.id), "order_id": str(receipt.order_id),
            "trip_stop_id": str(receipt.trip_stop_id) if receipt.trip_stop_id else None,
            "status": receipt.status, "receiver_name": receipt.receiver_name,
            "ordered_quantity": receipt.ordered_quantity, "dispatched_quantity": receipt.dispatched_quantity,
            "received_quantity": receipt.received_quantity, "notes": receipt.notes,
            "confirmed_by_id": str(receipt.confirmed_by_id) if receipt.confirmed_by_id else None,
            "confirmed_at": utc_iso(receipt.confirmed_at),
            "manifest_version_id": str(receipt.manifest_version_id) if receipt.manifest_version_id else None}


def issue_read(issue: DeliveryIssue) -> dict:
    return {"id": str(issue.id), "receipt_id": str(issue.receipt_id) if issue.receipt_id else None,
            "order_id": str(issue.order_id), "issue_type": issue.issue_type, "status": issue.status,
            "affected_quantity": issue.affected_quantity, "notes": issue.notes,
            "reported_by_id": str(issue.reported_by_id) if issue.reported_by_id else None,
            "created_at": utc_iso(issue.created_at), "resolution_notes": issue.resolution_notes,
            "resolved_by_id": str(issue.resolved_by_id) if issue.resolved_by_id else None,
            "resolved_at": utc_iso(issue.resolved_at)}


def delivery_read(db: Session, order: Order) -> dict:
    row = db.execute(select(TripStop, ProofOfDelivery, Trip)
                     .join(ProofOfDelivery, ProofOfDelivery.trip_stop_id == TripStop.id)
                     .join(Trip, Trip.id == TripStop.trip_id)
                     .where(TripStop.order_id == order.id, TripStop.status == "DELIVERED",
                            ProofOfDelivery.outcome == "DELIVERED")
                     .order_by(ProofOfDelivery.created_at.desc(), ProofOfDelivery.id).limit(1)).first()
    if order.status not in {"DELIVERED", "RECEIVED"} or row is None:
        raise api_error(409, "DELIVERY_NOT_COMPLETE", "A successfully synced delivery is required before receiving this order.")
    stop, proof, trip = row
    event = db.get(DeliveryEvent, proof.delivery_event_id) if proof.delivery_event_id else None
    snapshot = (event.metadata_ or {}).get("manifest") if event else None
    if snapshot:
        manifest_id = snapshot["id"]
        manifest_number = snapshot["version_number"]
        dispatched = snapshot["dispatched_quantity"]
    else:
        # T07 deliveries predate the quantity snapshot. Require actual acknowledged data.
        manifest = db.scalar(select(ManifestVersion).where(
            ManifestVersion.trip_id == trip.id, ManifestVersion.acknowledged_at.is_not(None)
        ).order_by(ManifestVersion.version_number.desc()))
        line = db.scalar(select(ManifestCheck).where(
            ManifestCheck.manifest_version_id == manifest.id, ManifestCheck.order_id == order.id
        )) if manifest else None
        if line is None:
            raise api_error(409, "DELIVERY_QUANTITY_UNAVAILABLE", "The acknowledged delivery manifest is unavailable.")
        manifest_id, manifest_number, dispatched = str(manifest.id), manifest.version_number, line.loaded_quantity
    outlet = db.get(Outlet, order.outlet_id)
    vehicle = db.get(Vehicle, trip.vehicle_id)
    driver = db.get(User, trip.assigned_driver_id) if trip.assigned_driver_id else None
    receipt = db.scalar(select(Receipt).where(Receipt.order_id == order.id))
    issue = db.scalar(select(DeliveryIssue).where(DeliveryIssue.order_id == order.id).order_by(DeliveryIssue.created_at.desc()).limit(1))
    return {"order_id": str(order.id), "order_ref": order.reference, "order_status": order.status,
            "outlet_id": order.outlet_id, "brand": outlet.brand, "district": outlet.district,
            "depot_code": outlet.depot_code, "temperature_requirement": order.temperature_requirement,
            "ordered_quantity": order.units, "ordered_weight_kg": order.weight_kg,
            "dispatched_quantity": dispatched, "trip_stop_id": str(stop.id),
            "manifest_version_id": manifest_id, "manifest_version": manifest_number,
            "vehicle_id": trip.vehicle_id, "vehicle_type": vehicle.type if vehicle else None,
            "driver_name": driver.display_name if driver else None, "delivered_at": utc_iso(proof.created_at),
            "pod_receiver_name": proof.receiver_name, "pod_notes": proof.notes,
            "receipt": receipt_read(receipt) if receipt else None, "issue": issue_read(issue) if issue else None}


def replay(db: Session, key: str, command_type: str, aggregate_id: str, command: dict) -> dict | None:
    prior = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
    if prior is None:
        return None
    if prior.command_type != command_type or prior.aggregate_id != aggregate_id or prior.request_metadata != command:
        raise api_error(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for a different request.")
    if prior.result_metadata is None:
        raise api_error(409, "COMMAND_IN_PROGRESS", "The request is still processing.")
    return prior.result_metadata


def commit_command(db: Session, key: str, command_type: str, aggregate_id: str, command: dict, result: dict) -> dict:
    db.add(IdempotencyRecord(key=key, command_type=command_type, aggregate_id=aggregate_id,
                             request_metadata=command, result_metadata=result, status="COMPLETED"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = replay(db, key, command_type, aggregate_id, command)
        if prior is not None:
            return prior
        raise api_error(409, "RECEIPT_ALREADY_RECORDED", "This order already has a receiving decision.") from None
    return result


def key_value(key: str) -> str:
    if not key.strip():
        raise api_error(422, "VALIDATION_ERROR", "Idempotency-Key cannot be blank.")
    return key.strip()


def receive(db: Session, order_id: UUID, payload: ReceiptCreate, principal: Principal, key: str) -> dict:
    key = key_value(key)
    order = scoped_order(db, order_id, principal, lock=True)
    reporting = isinstance(payload, IssueCreate)
    command_type = "REPORT_DELIVERY_ISSUE" if reporting else "CONFIRM_STORE_RECEIPT"
    command = {"actor_id": str(principal.user.id), "payload": payload.model_dump(mode="json")}
    prior = replay(db, key, command_type, str(order.id), command)
    if prior is not None:
        return prior
    if db.scalar(select(Receipt.id).where(Receipt.order_id == order.id)):
        raise api_error(409, "RECEIPT_ALREADY_RECORDED", "This order already has a receiving decision.")
    delivery = delivery_read(db, order)
    if order.status != "DELIVERED":
        raise api_error(409, "RECEIPT_NOT_ELIGIBLE", "Only a delivered order can be received.")
    if payload.received_quantity > delivery["dispatched_quantity"]:
        raise api_error(422, "QUANTITY_EXCEEDS_DISPATCHED", "Received units cannot exceed dispatched units.")
    if payload.received_quantity < delivery["dispatched_quantity"] and not payload.notes:
        raise api_error(422, "PARTIAL_RECEIPT_REASON_REQUIRED", "Explain the difference from the dispatched quantity.")
    if reporting:
        if payload.issue_type == "MISSING_QUANTITY":
            if payload.affected_quantity != order.units - payload.received_quantity:
                raise api_error(422, "ISSUE_QUANTITY_MISMATCH", "Missing units must equal ordered units minus received units.")
        elif payload.affected_quantity > delivery["dispatched_quantity"]:
            raise api_error(422, "ISSUE_QUANTITY_MISMATCH", "Affected units cannot exceed dispatched units.")
    now = datetime.now(UTC)
    receipt = Receipt(order_id=order.id, trip_stop_id=UUID(delivery["trip_stop_id"]),
                      manifest_version_id=UUID(delivery["manifest_version_id"]),
                      status="DISPUTED" if reporting else ("CONFIRMED" if payload.received_quantity == order.units else "PARTIAL"),
                      ordered_quantity=order.units, dispatched_quantity=delivery["dispatched_quantity"],
                      received_quantity=payload.received_quantity, receiver_name=payload.receiver_name,
                      confirmed_by_id=principal.user.id, confirmed_at=now, notes=payload.notes)
    db.add(receipt)
    # The order row is locked in PostgreSQL; its unique receipt constraint also guards other stores.
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        prior = replay(db, key, command_type, str(order_id), command)
        if prior is not None:
            return prior
        raise api_error(409, "RECEIPT_ALREADY_RECORDED", "This order already has a receiving decision.") from None
    issue = None
    if reporting:
        issue = DeliveryIssue(order_id=order.id, receipt_id=receipt.id, issue_type=payload.issue_type,
                              affected_quantity=payload.affected_quantity, notes=payload.notes, status="OPEN",
                              reported_by_id=principal.user.id, created_at=now)
        db.add(issue)
        db.flush()
    else:
        order.status = "RECEIVED"
    result = {"receipt": receipt_read(receipt), "issue": issue_read(issue) if issue else None, "order_status": order.status}
    db.add(AuditEvent(aggregate_type="ORDER", aggregate_id=str(order.id),
                      action="DELIVERY_ISSUE_REPORTED" if reporting else "RECEIPT_CONFIRMED",
                      actor_id=principal.user.id, old_state={"status": "DELIVERED"}, new_state=result,
                      reason=payload.notes, correlation_id=key,
                      metadata_={"manifest_version_id": delivery["manifest_version_id"], "manifest_version": delivery["manifest_version"]}))
    return commit_command(db, key, command_type, str(order.id), command, result)


def review(db: Session, issue_id: UUID, payload: IssueReview, principal: Principal, key: str) -> dict:
    key = key_value(key)
    issue = db.get(DeliveryIssue, issue_id)
    if issue is None:
        raise api_error(404, "ISSUE_NOT_FOUND", "The delivery issue was not found.")
    # Use the same order-first locking order as receiving to serialize review and retries.
    order = scoped_order(db, issue.order_id, principal, lock=True)
    db.refresh(issue)
    command = {"actor_id": str(principal.user.id), "payload": payload.model_dump(mode="json")}
    prior = replay(db, key, "REVIEW_DELIVERY_ISSUE", str(issue.id), command)
    if prior is not None:
        return prior
    expected = "OPEN" if payload.status == "IN_REVIEW" else "IN_REVIEW"
    receipt = db.get(Receipt, issue.receipt_id) if issue.receipt_id else None
    if issue.status != expected or receipt is None or receipt.status != "DISPUTED" or order.status != "DELIVERED":
        raise api_error(409, "ISSUE_INVALID_TRANSITION", "Start review before resolving an open delivery issue.")
    old_status = issue.status
    issue.status = payload.status
    if payload.status == "RESOLVED":
        issue.resolution_notes, issue.resolved_by_id, issue.resolved_at = payload.reason, principal.user.id, datetime.now(UTC)
        receipt.status = "CONFIRMED" if receipt.received_quantity == receipt.ordered_quantity else "PARTIAL"
        order.status = "RECEIVED"
    result = {"issue": issue_read(issue), "receipt": receipt_read(receipt), "order_status": order.status}
    db.add(AuditEvent(aggregate_type="DELIVERY_ISSUE", aggregate_id=str(issue.id),
                      action="DELIVERY_ISSUE_RESOLVED" if payload.status == "RESOLVED" else "DELIVERY_ISSUE_REVIEWED",
                      actor_id=principal.user.id, old_state={"status": old_status}, new_state=result,
                      reason=payload.reason, correlation_id=key,
                      metadata_={"order_id": str(order.id), "manifest_version_id": str(receipt.manifest_version_id) if receipt.manifest_version_id else None}))
    return commit_command(db, key, "REVIEW_DELIVERY_ISSUE", str(issue.id), command, result)
