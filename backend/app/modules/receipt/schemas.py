from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReceiptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    receiver_name: str = Field(min_length=1, max_length=120)
    received_quantity: int = Field(ge=0, strict=True)
    notes: str | None = Field(default=None, max_length=1000)


class IssueCreate(ReceiptCreate):
    issue_type: Literal["MISSING_QUANTITY", "DAMAGED", "WRONG_ITEM", "OTHER"]
    affected_quantity: int = Field(gt=0, strict=True)
    notes: str = Field(min_length=1, max_length=1000)


class IssueReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["IN_REVIEW", "RESOLVED"]
    reason: str = Field(min_length=1, max_length=1000)
