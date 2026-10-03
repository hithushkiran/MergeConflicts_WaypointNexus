"""Run with FND03_POSTGRES_TEST_URL against an isolated PostgreSQL database."""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


URL = os.getenv("FND03_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires isolated PostgreSQL via FND03_POSTGRES_TEST_URL")


def test_seeded_counts_and_uniqueness():
    engine = create_engine(URL)
    with engine.connect() as connection:
        counts = {table: connection.execute(text(f"select count(*) from {table}")).scalar() for table in ("roles", "depots", "outlets", "vehicles", "users", "orders", "planning_runs")}
        assert counts == {"roles": 4, "depots": 2, "outlets": 120, "vehicles": 60, "users": 4, "orders": 4, "planning_runs": 1}
        with pytest.raises(IntegrityError):
            connection.execute(text("insert into outlets (outlet_id, brand, district, depot_code, dock_type, parking_constraint) values ('OUT001','FRESH','x','Peliyagoda','x','x')"))
            connection.commit()
        connection.rollback()
        with pytest.raises(IntegrityError):
            connection.execute(text("insert into idempotency_records (id, key, command_type, status) values ('00000000-0000-0000-0000-000000000001', 'same-key', 'x', 'x'), ('00000000-0000-0000-0000-000000000002', 'same-key', 'x', 'x')"))
            connection.commit()
