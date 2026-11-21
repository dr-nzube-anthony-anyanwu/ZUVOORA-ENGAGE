"""Database access with RLS always enforced.

The pool connects as `engage_api`, a NOINHERIT role with no table privileges of its own.
`user_transaction` switches to the `engage_app` role and installs the *verified* JWT claims
for the duration of one transaction (SET LOCAL / set_config(..., true)), so every query is
subject to the same row-level-security policies tested in supabase/tests. If the role switch
were ever skipped, queries would fail with permission errors rather than leak data.

`engage_app` is deliberately not Supabase's `authenticated` role: the Data API (PostgREST)
runs as `authenticated`, which has no privileges on Engage tables (ADR-016).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import Settings
from app.security.jwt import Principal


class Database:
    def __init__(self, settings: Settings) -> None:
        if settings.database_url is None:
            raise RuntimeError("DATABASE_URL is not configured")
        self._pool = ConnectionPool(
            conninfo=settings.database_url.get_secret_value(),
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=False,
            name="engage_api",
        )

    def open(self) -> None:
        self._pool.open(wait=True, timeout=15)

    def close(self) -> None:
        self._pool.close()

    def ping(self) -> bool:
        try:
            with self._pool.connection(timeout=3) as conn:
                conn.execute("select 1")
            return True
        except (psycopg.Error, TimeoutError):
            return False

    @contextmanager
    def widget_transaction(
        self, tenant_id: uuid.UUID | None = None, conversation_id: uuid.UUID | None = None
    ) -> Iterator[psycopg.Connection]:
        """One transaction as the anonymous widget visitor (role engage_widget, ADR-025).

        The tenant and conversation come only from verified widget tokens, never from request
        bodies. No user JWT claims are present, so staff policies cannot match.
        """
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("select set_config('request.jwt.claims', '', true)")
            conn.execute(
                "select set_config('request.widget.tenant_id', %s, true), "
                "set_config('request.widget.conversation_id', %s, true)",
                (
                    str(tenant_id) if tenant_id else "",
                    str(conversation_id) if conversation_id else "",
                ),
            )
            conn.execute("set local role engage_widget")
            yield conn

    @contextmanager
    def user_transaction(self, principal: Principal) -> Iterator[psycopg.Connection]:
        """One transaction executed as the authenticated end user under RLS."""
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (json.dumps(principal.claims),),
            )
            conn.execute("set local role engage_app")
            yield conn
