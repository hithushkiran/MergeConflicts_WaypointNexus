"""Deterministic, single-trip vehicle allocation using OR-Tools CP-SAT."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ortools.sat.python import cp_model
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.persistence import Deferral, Order, PlanVersion, PlanningRun, Trip, TripStop
from app.modules.planning.eligibility import evaluate_vehicle
from app.modules.planning.reference_data import PlanningReferenceData


@dataclass(frozen=True)
class AllocationResult:
    status: str
    assignments: tuple[dict[str, str], ...]
    deferred: tuple[dict[str, Any], ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioAllocationResult:
    status: str
    rows: tuple[dict[str, Any], ...]
    trips: tuple[dict[str, Any], ...]
    diagnostics: tuple[str, ...]


def allocate_orders(
    orders: list[dict[str, Any]],
    outlets: dict[str, dict[str, Any]],
    vehicles: list[dict[str, Any]],
    constraint_evidence: dict[tuple[str, str], dict[str, Any]],
    *,
    time_limit_seconds: float = 5.0,
) -> AllocationResult:
    """Assign at most one vehicle to each order while respecting hard limits.

    ``constraint_evidence`` is keyed by ``(order_id, vehicle_id)`` and supplies
    verified availability and route estimates to the independent eligibility
    engine. Unknown evidence excludes that pair from the solver.
    """
    ordered_orders = sorted(orders, key=lambda row: (row["reference"], row["id"]))
    ordered_vehicles = sorted(vehicles, key=lambda row: row["vehicle_id"])
    model = cp_model.CpModel()
    choices: dict[tuple[str, str], cp_model.IntVar] = {}
    fuel_liters: dict[tuple[str, str], float] = {}
    eligible_candidates: dict[str, list[dict[str, Any]]] = {order["id"]: [] for order in ordered_orders}
    candidate_reasons: dict[str, set[str]] = {order["id"]: set() for order in ordered_orders}
    unverified_reasons: dict[str, set[str]] = {order["id"]: set() for order in ordered_orders}

    for order in ordered_orders:
        outlet = outlets.get(order["outlet_id"], {})
        for vehicle in ordered_vehicles:
            evidence = constraint_evidence.get((order["id"], vehicle["vehicle_id"]), {})
            result = evaluate_vehicle(
                order,
                outlet,
                vehicle,
                availability_known=evidence.get("availability_known", False),
                available=evidence.get("available"),
                access_compatible=evidence.get("access_compatible"),
                estimated_trip_km=evidence.get("estimated_trip_km"),
                estimated_arrival_minutes=evidence.get("estimated_arrival_minutes"),
            )
            candidate_reasons[order["id"]].update(result.reasons)
            if result.unverified:
                unverified_reasons[order["id"]].update(result.unverified)
            if result.eligible:
                eligible_candidates[order["id"]].append(vehicle)
                choices[(order["id"], vehicle["vehicle_id"])] = model.new_bool_var(
                    f"assign_{order['id']}_{vehicle['vehicle_id']}"
                )
                fuel_liters[(order["id"], vehicle["vehicle_id"])] = (
                    float(evidence["estimated_trip_km"]) / float(vehicle["km_per_l"])
                )

    for order in ordered_orders:
        order_vars = [var for (order_id, _), var in choices.items() if order_id == order["id"]]
        if order_vars:
            model.add(sum(order_vars) <= 1)
    for vehicle in ordered_vehicles:
        vehicle_id = vehicle["vehicle_id"]
        assigned = [(order, choices[(order["id"], vehicle_id)]) for order in ordered_orders
                    if (order["id"], vehicle_id) in choices]
        if assigned:
            # Integer scaling keeps the model precise for decimal capacities.
            model.add(sum(round(float(order["weight_kg"]) * 1000) * var for order, var in assigned)
                      <= round(float(vehicle["weight_cap_kg"]) * 1000))
            model.add(sum(round(float(order["volume_m3"]) * 1000) * var for order, var in assigned)
                      <= round(float(vehicle["volume_cap_m3"]) * 1000))
            model.add(sum(round(fuel_liters[(order["id"], vehicle_id)] * 1000) * var
                          for order, var in assigned)
                      <= round(float(vehicle["weekly_fuel_quota_l"]) * 1000))

    # Prioritize served orders, then use fewer vehicles, then stable ordering.
    served = list(choices.values())
    used_vehicle_vars: dict[str, cp_model.IntVar] = {}
    for vehicle in ordered_vehicles:
        vehicle_id = vehicle["vehicle_id"]
        vehicle_choices = [var for (order_id, vid), var in choices.items() if vid == vehicle_id]
        if vehicle_choices:
            used = model.new_bool_var(f"used_{vehicle_id}")
            model.add(sum(vehicle_choices) >= used)
            model.add(sum(vehicle_choices) <= len(ordered_orders) * used)
            used_vehicle_vars[vehicle_id] = used
    tie_break = [((index + 1) * (vehicle_index + 1), var)
                 for index, order in enumerate(ordered_orders)
                 for vehicle_index, vehicle in enumerate(ordered_vehicles)
                 if (var := choices.get((order["id"], vehicle["vehicle_id"]))) is not None]
    tie_bound = max(1, len(tie_break) ** 2 + 1)
    served_weight = (len(used_vehicle_vars) + 1) * tie_bound
    objective = served_weight * sum(served) - tie_bound * sum(used_vehicle_vars.values())
    if tie_break:
        objective -= sum(weight * var for weight, var in tie_break)
    model.maximize(objective)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.01, time_limit_seconds)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status_code = solver.solve(model)
    status_name = solver.status_name(status_code)
    assignments = tuple(
        {"order_id": order["id"], "vehicle_id": vehicle["vehicle_id"]}
        for order in ordered_orders
        for vehicle in ordered_vehicles
        if (order["id"], vehicle["vehicle_id"]) in choices
        and solver.boolean_value(choices[(order["id"], vehicle["vehicle_id"])])
    ) if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE) else ()
    assigned_ids = {item["order_id"] for item in assignments}
    assigned_by_vehicle: dict[str, list[dict[str, Any]]] = {}
    order_by_id = {order["id"]: order for order in ordered_orders}
    for assignment in assignments:
        assigned_by_vehicle.setdefault(assignment["vehicle_id"], []).append(
            order_by_id[assignment["order_id"]]
        )
    deferred = []
    for order in ordered_orders:
        if order["id"] in assigned_ids:
            continue
        reasons = sorted(candidate_reasons[order["id"]])
        if unverified_reasons[order["id"]]:
            reasons.extend(sorted(unverified_reasons[order["id"]]))
            reasons.append("CONSTRAINTS_UNVERIFIED")
        if not reasons:
            for vehicle in eligible_candidates[order["id"]]:
                vehicle_id = vehicle["vehicle_id"]
                current_load = assigned_by_vehicle.get(vehicle_id, [])
                if not current_load:
                    continue
                if sum(float(item["weight_kg"]) for item in current_load) + float(order["weight_kg"]) > float(vehicle["weight_cap_kg"]):
                    reasons.append("AGGREGATE_WEIGHT_CAPACITY_EXCEEDED")
                if sum(float(item["volume_m3"]) for item in current_load) + float(order["volume_m3"]) > float(vehicle["volume_cap_m3"]):
                    reasons.append("AGGREGATE_VOLUME_CAPACITY_EXCEEDED")
                current_fuel = sum(fuel_liters[(item["id"], vehicle_id)] for item in current_load)
                if current_fuel + fuel_liters[(order["id"], vehicle_id)] > float(vehicle["weekly_fuel_quota_l"]):
                    reasons.append("AGGREGATE_FUEL_QUOTA_EXCEEDED")
            if not reasons:
                reasons.append("NO_ELIGIBLE_VEHICLE")
        deferred.append({"order_id": order["id"], "reasons": sorted(set(reasons))})

    diagnostics = []
    if status_code == cp_model.UNKNOWN:
        diagnostics.append("OPTIMIZER_TIMEOUT_WITHOUT_FEASIBLE_SOLUTION")
    elif status_code == cp_model.FEASIBLE:
        diagnostics.append("OPTIMIZER_TIMEOUT_RETURNED_BEST_FEASIBLE_SOLUTION")
    elif status_code == cp_model.INFEASIBLE:
        diagnostics.append("NO_FEASIBLE_ASSIGNMENT")
    return AllocationResult(status=status_name, assignments=assignments,
                            deferred=tuple(deferred), diagnostics=tuple(diagnostics))


def allocate_scenario(
    data: PlanningReferenceData,
    *,
    time_limit_seconds: float = 5.0,
) -> ScenarioAllocationResult:
    """Allocate a seeded operating-day scenario to up to two coherent trips/vehicle."""
    if not data.is_operating_day:
        return ScenarioAllocationResult(
            status="NOT_OPERATING_DAY",
            rows=tuple({"scenario": data.scenario, "order_ref": order["order_ref"],
                        "decision": "deferred", "vehicle_id": None, "trip_id": None,
                        "reasons": ["NON_OPERATING_DAY"]} for order in data.orders),
            trips=(),
            diagnostics=("CALENDAR_MARKS_DATE_NON_OPERATING",),
        )

    orders = list(data.orders)
    vehicles = list(data.vehicles)
    model = cp_model.CpModel()
    assign: dict[tuple[str, str, int], cp_model.IntVar] = {}
    candidates: dict[str, list[tuple[str, str, int]]] = {o["order_ref"]: [] for o in orders}
    reasons: dict[str, set[str]] = {o["order_ref"]: set() for o in orders}
    unverified: dict[str, set[str]] = {o["order_ref"]: set() for o in orders}
    order_by_ref = {o["order_ref"]: o for o in orders}
    vehicle_by_id = {v["vehicle_id"]: v for v in vehicles}

    for order in orders:
        route = data.travel[order["district"]]
        allowance = data.service_allowance[(order["brand"], order["dock_type"])]
        departure = 3 * 60 + 30 if order["brand"] == "Fresh" else 8 * 60
        estimated_arrival = departure + int(route["depot_to_district_freeflow_min"] + allowance)
        outlet = {
            "depot_code": order["depot"],
            "parking_constraint": order["parking_constraint"],
            "window_open_time": order["window_open_time"],
            "window_close_time": order["window_close_time"],
        }
        normalized_order = {
            **order, "reference": order["order_ref"],
            "temperature_requirement": order["temp_requirement"],
        }
        for vehicle in vehicles:
            available = data.availability.get(vehicle["vehicle_id"])
            result = evaluate_vehicle(
                normalized_order,
                outlet,
                vehicle,
                availability_known=available is not None,
                available=available,
                weekly_fuel_used_l=vehicle["weekly_fuel_used_l"],
                estimated_trip_km=route["trip_route_km"],
                estimated_arrival_minutes=estimated_arrival,
            )
            reasons[order["order_ref"]].update(result.reasons)
            unverified[order["order_ref"]].update(result.unverified)
            if result.eligible:
                for trip_no in (1, 2):
                    key = (order["order_ref"], vehicle["vehicle_id"], trip_no)
                    assign[key] = model.new_bool_var(
                        f"assign_{order['order_ref']}_{vehicle['vehicle_id']}_{trip_no}"
                    )
                    candidates[order["order_ref"]].append(key)

    for order in orders:
        vars_ = [assign[key] for key in candidates[order["order_ref"]]]
        if vars_:
            model.add(sum(vars_) <= 1)

    group_active: dict[tuple[str, int, str, str], cp_model.IntVar] = {}
    group_keys = sorted({(vid, trip, order_by_ref[ref]["brand"], order_by_ref[ref]["district"])
                         for ref, vid, trip in assign})
    for vid, trip, brand, district in group_keys:
        key = (vid, trip, brand, district)
        group_active[key] = model.new_bool_var(f"trip_{vid}_{trip}_{brand}_{district}")
        group_orders = [ref for ref, v, t in assign
                        if v == vid and t == trip and order_by_ref[ref]["brand"] == brand
                        and order_by_ref[ref]["district"] == district]
        group_vars = [assign[(ref, vid, trip)] for ref in group_orders]
        for ref in group_orders:
            model.add(assign[(ref, vid, trip)] <= group_active[key])
        model.add(group_active[key] <= sum(group_vars))

    for vid, trip in sorted({(vid, trip) for _, vid, trip in assign}):
        active_groups = [var for (v, t, _, _), var in group_active.items() if v == vid and t == trip]
        if active_groups:
            model.add(sum(active_groups) <= 1)
        assigned = [(order_by_ref[ref], assign[(ref, v, t)])
                    for ref, v, t in assign if v == vid and t == trip]
        vehicle = vehicle_by_id[vid]
        model.add(sum(round(o["weight_kg"] * 1000) * x for o, x in assigned)
                  <= round(vehicle["weight_cap_kg"] * 1000))
        model.add(sum(round(o["volume_m3"] * 1000) * x for o, x in assigned)
                  <= round(vehicle["volume_cap_m3"] * 1000))

    # Enforce per-vehicle weekly fuel and the Fresh/daytime operating windows.
    for vehicle in vehicles:
        vid = vehicle["vehicle_id"]
        vehicle_groups = [(key, var) for key, var in group_active.items() if key[0] == vid]
        model.add(
            round(vehicle["weekly_fuel_used_l"] * 1000)
            + sum(round(data.travel[district]["trip_route_km"] / vehicle["km_per_l"] * 1000) * var
                  for (v, _trip, _brand, district), var in vehicle_groups)
            <= round(vehicle["weekly_fuel_quota_l"] * 1000)
        )
        for brand, budget in (("Fresh", 270), ("__DAYTIME__", 480)):
            time_terms = []
            for (v, trip, trip_brand, district), active in vehicle_groups:
                if (brand == "Fresh") != (trip_brand == "Fresh"):
                    continue
                route = data.travel[district]
                interstop = int(route["inter_stop_freeflow_min"])
                base = int(route["depot_to_district_freeflow_min"])
                group_order_refs = [ref for ref, cv, ct in assign if cv == vid and ct == trip
                                    and order_by_ref[ref]["brand"] == trip_brand
                                    and order_by_ref[ref]["district"] == district]
                xs = [assign[(ref, vid, trip)] for ref in group_order_refs]
                services = [int(data.service_allowance[(order_by_ref[ref]["brand"],
                                                         order_by_ref[ref]["dock_type"])])
                            * assign[(ref, vid, trip)] for ref in group_order_refs]
                time_terms.append((base - interstop) * active + interstop * sum(xs) + sum(services))
            model.add(sum(time_terms) <= budget)

    # Serve as many as possible; among equally large plans prefer prior-day
    # deferrals, then fewer active trips and stable order/vehicle/slot choices.
    tie_bound = len(assign) ** 2 + 1
    active_bound = max(1, len(group_active))
    prior_weight = (active_bound + 1) * tie_bound
    served_weight = (len(orders) + 1) * prior_weight
    served_terms = []
    prior_terms = []
    for order in orders:
        order_vars = [assign[key] for key in candidates[order["order_ref"]]]
        served_terms.extend(served_weight * var for var in order_vars)
        if order["prior_day_deferral"]:
            prior_terms.extend(prior_weight * var for var in order_vars)
    active_terms = list(group_active.values())
    tie_terms = [rank * var for rank, var in enumerate(assign.values(), start=1)]
    model.maximize(sum(served_terms) + sum(prior_terms)
                   - tie_bound * sum(active_terms) - sum(tie_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.01, time_limit_seconds)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status_code = solver.solve(model)
    has_solution = status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    rows: list[dict[str, Any]] = []
    for order in orders:
        selected = next((key for key in candidates[order["order_ref"]]
                         if has_solution and solver.boolean_value(assign[key])), None)
        if selected:
            _, vid, trip = selected
            rows.append({"scenario": data.scenario, "order_ref": order["order_ref"],
                         "decision": "served", "vehicle_id": vid, "trip_id": trip,
                         "reasons": [], "priority": 100 if order["prior_day_deferral"] else 0})
        else:
            deferred_reasons = sorted(reasons[order["order_ref"]])
            if unverified[order["order_ref"]]:
                deferred_reasons.extend(sorted(unverified[order["order_ref"]]))
                deferred_reasons.append("CONSTRAINTS_UNVERIFIED")
            if not deferred_reasons and candidates[order["order_ref"]]:
                deferred_reasons.append("TRIP_RESOURCE_OR_TIME_BUDGET_EXCEEDED")
            if not deferred_reasons:
                deferred_reasons.append("NO_ELIGIBLE_VEHICLE")
            rows.append({"scenario": data.scenario, "order_ref": order["order_ref"],
                         "decision": "deferred", "vehicle_id": None, "trip_id": None,
                         "reasons": sorted(set(deferred_reasons)),
                         "priority": 100 if order["prior_day_deferral"] else 0})
    trips = _build_scenario_trips(data, rows)
    diagnostics = []
    if status_code == cp_model.UNKNOWN:
        diagnostics.append("OPTIMIZER_TIMEOUT_WITHOUT_FEASIBLE_SOLUTION")
    elif status_code == cp_model.FEASIBLE:
        diagnostics.append("OPTIMIZER_TIMEOUT_RETURNED_BEST_FEASIBLE_SOLUTION")
    elif status_code == cp_model.INFEASIBLE:
        diagnostics.append("NO_FEASIBLE_ASSIGNMENT")
    result_status = solver.status_name(status_code)
    if any(not trip["metrics"]["time_windows_valid"] for trip in trips):
        result_status = "VALIDATION_FAILED"
        diagnostics.append("DELIVERY_WINDOW_VALIDATION_FAILED")
    return ScenarioAllocationResult(result_status, tuple(rows), trips, tuple(diagnostics))


def _build_scenario_trips(
    data: PlanningReferenceData,
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Create stable stop sequences, local ETAs, and utilization metrics."""
    orders = {order["order_ref"]: order for order in data.orders}
    vehicles = {vehicle["vehicle_id"]: vehicle for vehicle in data.vehicles}
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for assignment in rows:
        if assignment["decision"] == "served":
            grouped.setdefault((assignment["vehicle_id"], assignment["trip_id"]), []).append(
                orders[assignment["order_ref"]]
            )

    artifacts = []
    colombo = ZoneInfo("Asia/Colombo")
    for (vehicle_id, trip_no), stops in sorted(grouped.items()):
        stops.sort(key=lambda order: (
            order["window_close_time"] or "23:59",
            order["window_open_time"] or "00:00",
            order["order_ref"],
        ))
        brand = stops[0]["brand"]
        district = stops[0]["district"]
        route = data.travel[district]
        service_times = [data.service_allowance[(order["brand"], order["dock_type"])] for order in stops]
        start_at = datetime.combine(data.planning_date, time(3, 30) if brand == "Fresh" else time(8), tzinfo=colombo)
        cursor = start_at
        stop_rows = []
        for index, (order, service_minutes) in enumerate(zip(stops, service_times)):
            cursor += timedelta(minutes=int(route["depot_to_district_freeflow_min"] if index == 0
                                           else route["inter_stop_freeflow_min"]))
            opened = order["window_open_time"]
            if opened:
                open_at = datetime.combine(data.planning_date, time.fromisoformat(opened), tzinfo=colombo)
                cursor = max(cursor, open_at)  # early arrival waits for the receiving window
            close = order["window_close_time"]
            service_end = cursor + timedelta(minutes=service_minutes)
            if close and service_end > datetime.combine(data.planning_date, time.fromisoformat(close), tzinfo=colombo):
                # Keep the candidate explainable; the caller can see this is not
                # safe to publish and the independent validator must reject it.
                stop_window_valid = False
            else:
                stop_window_valid = True
            stop_rows.append({
                "order_ref": order["order_ref"],
                "sequence_number": index + 1,
                "planned_arrival": cursor.isoformat(),
                "planned_service_minutes": service_minutes,
                "window_valid": stop_window_valid,
            })
            cursor = service_end
        vehicle = vehicles[vehicle_id]
        weight = sum(order["weight_kg"] for order in stops)
        volume = sum(order["volume_m3"] for order in stops)
        distance = route["trip_route_km"]
        artifacts.append({
            "vehicle_id": vehicle_id,
            "trip_number": trip_no,
            "brand": brand,
            "district": district,
            "status": "DRAFT",
            "stops": stop_rows,
            "metrics": {
                "weight_kg": weight,
                "volume_m3": volume,
                "weight_utilization_pct": round(100 * weight / vehicle["weight_cap_kg"], 2),
                "volume_utilization_pct": round(100 * volume / vehicle["volume_cap_m3"], 2),
                "distance_km": distance,
                "fuel_liters": round(distance / vehicle["km_per_l"], 3),
                "duration_minutes": round((route["depot_to_district_freeflow_min"]
                                            + (len(stops) - 1) * route["inter_stop_freeflow_min"]
                                            + sum(service_times)), 2),
                "time_windows_valid": all(stop["window_valid"] for stop in stop_rows),
            },
        })
    return tuple(artifacts)


