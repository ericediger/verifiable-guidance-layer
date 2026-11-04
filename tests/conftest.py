"""Test configuration.

Three flags control how the probabilistic stages run:

    (default)   replay  — serve recorded model responses; deterministic; no network
    --live              — call the real APIs
    --record            — call the real APIs and save every response as a fixture
    --repeat N          — in live mode, run each gold question N times and report a rate

The database is seeded to Release 1 once per session. Tests that change the graph
(publishing a release) do so inside a transaction that is rolled back, so every test
sees Release 1 unless it builds on top of it deliberately.
"""

from __future__ import annotations

import os
import warnings

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--live", action="store_true", help="call the real model APIs")
    parser.addoption("--record", action="store_true", help="call the real APIs and record fixtures")
    parser.addoption("--repeat", type=int, default=1, help="repetitions per gold question in live mode")


def pytest_configure(config: pytest.Config) -> None:
    # Must happen before any `vgl` import, because settings are read at import time.
    _use_test_database()
    if config.getoption("--record"):
        os.environ["VGL_LLM_MODE"] = "record"
    elif config.getoption("--live"):
        os.environ["VGL_LLM_MODE"] = "live"
    else:
        os.environ["VGL_LLM_MODE"] = "replay"


def _use_test_database() -> None:
    """Point the suite at <database>_test so a test run never resets the demo database."""
    import psycopg

    base = os.environ.get("DATABASE_URL", "postgresql://vgl:vgl@localhost:5432/vgl")
    if base.endswith("_test"):
        return
    test_url = base + "_test"
    dbname = test_url.rsplit("/", 1)[1]
    admin = psycopg.connect(base, autocommit=True)
    try:
        if not admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone():
            admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        admin.close()
    os.environ["DATABASE_URL"] = test_url


@pytest.fixture(scope="session")
def repeat(request: pytest.FixtureRequest) -> int:
    return request.config.getoption("--repeat") if os.environ.get("VGL_LLM_MODE") != "replay" else 1


@pytest.fixture(scope="session")
def seeded_db() -> bool:
    """Seed Release 1 once. Returns whether embeddings are available."""
    from vgl import db
    from vgl.llm import FixtureMissing
    from vgl.seed import seed

    with db.connection() as conn:
        seed(conn, embed=False, quiet=True)
    embedded = False
    try:
        from vgl.seed import embed_missing

        with db.connection() as conn:
            embed_missing(conn)
        embedded = True
    except FixtureMissing as e:
        warnings.warn(f"embeddings unavailable in replay mode ({e}); search-dependent evals will skip")
    except RuntimeError as e:
        warnings.warn(f"embeddings unavailable ({e}); search-dependent evals will skip")
    return embedded


@pytest.fixture
def conn(seeded_db):
    """A connection that rolls back everything a test did."""
    from vgl import db

    c = db.connect()
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture
def embedded(seeded_db) -> None:
    if not seeded_db:
        pytest.skip("no embeddings recorded; run `pytest --record` once with API keys")
