"""Hard-constraint eligibility checks kept independent from allocation."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reasons: tuple[str, ...]
    unverified: tuple[str, ...]


def evaluate_vehicle(
    order: dict[str, Any],
    outlet: dict[str, Any],
    vehicle: dict[str, Any],
    *,
    availability_known: bool = False,
    available: bool | None = None,
    weekly_fuel_used_l: float = 0,
    access_compatible: bool | None = None,
    estimated_trip_km: float | None = None,
    estimated_arrival_minutes: int | None = None,
) -> EligibilityResult:
    """Evaluate one order/vehicle pair; unknown constraints never pass silently.

    ``eligible`` means every hard constraint was verified. Missing availability,
    route/fuel estimates, or unsupported access labels are reported separately
    so callers cannot mistake an unknown assignment for a valid one.
    """
    reasons: list[str] = []
    unverified: list[str] = []

    if outlet.get("depot_code") != vehicle.get("depot_code"):
        reasons.append("DEPOT_MISMATCH")
    if float(order.get("weight_kg", 0)) > float(vehicle.get("weight_cap_kg", 0)):
        reasons.append("WEIGHT_CAPACITY_EXCEEDED")
    if float(order.get("volume_m3", 0)) > float(vehicle.get("volume_cap_m3", 0)):
        reasons.append("VOLUME_CAPACITY_EXCEEDED")
    requirement = str(order.get("temperature_requirement", "")).strip().lower()
    capability = str(vehicle.get("temperature_capability", vehicle.get("temp", ""))).strip().lower()
    if requirement in {"chilled", "frozen"} and capability != "reefer":
        # Published rule: reefer vehicles serve chilled/frozen and ambient loads.
        reasons.append("TEMPERATURE_INCOMPATIBLE")
    elif requirement not in {"chilled", "frozen", "ambient"} or (
        requirement == "ambient" and capability not in {"ambient", "reefer"}
    ):
        reasons.append("TEMPERATURE_INCOMPATIBLE")

    if access_compatible is not None:
        compatible = access_compatible
    else:
        parking_rule = str(outlet.get("parking_constraint", "")).strip().lower()
        if parking_rule == "van_only":
            compatible = str(vehicle.get("type", "")).strip().lower() == "van"
        else:
            # Task 2B defines van_only as the only vehicle-specific parking rule.
            compatible = True
    if not compatible:
        reasons.append("VEHICLE_ACCESS_INCOMPATIBLE")

    if not availability_known:
        unverified.append("VEHICLE_AVAILABILITY_UNKNOWN")
    elif available is not True:
        reasons.append("VEHICLE_UNAVAILABLE")

    if estimated_trip_km is None:
        unverified.append("TRAVEL_DISTANCE_UNKNOWN")
    else:
        km_per_l = float(vehicle.get("km_per_l", 0))
        if estimated_trip_km < 0 or km_per_l <= 0:
            reasons.append("FUEL_ESTIMATE_INVALID")
        else:
            estimated_liters = estimated_trip_km / km_per_l
            quota = float(vehicle.get("weekly_fuel_quota_l", 0)) - weekly_fuel_used_l
            if estimated_liters > quota:
                reasons.append("FUEL_QUOTA_EXCEEDED")

    window_open = outlet.get("window_open_time")
    window_close = outlet.get("window_close_time")
    if window_open or window_close:
        if estimated_arrival_minutes is None:
            unverified.append("DELIVERY_WINDOW_UNVERIFIED")
        else:
            try:
                def minute_of_day(value: str) -> int:
                    hour, minute = map(int, value.split(":", 1))
                    if not 0 <= hour < 24 or not 0 <= minute < 60:
                        raise ValueError
                    return hour * 60 + minute

                # Early arrival can wait until the receiving window opens.
                if window_close and estimated_arrival_minutes > minute_of_day(window_close):
                    reasons.append("ARRIVAL_AFTER_DELIVERY_WINDOW")
            except (ValueError, AttributeError):
                reasons.append("DELIVERY_WINDOW_CONFIGURATION_INVALID")

    return EligibilityResult(
        eligible=not reasons and not unverified,
        reasons=tuple(sorted(set(reasons))),
        unverified=tuple(sorted(set(unverified))),
    )
