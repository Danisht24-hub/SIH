from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from config import Settings, load_settings

if TYPE_CHECKING:
    import psycopg

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(settings: Settings | None = None) -> "psycopg.Connection":
    import psycopg
    from psycopg.rows import dict_row

    settings = settings or load_settings()
    return psycopg.connect(settings.dsn, row_factory=dict_row)


def init_schema(settings: Settings | None = None) -> None:
    settings = settings or load_settings()
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
