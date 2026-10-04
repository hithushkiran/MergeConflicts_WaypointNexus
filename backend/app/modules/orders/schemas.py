from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TemperatureRequirement = Literal["AMBIENT", "CHILLED", "FROZEN"]


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_delivery_date: date
    temperature_requirement: TemperatureRequirement
    units: int = Field(gt=0, le=100_000)
    weight_kg: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    volume_m3: float = Field(gt=0, le=100_000, allow_inf_nan=False)
    notes: str | None = Field(default=None, max_length=500)


class OrderRead(BaseModel):
    id: str
    reference: str
    outlet_id: str
    requested_delivery_date: date
    temperature_requirement: TemperatureRequirement
    units: int
    weight_kg: float
    volume_m3: float
    status: str
    notes: str | None
    cutoff_at: datetime | None
    created_at: datetime


class OrderList(BaseModel):
    items: list[OrderRead]
    next_cursor: str | None = None


class OrderEligibility(BaseModel):
    cutoff_at: datetime
    cutoff_time: str
    next_eligible_delivery_date: date
    late_order: bool
    explanation: str
