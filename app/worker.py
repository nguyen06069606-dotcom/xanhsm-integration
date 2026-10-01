"""Worker: đồng bộ chuyến đi từ API Xanh SM vào PostgreSQL (không trùng lặp)."""
import logging
import signal
import threading
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from core.client import ApiClient
from core.config import setup_logging, settings
from core.db import connect, ensure_schema
from core.mapper import content_hash, map_trip

log = logging.getLogger("worker")
SYNC_LOCK_ID = 727001
CURSOR_KEY = "trips_cursor"

# Chống trùng: UNIQUE(external_id) + ON CONFLICT.
# - Chưa có      -> INSERT                      (inserted)
# - Có, dữ liệu đổi -> UPDATE                   (updated)
# - Có, không đổi   -> bỏ qua, không trả về dòng (unchanged)
UPSERT = """
INSERT INTO trips (external_id, driver_id, driver_name, vehicle_plate, pickup_address,
                   dropoff_address, distance_km, fare_vnd, status, started_at, completed_at,
                   payload, content_hash)
VALUES (%(external_id)s, %(driver_id)s, %(driver_name)s, %(vehicle_plate)s, %(pickup_address)s,
        %(dropoff_address)s, %(distance_km)s, %(fare_vnd)s, %(status)s, %(started_at)s,
        %(completed_at)s, %(payload)s, %(content_hash)s)
ON CONFLICT (external_id) DO UPDATE SET
    driver_id = EXCLUDED.driver_id, driver_name = EXCLUDED.driver_name,
    vehicle_plate = EXCLUDED.vehicle_plate, pickup_address = EXCLUDED.pickup_address,
    dropoff_address = EXCLUDED.dropoff_address, distance_km = EXCLUDED.distance_km,
    fare_vnd = EXCLUDED.fare_vnd, status = EXCLUDED.status, started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at, payload = EXCLUDED.payload,
    content_hash = EXCLUDED.content_hash, updated_at = now()
WHERE trips.content_hash IS DISTINCT FROM EXCLUDED.content_hash
RETURNING (xmax = 0) AS inserted
"""


def upsert_trip(cur, trip: dict) -> str:
    params = {**trip, "payload": Jsonb(trip["payload"]), "content_hash": content_hash(trip["payload"])}
    cur.execute(UPSERT, params)
    row = cur.fetchone()
    if row is None:
        return "unchanged"
    return "inserted" if row["inserted"] else "updated"


def get_cursor(conn) -> str:
    row = conn.execute("SELECT value FROM sync_state WHERE key = %s", (CURSOR_KEY,)).fetchone()
    return row["value"] if row else settings.initial_sync_from


def set_cursor(conn, value: datetime) -> None:
    conn.execute(
        """INSERT INTO sync_state (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
        (CURSOR_KEY, value.isoformat()),
    )


def finish_run(conn, run_id: int, status: str, stats: dict, error: str | None) -> None:
    conn.execute(
        """UPDATE sync_runs SET finished_at = now(), status = %s, fetched = %s, inserted = %s,
           updated = %s, unchanged = %s, skipped = %s, error = %s WHERE id = %s""",
        (status, stats["fetched"], stats["inserted"], stats["updated"],
         stats["unchanged"], stats["skipped"], error, run_id),
    )
    conn.commit()


def run_sync(client: ApiClient) -> None:
    conn = connect()
    try:
        got = conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (SYNC_LOCK_ID,)).fetchone()["ok"]
        if not got:
            log.info("Đang có tiến trình sync khác, bỏ qua lượt này")
            return
        started = datetime.now(timezone.utc)
        run_id = conn.execute("INSERT INTO sync_runs (status) VALUES ('running') RETURNING id").fetchone()["id"]
        conn.commit()
        stats = {"fetched": 0, "inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
        try:
            since = get_cursor(conn)
            log.info("Sync từ %s", since)
            for items in client.iter_trips(since):
                with conn.cursor() as cur:
                    for raw in items:
                        stats["fetched"] += 1
                        try:
                            trip = map_trip(raw)
                        except (KeyError, ValueError, TypeError) as e:
                            stats["skipped"] += 1
                            log.warning("Bỏ qua bản ghi lỗi (%s): %.200s", e, raw)
                            continue
                        stats[upsert_trip(cur, trip)] += 1
                conn.commit()
            set_cursor(conn, started - timedelta(minutes=settings.sync_overlap_minutes))
            conn.commit()
            finish_run(conn, run_id, "success", stats, None)
            log.info("Sync xong: %s", stats)
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            log.exception("Sync thất bại")
            finish_run(conn, run_id, "failed", stats, str(e)[:500])
    finally:
        conn.close()  # đóng kết nối là nhả advisory lock


def main() -> None:
    setup_logging()
    ensure_schema()
    client = ApiClient()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    log.info("Worker khởi động, chu kỳ %ss, API: %s", settings.sync_interval, settings.api_base_url)
    while not stop.is_set():
        try:
            run_sync(client)
        except Exception:  # noqa: BLE001
            log.exception("Lỗi không mong muốn")
        stop.wait(settings.sync_interval)
    log.info("Worker dừng")


if __name__ == "__main__":
    main()
