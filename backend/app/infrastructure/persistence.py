from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))


class Depot(Base):
    __tablename__ = "depots"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class Outlet(Base):
    __tablename__ = "outlets"
    outlet_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    brand: Mapped[str] = mapped_column(String(16), index=True)
    district: Mapped[str] = mapped_column(String(80), index=True)
    depot_code: Mapped[str] = mapped_column(ForeignKey("depots.code"), index=True)
    dock_type: Mapped[str] = mapped_column(String(32))
    parking_constraint: Mapped[str] = mapped_column(String(32))
    mall_window: Mapped[str | None] = mapped_column(String(80))
    window_open_time: Mapped[str | None] = mapped_column(String(8))
    window_close_time: Mapped[str | None] = mapped_column(String(8))


class Vehicle(Base):
    __tablename__ = "vehicles"
    vehicle_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(16))
    temp: Mapped[str] = mapped_column(String(16))
    weight_cap_kg: Mapped[float] = mapped_column(Float)
    volume_cap_m3: Mapped[float] = mapped_column(Float)
    fuel_type: Mapped[str] = mapped_column(String(24))
    km_per_l: Mapped[float] = mapped_column(Float)
    weekly_fuel_quota_l: Mapped[float] = mapped_column(Float)
    depot_code: Mapped[str] = mapped_column(ForeignKey("depots.code"), index=True)
    __table_args__ = (CheckConstraint("weight_cap_kg > 0"), CheckConstraint("volume_cap_m3 > 0"))


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    outlet_id: Mapped[str | None] = mapped_column(ForeignKey("outlets.outlet_id"))
    depot_code: Mapped[str | None] = mapped_column(ForeignKey("depots.code"))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey("outlets.outlet_id"), index=True)
    requested_delivery_date: Mapped[datetime] = mapped_column(Date, index=True)
    temperature_requirement: Mapped[str] = mapped_column(String(16))
    units: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[float] = mapped_column(Float)
    volume_m3: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("units >= 0"), CheckConstraint("weight_kg >= 0"), CheckConstraint("volume_m3 >= 0"),)


class PlanningRun(Base):
    __tablename__ = "planning_runs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_date: Mapped[datetime] = mapped_column(Date, index=True)
    snapshot_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    runtime_metadata: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanVersion(Base):
    __tablename__ = "plan_versions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    planning_run_id: Mapped[UUID] = mapped_column(ForeignKey("planning_runs.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    input_digest: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("planning_run_id", "version_number"),)


class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    plan_version_id: Mapped[UUID] = mapped_column(ForeignKey("plan_versions.id"), index=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.vehicle_id"), index=True)
    trip_number: Mapped[int] = mapped_column(Integer)
    brand: Mapped[str] = mapped_column(String(16))
    district: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint(
        "plan_version_id", "vehicle_id", "trip_number",
        name="uq_trips_plan_version_vehicle_trip",
    ),)


class TripStop(Base):
    __tablename__ = "trip_stops"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    trip_id: Mapped[UUID] = mapped_column(ForeignKey("trips.id"), index=True)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    planned_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_service_minutes: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("trip_id", "sequence_number"), UniqueConstraint("trip_id", "order_id"))


class Deferral(Base):
    __tablename__ = "deferrals"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"))
    plan_version_id: Mapped[UUID] = mapped_column(ForeignKey("plan_versions.id"))
    reason: Mapped[str] = mapped_column(String(80)); priority: Mapped[int | None] = mapped_column(Integer); notes: Mapped[str | None] = mapped_column(Text)


class ManifestCheck(Base):
    __tablename__ = "manifest_checks"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    trip_id: Mapped[UUID] = mapped_column(ForeignKey("trips.id")); order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id")); expected_quantity: Mapped[int] = mapped_column(Integer); loaded_quantity: Mapped[int] = mapped_column(Integer, default=0); status: Mapped[str] = mapped_column(String(32))


class Shortfall(Base):
    __tablename__ = "shortfalls"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    trip_id: Mapped[UUID | None] = mapped_column(ForeignKey("trips.id"), index=True); order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id")); reason: Mapped[str] = mapped_column(String(80)); quantity: Mapped[int] = mapped_column(Integer); blocking: Mapped[bool] = mapped_column(Boolean); status: Mapped[str] = mapped_column(String(32), index=True); resolution: Mapped[str | None] = mapped_column(Text)


class DeliveryEvent(Base):
    __tablename__ = "delivery_events"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    trip_stop_id: Mapped[UUID] = mapped_column(ForeignKey("trip_stops.id"), index=True); event_type: Mapped[str] = mapped_column(String(64)); occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True)); server_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now()); command_ref: Mapped[str | None] = mapped_column(String(128)); metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)


class ProofOfDelivery(Base):
    __tablename__ = "proofs_of_delivery"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    trip_stop_id: Mapped[UUID] = mapped_column(ForeignKey("trip_stops.id")); delivery_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("delivery_events.id")); receiver_name: Mapped[str | None] = mapped_column(String(120)); outcome: Mapped[str] = mapped_column(String(32)); object_ref: Mapped[str | None] = mapped_column(String(255)); checksum: Mapped[str | None] = mapped_column(String(128)); mime_type: Mapped[str | None] = mapped_column(String(80)); notes: Mapped[str | None] = mapped_column(Text); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Receipt(Base):
    __tablename__ = "receipts"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), unique=True); trip_stop_id: Mapped[UUID | None] = mapped_column(ForeignKey("trip_stops.id")); status: Mapped[str] = mapped_column(String(32)); confirmed_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id")); confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); notes: Mapped[str | None] = mapped_column(Text)


class DeliveryIssue(Base):
    __tablename__ = "delivery_issues"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    receipt_id: Mapped[UUID | None] = mapped_column(ForeignKey("receipts.id")); order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id")); issue_type: Mapped[str] = mapped_column(String(64)); notes: Mapped[str | None] = mapped_column(Text); status: Mapped[str] = mapped_column(String(32)); reported_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id")); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(64), index=True); aggregate_id: Mapped[str] = mapped_column(String(64), index=True); action: Mapped[str] = mapped_column(String(64)); actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id")); old_state: Mapped[dict | None] = mapped_column(JSON); new_state: Mapped[dict | None] = mapped_column(JSON); reason: Mapped[str | None] = mapped_column(Text); correlation_id: Mapped[str | None] = mapped_column(String(128)); metadata_: Mapped[dict | None] = mapped_column("metadata", JSON); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True); command_type: Mapped[str] = mapped_column(String(64)); aggregate_id: Mapped[str | None] = mapped_column(String(64)); request_metadata: Mapped[dict | None] = mapped_column(JSON); result_metadata: Mapped[dict | None] = mapped_column(JSON); status: Mapped[str] = mapped_column(String(32)); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
