"""API Monitor: kiểm tra API Xanh SM định kỳ, lưu độ trễ, cảnh báo Telegram."""
import logging
import signal
import threading

import httpx

from core.client import ApiClient
from core.config import setup_logging, settings
from core.db import ensure_schema, transaction

log = logging.getLogger("monitor")


def alert(text: str) -> None:
    if not (settings.telegram_token and settings.telegram_chat_id):
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Gửi Telegram lỗi: %s", e)


def main() -> None:
    setup_logging()
    ensure_schema()
    client = ApiClient()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    fails, down, loops = 0, False, 0
    log.info("Monitor khởi động: %s%s", settings.api_base_url, settings.monitor_path)
    while not stop.is_set():
        ok, code, ms, err = client.ping(settings.monitor_path)
        try:
            with transaction() as conn:
                conn.execute(
                    "INSERT INTO api_health (ok, status_code, latency_ms, error) VALUES (%s,%s,%s,%s)",
                    (ok, code, ms, err),
                )
                loops += 1
                if loops % 120 == 0:  # dọn dữ liệu cũ hơn 30 ngày
                    conn.execute("DELETE FROM api_health WHERE checked_at < now() - interval '30 days'")
        except Exception:  # noqa: BLE001
            log.exception("Ghi api_health lỗi")
        if ok:
            if down:
                alert(f"✅ Xanh SM API đã hoạt động lại ({ms} ms)")
                down = False
            fails = 0
        else:
            fails += 1
            log.warning("API lỗi (%s lần liên tiếp): %s", fails, err)
            if fails >= settings.monitor_fail_threshold and not down:
                alert(f"🚨 Xanh SM API lỗi {fails} lần liên tiếp: {err}")
                down = True
        stop.wait(settings.monitor_interval)


if __name__ == "__main__":
    main()