def persist_scenario_allocation(
    db: Session,
    planning_run: PlanningRun,
    result: ScenarioAllocationResult,
) -> PlanVersion:
    """Persist a validated candidate version, its trips, stops, and deferrals atomically."""
    if result.status not in {"OPTIMAL", "FEASIBLE"}:
        raise ValueError(f"cannot persist allocation with solver status {result.status}")
    if any(not trip["metrics"].get("time_windows_valid", False) for trip in result.trips):
        raise ValueError("cannot persist allocation with a delivery-window violation")
    order_refs = [row["order_ref"] for row in result.rows]
    if len(order_refs) != len(set(order_refs)):
        raise ValueError("allocation contains duplicate order decisions")
    trip_keys = {(trip["vehicle_id"], trip["trip_number"]) for trip in result.trips}
    for row in result.rows:
        if row["decision"] not in {"served", "deferred"}:
            raise ValueError(f"invalid allocation decision for {row['order_ref']}")
        if row["decision"] == "served" and (row["vehicle_id"], row["trip_id"]) not in trip_keys:
            raise ValueError(f"served order {row['order_ref']} has no constructed trip")
    served_refs = {row["order_ref"] for row in result.rows if row["decision"] == "served"}
    stop_refs = [stop["order_ref"] for trip in result.trips for stop in trip["stops"]]
    if served_refs != set(stop_refs) or len(stop_refs) != len(set(stop_refs)):
        raise ValueError("allocation trips do not contain each served order exactly once")
    orders = db.scalars(select(Order).where(Order.reference.in_(order_refs))).all() if order_refs else []
    order_by_reference = {order.reference: order for order in orders}
    missing = sorted(set(order_refs) - set(order_by_reference))
    if missing:
        raise ValueError(f"allocation refers to orders absent from the planning database: {missing}")

    latest_version = db.scalar(select(func.max(PlanVersion.version_number)).where(
        PlanVersion.planning_run_id == planning_run.id
    )) or 0
    version = PlanVersion(
        planning_run_id=planning_run.id,
        version_number=latest_version + 1,
        status="DRAFT",
        input_digest=planning_run.snapshot_hash,
    )
    db.add(version)
    db.flush()
    for candidate_trip in result.trips:
        trip = Trip(
            plan_version_id=version.id,
            vehicle_id=candidate_trip["vehicle_id"],
            trip_number=candidate_trip["trip_number"],
            brand=candidate_trip["brand"],
            district=candidate_trip["district"],
            status="DRAFT",
            metrics=candidate_trip["metrics"],
        )
        db.add(trip)
        db.flush()
        for stop in candidate_trip["stops"]:
            planned_local = datetime.fromisoformat(stop["planned_arrival"])
            planned_utc = planned_local.astimezone(ZoneInfo("UTC"))
            db.add(TripStop(
                trip_id=trip.id,
                order_id=order_by_reference[stop["order_ref"]].id,
                sequence_number=stop["sequence_number"],
                planned_arrival=planned_utc,
                planned_service_minutes=stop["planned_service_minutes"],
            ))

    for row in result.rows:
        if row["decision"] == "deferred":
            codes = row["reasons"] or ["LOWER_PRIORITY_THAN_SERVED_SET"]
            db.add(Deferral(
                order_id=order_by_reference[row["order_ref"]].id,
                plan_version_id=version.id,
                reason=codes[0],
                priority=row.get("priority"),
                notes=", ".join(codes),
            ))
    try:
        db.commit()
        db.refresh(version)
    except Exception:
        db.rollback()
        raise
    return version
