"""HTTP client gọi API Xanh SM: xác thực, retry, phân trang.

Nếu API thật khác (header, tên tham số, cách phân trang...), chỉnh ở đây
và ở core/mapper.py. Phần còn lại của hệ thống không cần đổi.
"""
import logging
import time
from typing import Iterator

import httpx

from .config import settings as s

log = logging.getLogger(__name__)


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=s.api_base_url, timeout=s.api_timeout)
        self._token: str | None = None
        self._token_exp = 0.0

    # ---------- xác thực ----------
    def _fetch_token(self) -> None:
        r = self.http.post(
            s.api_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": s.api_client_id,
                "client_secret": s.api_client_secret,
            },
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 3600)) - 30

    def headers(self) -> dict[str, str]:
        mode = s.api_auth_mode
        if mode == "bearer":
            return {"Authorization": f"Bearer {s.api_key}"}
        if mode == "header":
            return {s.api_key_header: s.api_key}
        if mode == "oauth2":
            if not self._token or time.time() >= self._token_exp:
                self._fetch_token()
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    # ---------- request có retry ----------
    def request(self, method: str, path: str, **kw) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(1, s.api_max_retries + 1):
            try:
                r = self.http.request(method, path, headers=self.headers(), **kw)
                if r.status_code == 401 and s.api_auth_mode == "oauth2":
                    self._token = None
                    last = ApiError("401 Unauthorized, làm mới token")
                    continue
                if r.status_code == 429 or r.status_code >= 500:
                    last = ApiError(f"HTTP {r.status_code}")
                    log.warning("API lỗi %s (lần %s), thử lại", r.status_code, attempt)
                    time.sleep(min(2**attempt, 30))
                    continue
                r.raise_for_status()
                return r
            except httpx.TransportError as e:
                last = e
                log.warning("Lỗi mạng khi gọi API (lần %s): %s", attempt, e)
                time.sleep(min(2**attempt, 30))
        raise ApiError(f"Gọi API thất bại sau {s.api_max_retries} lần: {last}")

    # ---------- nghiệp vụ ----------
    def iter_trips(self, updated_since: str) -> Iterator[list[dict]]:
        """Trả về từng trang dữ liệu chuyến đi cập nhật sau updated_since."""
        page = 1
        while True:
            r = self.request(
                "GET",
                s.api_trips_path,
                params={
                    "updated_since": updated_since,
                    "page": page,
                    "page_size": s.api_page_size,
                },
            )
            body = r.json()
            if isinstance(body, dict):
                items = body.get(s.api_data_key, [])
                total = body.get(s.api_total_pages_key)
            else:
                items, total = body, None
            if items:
                yield items
            if not items:
                break
            if total is not None and page >= int(total):
                break
            if total is None and len(items) < s.api_page_size:
                break
            page += 1

    def ping(self, path: str) -> tuple[bool, int | None, int, str | None]:
        t = time.perf_counter()
        try:
            r = self.http.get(path, headers=self.headers())
            ms = int((time.perf_counter() - t) * 1000)
            ok = r.status_code < 400
            return ok, r.status_code, ms, None if ok else f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            return False, None, int((time.perf_counter() - t) * 1000), str(e)[:300]
