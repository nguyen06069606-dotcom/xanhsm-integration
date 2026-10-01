import logging
import time
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .config import settings

log = logging.getLogger(__name__)
SCHEMA_LOCK_ID = 727000


def connect(retries: int = 30, delay: float = 2.0) -> psycopg.Connection:
    last: Exception | None = None
    for _ in range(retries):
        try:
            return psycopg.connect(settings.database_url, row_factory=dict_row)
        except psycopg.OperationalError as e:
            last = e
            log.warning("Database chưa sẵn sàng, thử lại: %s", e)
            time.sleep(delay)
    raise RuntimeError(f"Không kết nối được database: {last}")


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema() -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    conn = connect()
    try:
        conn.execute("SELECT pg_advisory_lock(%s)", (SCHEMA_LOCK_ID,))
        conn.execute(sql)
        conn.commit()
        conn.execute("SELECT pg_advisory_unlock(%s)", (SCHEMA_LOCK_ID,))
        conn.commit()
        log.info("Schema sẵn sàng")
    finally:
        conn.close()
