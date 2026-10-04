from app.modules.planning.eligibility import evaluate_vehicle


def pair():
    return (
        {"weight_kg": 20, "volume_m3": 1, "temperature_requirement": "CHILLED"},
        {"depot_code": "DEPOT-A", "dock_type": "STANDARD", "parking_constraint": "NONE"},
        {"depot_code": "DEPOT-A", "weight_cap_kg": 100, "volume_cap_m3": 4,
         "temperature_capability": "REEFER", "km_per_l": 8, "weekly_fuel_quota_l": 100},
    )


def test_vehicle_eligibility_passes_only_when_all_hard_constraints_are_verified():
    order, outlet, vehicle = pair()
    result = evaluate_vehicle(order, outlet, vehicle, availability_known=True, available=True,
                              access_compatible=True, estimated_trip_km=40)
    assert result.eligible is True
    assert result.reasons == ()
    assert result.unverified == ()


def test_capacity_and_temperature_failures_have_specific_reasons():
    order, outlet, vehicle = pair()
    order.update(weight_kg=101, volume_m3=5, temperature_requirement="FROZEN")
    vehicle["temperature_capability"] = "AMBIENT"
    result = evaluate_vehicle(order, outlet, vehicle, availability_known=True, available=True,
                              access_compatible=True, estimated_trip_km=40)
    assert result.eligible is False
    assert set(result.reasons) == {
        "WEIGHT_CAPACITY_EXCEEDED", "VOLUME_CAPACITY_EXCEEDED", "TEMPERATURE_INCOMPATIBLE"
    }


def test_unavailable_and_wrong_depot_are_rejected():
    order, outlet, vehicle = pair()
    outlet["depot_code"] = "DEPOT-B"
    result = evaluate_vehicle(order, outlet, vehicle, availability_known=True, available=False,
                              access_compatible=True, estimated_trip_km=40)
    assert set(result.reasons) == {"DEPOT_MISMATCH", "VEHICLE_UNAVAILABLE"}


def test_unknown_availability_route_and_windows_are_not_reported_eligible():
    order, outlet, vehicle = pair()
    outlet.update(window_open_time="09:00", window_close_time="12:00", dock_type="RESTRICTED")
    result = evaluate_vehicle(order, outlet, vehicle)
    assert result.eligible is False
    assert result.reasons == ()
    assert set(result.unverified) == {
        "DELIVERY_WINDOW_UNVERIFIED", "TRAVEL_DISTANCE_UNKNOWN",
        "VEHICLE_AVAILABILITY_UNKNOWN",
    }


def test_impossible_delivery_window_and_fuel_quota_have_specific_reasons():
    order, outlet, vehicle = pair()
    outlet.update(window_open_time="09:00", window_close_time="12:00")
    vehicle["weekly_fuel_quota_l"] = 2
    result = evaluate_vehicle(order, outlet, vehicle, availability_known=True, available=True,
                              access_compatible=True, estimated_trip_km=40,
                              estimated_arrival_minutes=13 * 60)
    assert set(result.reasons) == {"FUEL_QUOTA_EXCEEDED", "ARRIVAL_AFTER_DELIVERY_WINDOW"}


def test_published_van_only_rule_accepts_vans_and_rejects_other_vehicle_types():
    order, outlet, vehicle = pair()
    outlet["parking_constraint"] = "van_only"
    vehicle.update(type="truck", temperature_capability="REEFER")
    result = evaluate_vehicle(order, outlet, vehicle, availability_known=True, available=True,
                              estimated_trip_km=40)
    assert "VEHICLE_ACCESS_INCOMPATIBLE" in result.reasons

    vehicle["type"] = "VAN"
    assert evaluate_vehicle(order, outlet, vehicle, availability_known=True, available=True,
                            estimated_trip_km=40).eligible is True


def test_reefer_can_carry_frozen_and_ambient_orders():
    order, outlet, vehicle = pair()
    order["temperature_requirement"] = "FROZEN"
    assert evaluate_vehicle(order, outlet, vehicle, availability_known=True, available=True,
                            estimated_trip_km=40).eligible is True
    order["temperature_requirement"] = "AMBIENT"
    assert evaluate_vehicle(order, outlet, vehicle, availability_known=True, available=True,
                            estimated_trip_km=40).eligible is True
