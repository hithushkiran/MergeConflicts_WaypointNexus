from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


COLOMBO = ZoneInfo("Asia/Colombo")


@dataclass(frozen=True)
class OrderTiming:
    cutoff_at: datetime
    next_eligible_delivery_date: date
    late_order: bool


def calculate_order_timing(
    cutoff_time: time,
    now: datetime | None = None,
) -> OrderTiming:
    """Return today's Colombo cutoff and the earliest eligible calendar date."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_now = now.astimezone(COLOMBO)
    cutoff_at = datetime.combine(local_now.date(), cutoff_time, tzinfo=COLOMBO)
    late_order = local_now > cutoff_at
    days_until_delivery = 1 if late_order else 0
    return OrderTiming(
        cutoff_at=cutoff_at,
        next_eligible_delivery_date=local_now.date() + timedelta(days=days_until_delivery),
        late_order=late_order,
    )
