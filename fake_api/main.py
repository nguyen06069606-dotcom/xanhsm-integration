"""Fake Xanh SM API: mô phỏng API thật để phát triển và test khi chưa có API.

- POST /oauth/token   (client credentials)
- GET  /v1/trips      (updated_since, page, page_size) -> {data, page, total_pages, total}
- GET  /health
Dữ liệu tự sinh liên tục: chuyến mới, chuyến đổi trạng thái. Phân trang + lọc
updated_since khiến các bản ghi được trả LẶP LẠI giữa các lần gọi, đúng để kiểm
tra cơ chế chống trùng của hệ thống.
"""
import os
import random
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query

CLIENT_ID = os.getenv("FAKE_CLIENT_ID", "demo-client")
CLIENT_SECRET = os.getenv("FAKE_CLIENT_SECRET", "demo-secret")
TICK = float(os.getenv("FAKE_TICK_SECONDS", "3"))
ERROR_RATE = float(os.getenv("FAKE_ERROR_RATE", "0"))

LOCK = threading.Lock()
TRIPS: dict[str, dict] = {}
STARTED: dict[str, datetime] = {}
TOKENS: dict[str, float] = {}
SEQ = 0

ADDR = ["Bến Thành, Q.1", "Landmark 81, Bình Thạnh", "Sân bay Tân Sơn Nhất", "Vincom Thảo Điền, TP Thủ Đức",
        "Đại học Bách Khoa, Q.10", "Crescent Mall, Q.7", "Chợ Bình Tây, Q.6", "Aeon Tân Phú",
        "Công viên Gia Định, Phú Nhuận", "Ga Sài Gòn, Q.3", "Phú Mỹ Hưng, Q.7", "Gigamall Phạm Văn Đồng"]
DRIVERS = [("D001", "Nguyễn Văn An"), ("D002", "Trần Minh Khoa"), ("D003", "Lê Quốc Huy"),
           ("D004", "Phạm Thanh Tùng"), ("D005", "Võ Hoàng Nam"), ("D006", "Đặng Thị Lan"),
           ("D007", "Bùi Anh Dũng"), ("D008", "Hoàng Minh Tuấn")]


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if dt else None


def parse(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def make_trip(started: datetime, status: str) -> dict:
    global SEQ
    SEQ += 1
    did, dname = random.choice(DRIVERS)
    pick, drop = random.sample(ADDR, 2)
    dist = round(random.uniform(1.5, 25), 1)
    fare = int(round((12000 + dist * 11500) / 1000) * 1000)
    done = started + timedelta(minutes=max(5, int(dist * 3)))
    tid = f"XSM-{SEQ:06d}"
    trip = {
        "trip_id": tid,
        "driver": {"id": did, "name": dname},
        "vehicle": {"plate": f"51K-{random.randint(100, 999)}.{random.randint(10, 99)}"},
        "pickup": {"address": pick},
        "dropoff": {"address": drop},
        "distance_km": dist,
        "fare": {"amount": 0 if status == "cancelled" else fare, "currency": "VND"},
        "status": status,
        "started_at": iso(started),
        "completed_at": iso(done) if status == "completed" else None,
        "updated_at": iso(done if status != "in_progress" else started),
    }
    TRIPS[tid] = trip
    STARTED[tid] = started
    return trip


def seed() -> None:
    with LOCK:
        for _ in range(300):
            started = now() - timedelta(minutes=random.randint(30, 7 * 24 * 60))
            make_trip(started, "completed" if random.random() < 0.92 else "cancelled")


def ticker() -> None:
    while True:
        time.sleep(TICK)
        with LOCK:
            make_trip(now(), "in_progress")
            for tid, t in TRIPS.items():
                if t["status"] == "in_progress" and (now() - STARTED[tid]).total_seconds() > 20:
                    done = random.random() < 0.92
                    t["status"] = "completed" if done else "cancelled"
                    t["completed_at"] = iso(now()) if done else None
                    if not done:
                        t["fare"]["amount"] = 0
                    t["updated_at"] = iso(now())


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed()
    threading.Thread(target=ticker, daemon=True).start()
    yield


app = FastAPI(title="Fake Xanh SM API", lifespan=lifespan)


def require_token(authorization: str | None = Header(None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    exp = TOKENS.get(authorization[7:])
    if not exp or exp < time.time():
        raise HTTPException(401, "Invalid or expired token")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "time": iso(now())}


@app.post("/oauth/token")
def token(grant_type: str = Form(...), client_id: str = Form(...), client_secret: str = Form(...)) -> dict:
    if grant_type != "client_credentials" or client_id != CLIENT_ID or client_secret != CLIENT_SECRET:
        raise HTTPException(401, "Invalid client")
    tok = secrets.token_urlsafe(32)
    TOKENS[tok] = time.time() + 300  # hết hạn nhanh để test làm mới token
    return {"access_token": tok, "token_type": "Bearer", "expires_in": 300}


@app.get("/v1/trips", dependencies=[Depends(require_token)])
def list_trips(
    updated_since: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> dict:
    if random.random() < ERROR_RATE:
        raise HTTPException(503, "Simulated outage")
    since = iso(parse(updated_since)) if updated_since else "0"
    with LOCK:
        items = sorted((t for t in TRIPS.values() if t["updated_at"] > since),
                       key=lambda t: (t["updated_at"], t["trip_id"]))
        total = len(items)
        start = (page - 1) * page_size
        data = [dict(t, driver=dict(t["driver"]), vehicle=dict(t["vehicle"]), pickup=dict(t["pickup"]),
                     dropoff=dict(t["dropoff"]), fare=dict(t["fare"])) for t in items[start:start + page_size]]
    return {"data": data, "page": page, "total": total, "total_pages": max(1, -(-total // page_size))}
