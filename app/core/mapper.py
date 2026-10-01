"""Chuyển JSON của API Xanh SM sang cột trong bảng `trips`.

KHI CÓ API THẬT: đây là file DUY NHẤT cần sửa (cùng với .env).
Chỉ cần đổi các đường dẫn field bên dưới cho khớp tài liệu API.
Toàn bộ JSON gốc luôn được lưu trong cột `payload`, nên không mất dữ liệu.
"""
import hashlib
import json
from datetime import datetime
from typing import Any


def content_hash(raw: dict) -> str:
    canon = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _g(d: dict, *path: str, default: Any = None) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur if cur is not None else default


def _ts(v: Any) -> datetime | None:
    if not v:
        return None
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def map_trip(raw: dict) -> dict:
    """Raise KeyError nếu thiếu ID: bản ghi đó sẽ bị bỏ qua và đếm vào `skipped`."""
    return {
        "external_id": str(raw["trip_id"]),                    # <- field ID duy nhất của chuyến
        "driver_id": _g(raw, "driver", "id"),
        "driver_name": _g(raw, "driver", "name"),
        "vehicle_plate": _g(raw, "vehicle", "plate"),
        "pickup_address": _g(raw, "pickup", "address"),
        "dropoff_address": _g(raw, "dropoff", "address"),
        "distance_km": _g(raw, "distance_km"),
        "fare_vnd": int(_g(raw, "fare", "amount", default=0) or 0),
        "status": str(_g(raw, "status", default="unknown")).lower(),
        "started_at": _ts(_g(raw, "started_at")),
        "completed_at": _ts(_g(raw, "completed_at")),
        "payload": raw,
    }
