"""Dashboard: xem số liệu chuyến đi, lịch sử sync và sức khỏe API."""
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from core.config import setup_logging, settings
from core.db import ensure_schema, transaction

setup_logging()
if not settings.dashboard_password:
    raise RuntimeError("Chưa đặt DASHBOARD_PASSWORD trong .env")
ensure_schema()

app = FastAPI(title="Xanh SM Dashboard", docs_url=None, redoc_url=None)
security = HTTPBasic()
INDEX = Path(__file__).parent / "templates" / "index.html"


def auth(c: HTTPBasicCredentials = Depends(security)) -> None:
    ok_u = secrets.compare_digest(c.username.encode(), settings.dashboard_user.encode())
    ok_p = secrets.compare_digest(c.password.encode(), settings.dashboard_password.encode())
    if not (ok_u and ok_p):
        raise HTTPException(401, "Sai tài khoản", headers={"WWW-Authenticate": "Basic"})


def rows(sql: str, params: tuple | dict = ()) -> list[dict]:
    with transaction() as conn:
        return conn.execute(sql, params).fetchall()


@app.get("/healthz")
def healthz() -> dict:
    rows("SELECT 1")
    return {"ok": True}


@app.get("/", dependencies=[Depends(auth)])
def index() -> FileResponse:
    return FileResponse(INDEX)


@app.get("/api/overview", dependencies=[Depends(auth)])
def overview() -> dict:
    totals = rows(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE status = 'completed') AS completed,
                  count(*) FILTER (WHERE status = 'cancelled') AS cancelled,
                  count(*) FILTER (WHERE status = 'in_progress') AS in_progress,
                  count(*) FILTER (WHERE started_at >= date_trunc('day', now())) AS today,
                  COALESCE(sum(fare_vnd) FILTER (WHERE status = 'completed'), 0) AS revenue
           FROM trips"""
    )[0]
    daily = rows(
        """SELECT (started_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS day,
                  count(*) AS trips,
                  COALESCE(sum(fare_vnd) FILTER (WHERE status = 'completed'), 0) AS revenue
           FROM trips WHERE started_at >= now() - interval '7 days'
           GROUP BY 1 ORDER BY 1"""
    )
    by_status = rows("SELECT status, count(*) AS n FROM trips GROUP BY status ORDER BY n DESC")
    last_run = rows("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1")
    last_ok = rows("SELECT finished_at FROM sync_runs WHERE status = 'success' ORDER BY id DESC LIMIT 1")
    health = rows("SELECT * FROM api_health ORDER BY id DESC LIMIT 1")
    uptime = rows(
        """SELECT count(*) AS n, count(*) FILTER (WHERE ok) AS ok_n,
                  round(avg(latency_ms) FILTER (WHERE ok)) AS avg_ms
           FROM api_health WHERE checked_at >= now() - interval '24 hours'"""
    )[0]
    return {
        "totals": totals,
        "daily": daily,
        "by_status": by_status,
        "last_run": last_run[0] if last_run else None,
        "last_success": last_ok[0]["finished_at"] if last_ok else None,
        "health": health[0] if health else None,
        "uptime": uptime,
    }


@app.get("/api/trips", dependencies=[Depends(auth)])
def trips(
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    q: str | None = None,
) -> list[dict]:
    where, params = [], {"limit": limit, "offset": offset}
    if status:
        where.append("status = %(status)s")
        params["status"] = status
    if q:
        where.append("(external_id ILIKE %(q)s OR driver_name ILIKE %(q)s OR vehicle_plate ILIKE %(q)s)")
        params["q"] = f"%{q}%"
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return rows(
        f"""SELECT external_id, driver_name, vehicle_plate, pickup_address, dropoff_address,
                   distance_km, fare_vnd, status, started_at, completed_at
            FROM trips {clause} ORDER BY started_at DESC NULLS LAST, id DESC
            LIMIT %(limit)s OFFSET %(offset)s""",
        params,
    )


@app.get("/api/runs", dependencies=[Depends(auth)])
def runs(limit: int = Query(15, ge=1, le=100)) -> list[dict]:
    return rows("SELECT * FROM sync_runs ORDER BY id DESC LIMIT %s", (limit,))


@app.get("/api/health", dependencies=[Depends(auth)])
def health(limit: int = Query(60, ge=1, le=1000)) -> list[dict]:
    return rows("SELECT * FROM api_health ORDER BY id DESC LIMIT %s", (limit,))
