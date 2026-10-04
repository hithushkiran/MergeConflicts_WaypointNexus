from datetime import UTC, datetime
from secrets import token_hex

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.database import get_db_session
from app.infrastructure.persistence import IdempotencyRecord, Order, Outlet
from app.modules.identity.routes import Principal, api_error, require_roles
from app.modules.orders.schemas import OrderCreate, OrderEligibility, OrderList, OrderRead
from app.modules.orders.service import calculate_order_timing


router = APIRouter(prefix="/api/v1/store/orders", tags=["store orders"])


def require_store_outlet(principal: Principal):
    outlet_id = principal.user.outlet_id
    if not outlet_id:
        raise api_error(status.HTTP_403_FORBIDDEN, "STORE_SCOPE_REQUIRED", "This store account has no assigned outlet.")
    return outlet_id


def order_response(order: Order) -> OrderRead:
    cutoff_at = order.cutoff_at
    if cutoff_at is not None:
        cutoff_at = cutoff_at.replace(tzinfo=UTC) if cutoff_at.tzinfo is None else cutoff_at.astimezone(UTC)
    return OrderRead(
        id=str(order.id),
        reference=order.reference,
        outlet_id=order.outlet_id,
        requested_delivery_date=order.requested_delivery_date,
        temperature_requirement=order.temperature_requirement,
        units=order.units,
        weight_kg=order.weight_kg,
        volume_m3=order.volume_m3,
        status=order.status,
        notes=order.notes,
        cutoff_at=cutoff_at,
    created_at=(
        order.created_at.replace(tzinfo=UTC)
        if order.created_at.tzinfo is None
        else order.created_at.astimezone(UTC)
    ),
    )


def eligibility_response(now: datetime | None = None) -> OrderEligibility:
    settings = get_settings()
    timing = calculate_order_timing(settings.order_cutoff_local_time, now)
    local_cutoff = timing.cutoff_at
    if timing.late_order:
        explanation = (
            f"Today's {settings.order_cutoff_local_time:%H:%M} Colombo cutoff has passed. "
            f"The next eligible delivery date is {timing.next_eligible_delivery_date.isoformat()}."
        )
    else:
        explanation = (
            f"Orders submitted by {settings.order_cutoff_local_time:%H:%M} Colombo are eligible "
            f"from {timing.next_eligible_delivery_date.isoformat()}."
        )
    return OrderEligibility(
        cutoff_at=local_cutoff.astimezone(UTC),
        cutoff_time=settings.order_cutoff_local_time.strftime("%H:%M"),
        next_eligible_delivery_date=timing.next_eligible_delivery_date,
        late_order=timing.late_order,
        explanation=explanation,
    )


def idempotency_conflict() -> HTTPException:
    return api_error(
        status.HTTP_409_CONFLICT,
        "IDEMPOTENCY_KEY_REUSED",
        "This idempotency key was already used for a different order request.",
    )


@router.get("/eligibility", response_model=OrderEligibility)
def get_order_eligibility(
    principal: Principal = Depends(require_roles("STORE")),
) -> OrderEligibility:
    require_store_outlet(principal)
    return eligibility_response()


@router.get("", response_model=OrderList)
def list_store_orders(
    principal: Principal = Depends(require_roles("STORE")),
    db: Session = Depends(get_db_session),
) -> OrderList:
    outlet_id = require_store_outlet(principal)
    orders = db.scalars(
        select(Order)
        .where(Order.outlet_id == outlet_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
    ).all()
    return OrderList(items=[order_response(order) for order in orders])


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_store_order(
    payload: OrderCreate,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    principal: Principal = Depends(require_roles("STORE")),
    db: Session = Depends(get_db_session),
) -> OrderRead:
    outlet_id = require_store_outlet(principal)
    if not idempotency_key.strip():
        raise api_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", "Idempotency-Key cannot be blank.")
    idempotency_key = idempotency_key.strip()
    if db.get(Outlet, outlet_id) is None:
        raise api_error(status.HTTP_403_FORBIDDEN, "STORE_SCOPE_UNAVAILABLE", "The assigned outlet is not available.")

    command = {**payload.model_dump(mode="json"), "actor_id": str(principal.user.id), "outlet_id": outlet_id}
    previous = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key))
    if previous is not None:
        if previous.command_type != "CREATE_STORE_ORDER" or previous.request_metadata != command:
            raise idempotency_conflict()
        if previous.result_metadata is None:
            raise api_error(status.HTTP_409_CONFLICT, "ORDER_REQUEST_IN_PROGRESS", "The order request is still processing.")
        response.status_code = status.HTTP_201_CREATED
        return OrderRead.model_validate(previous.result_metadata)

    eligibility = eligibility_response()
    if payload.requested_delivery_date < eligibility.next_eligible_delivery_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "ORDER_DATE_TOO_SOON",
                "message": (
                    f"The requested date is before the next eligible delivery date "
                    f"({eligibility.next_eligible_delivery_date.isoformat()}). {eligibility.explanation}"
                ),
                "fields": [
                    {
                        "field": "requested_delivery_date",
                        "message": f"Choose {eligibility.next_eligible_delivery_date.isoformat()} or later.",
                    }
                ],
            },
        )

    order = Order(
        reference=f"WN-{datetime.now(UTC):%Y%m%d}-{token_hex(4).upper()}",
        outlet_id=outlet_id,
        requested_delivery_date=payload.requested_delivery_date,
        temperature_requirement=payload.temperature_requirement,
        units=payload.units,
        weight_kg=payload.weight_kg,
        volume_m3=payload.volume_m3,
        status="CONFIRMED",
        notes=payload.notes,
        cutoff_at=eligibility.cutoff_at,
    )
    db.add(order)
    db.flush()
    created = order_response(order)
    record = IdempotencyRecord(
        key=idempotency_key,
        command_type="CREATE_STORE_ORDER",
        aggregate_id=str(order.id),
        request_metadata=command,
        result_metadata=created.model_dump(mode="json"),
        status="COMPLETED",
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key))
        if existing is not None:
            if existing.command_type != "CREATE_STORE_ORDER" or existing.request_metadata != command:
                raise idempotency_conflict()
            if existing.result_metadata is not None:
                response.status_code = status.HTTP_201_CREATED
                return OrderRead.model_validate(existing.result_metadata)
        raise
    db.refresh(order)
    return order_response(order)
