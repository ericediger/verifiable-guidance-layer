"""Database access.

One place that knows how to open a connection, create the schema, and wipe it. Every
other module receives a connection and runs plain SQL against it.

Why plain SQL and not an ORM: the recursive closure query is the heart of the system
and it should be readable as SQL by anyone who asks "show me how you traverse the
graph". An ORM would hide exactly the thing we want to show.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from vgl.config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(database_url: str | None = None) -> psycopg.Connection:
    """Open a connection that returns rows as dicts and understands pgvector."""
    conn = psycopg.connect(database_url or settings.database_url, row_factory=dict_row)
    # The vector type only exists after CREATE EXTENSION; tolerate a fresh database.
    try:
        register_vector(conn)
    except psycopg.ProgrammingError:
        conn.rollback()
    return conn


@contextmanager
def connection(database_url: str | None = None) -> Iterator[psycopg.Connection]:
    conn = connect(database_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(conn: psycopg.Connection) -> None:
    """Create all tables (idempotent)."""
    conn.execute(SCHEMA_PATH.read_text())
    conn.commit()
    register_vector(conn)


def drop_schema(conn: psycopg.Connection) -> None:
    """Drop every table so the seed can start from nothing. Development only."""
    conn.execute(
        """
        DROP TABLE IF EXISTS issued_answers, answers, proposals, chunks, edges, nodes,
            concepts, adoptions, documents, jurisdictions, releases CASCADE
        """
    )
    conn.commit()
