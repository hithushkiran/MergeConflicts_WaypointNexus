from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.infrastructure.persistence import DeliveryIssue, Order, Outlet, Receipt
from app.modules.identity.routes import Principal, api_error, require_roles
from app.modules.orders.routes import require_store_outlet
from app.modules.receipt.schemas import IssueCreate, IssueReview, ReceiptCreate
from app.modules.receipt.service import delivery_read, issue_read, receipt_read, receive, review, scoped_order

store = APIRouter(prefix="/api/v1/store", tags=["store receipt"])
dispatcher = APIRouter(prefix="/api/v1/dispatcher", tags=["delivery issues"])


@store.get("/deliveries")
def deliveries(principal: Principal = Depends(require_roles("STORE")), db: Session = Depends(get_db_session)) -> dict:
    orders = db.scalars(select(Order).where(Order.outlet_id == require_store_outlet(principal),
                                           Order.status.in_(("DELIVERED", "RECEIVED")))
                        .order_by(Order.created_at.desc(), Order.id)).all()
    return {"items": [delivery_read(db, order) for order in orders], "next_cursor": None}


@store.get("/orders/{order_id}/delivery")
def delivery(order_id: UUID, principal: Principal = Depends(require_roles("STORE")), db: Session = Depends(get_db_session)) -> dict:
    return delivery_read(db, scoped_order(db, order_id, principal))


@store.get("/orders/{order_id}/receipt")
def saved_receipt(order_id: UUID, principal: Principal = Depends(require_roles("STORE")), db: Session = Depends(get_db_session)) -> dict:
    order = scoped_order(db, order_id, principal)
    receipt = db.scalar(select(Receipt).where(Receipt.order_id == order.id))
    if receipt is None:
        raise api_error(404, "RECEIPT_NOT_FOUND", "No receiving decision has been recorded.")
    return receipt_read(receipt)


@store.post("/orders/{order_id}/receipt", status_code=201)
def confirm_receipt(order_id: UUID, payload: ReceiptCreate,
                    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
                    principal: Principal = Depends(require_roles("STORE")), db: Session = Depends(get_db_session)) -> dict:
    return receive(db, order_id, payload, principal, idempotency_key)


@store.post("/orders/{order_id}/issues", status_code=201)
def report_issue(order_id: UUID, payload: IssueCreate,
                 idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
                 principal: Principal = Depends(require_roles("STORE")), db: Session = Depends(get_db_session)) -> dict:
    return receive(db, order_id, payload, principal, idempotency_key)


def issue_collection(db: Session, principal: Principal, status: str | None = None) -> dict:
    query = select(DeliveryIssue, Order, Outlet).join(Order, Order.id == DeliveryIssue.order_id).join(Outlet, Outlet.outlet_id == Order.outlet_id)
    if principal.role == "STORE":
        query = query.where(Order.outlet_id == require_store_outlet(principal))
    elif principal.user.depot_code:
        query = query.where(Outlet.depot_code == principal.user.depot_code)
    if status:
        query = query.where(DeliveryIssue.status == status)
    rows = db.execute(query.order_by(DeliveryIssue.created_at.desc(), DeliveryIssue.id)).all()
    items = []
    for issue, order, outlet in rows:
        receipt = db.get(Receipt, issue.receipt_id) if issue.receipt_id else None
        items.append({**issue_read(issue), "order_ref": order.reference, "order_status": order.status,
                      "outlet_id": outlet.outlet_id, "depot_code": outlet.depot_code,
                      "receipt": receipt_read(receipt) if receipt else None})
    return {"items": items, "next_cursor": None}


@store.get("/issues")
def store_issues(principal: Principal = Depends(require_roles("STORE")), db: Session = Depends(get_db_session)) -> dict:
    return issue_collection(db, principal)


@dispatcher.get("/delivery-issues")
def delivery_issues(status: str | None = Query(default=None, pattern="^(OPEN|IN_REVIEW|RESOLVED)$"),
                    principal: Principal = Depends(require_roles("DISPATCHER")), db: Session = Depends(get_db_session)) -> dict:
    return issue_collection(db, principal, status)


@dispatcher.post("/delivery-issues/{issue_id}/review")
def review_issue(issue_id: UUID, payload: IssueReview,
                 idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
                 principal: Principal = Depends(require_roles("DISPATCHER")), db: Session = Depends(get_db_session)) -> dict:
    return review(db, issue_id, payload, principal, idempotency_key)
