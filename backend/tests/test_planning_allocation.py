from app.modules.planning.allocation import allocate_orders


def fixture():
    orders = [
        {"id": "o1", "reference": "ORD-1", "outlet_id": "x", "weight_kg": 60,
         "volume_m3": 2, "temperature_requirement": "AMBIENT"},
        {"id": "o2", "reference": "ORD-2", "outlet_id": "x", "weight_kg": 50,
         "volume_m3": 1, "temperature_requirement": "AMBIENT"},
    ]
    outlets = {"x": {"depot_code": "D", "dock_type": "STANDARD", "parking_constraint": "NONE"}}
    vehicles = [{"vehicle_id": "v1", "depot_code": "D", "weight_cap_kg": 100,
                 "volume_cap_m3": 4, "temperature_capability": "AMBIENT", "km_per_l": 10,
                 "weekly_fuel_quota_l": 100}]
    evidence = {
        (order["id"], "v1"): {"availability_known": True, "available": True,
                              "access_compatible": True, "estimated_trip_km": 20}
        for order in orders
    }
    return orders, outlets, vehicles, evidence


def test_allocator_respects_combined_vehicle_capacity_and_defers_excess_order():
    orders, outlets, vehicles, evidence = fixture()
    result = allocate_orders(orders, outlets, vehicles, evidence)
    assert result.status == "OPTIMAL"
    assert len(result.assignments) == 1
    assert result.assignments[0]["order_id"] == "o1"
    assert result.deferred == ({"order_id": "o2", "reasons": ["AGGREGATE_WEIGHT_CAPACITY_EXCEEDED"]},)


def test_allocator_never_assigns_pair_with_unverified_constraints():
    orders, outlets, vehicles, _ = fixture()
    result = allocate_orders(orders, outlets, vehicles, {})
    assert result.assignments == ()
    assert all("CONSTRAINTS_UNVERIFIED" in item["reasons"] for item in result.deferred)
    assert all("VEHICLE_AVAILABILITY_UNKNOWN" in item["reasons"] for item in result.deferred)


def test_allocator_output_is_deterministic():
    orders, outlets, vehicles, evidence = fixture()
    first = allocate_orders(orders, outlets, vehicles, evidence)
    second = allocate_orders(list(reversed(orders)), outlets, vehicles, evidence)
    assert first == second
