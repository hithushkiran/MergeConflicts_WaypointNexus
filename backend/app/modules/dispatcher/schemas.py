from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DispatcherOrderRead(BaseModel):
    id: str
    reference: str
    outlet_id: str
    brand: str
    district: str
    depot_code: str
    dock_type: str
    parking_constraint: str
    window_open_time: str | None
    window_close_time: str | None
    requested_delivery_date: date
    temperature_requirement: str
    units: int
    weight_kg: float
    volume_m3: float
    status: str
    prior_day_deferral: bool


class DispatcherOrderList(BaseModel):
    items: list[DispatcherOrderRead]
    next_cursor: str | None = None


class PlanCreate(BaseModel):
    planning_date: date


class PlanPublish(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class PlanVersionRead(BaseModel):
    id: str
    planning_run_id: str
    planning_date: date
    version_number: int
    status: str
    created_at: datetime
    published_at: datetime | None = None
    orders: list[dict[str, Any]]
    trips: list[dict[str, Any]]
    diagnostics: list[str] = Field(default_factory=list)


class PlanCandidateResponse(BaseModel):
    plan: PlanVersionRead


class PlanVersionList(BaseModel):
    items: list[PlanVersionRead]


class PlanPublishResponse(BaseModel):
    plan_version_id: str
    version_number: int
    status: Literal["PUBLISHED"]
    published_at: datetime
    served_orders: int
    deferred_orders: int
    replayed: bool = False
