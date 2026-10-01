import logging
import os
from dataclasses import dataclass


def _e(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    database_url: str = _e("DATABASE_URL")

    api_base_url: str = _e("API_BASE_URL", "http://fake-api:8000").rstrip("/")
    api_auth_mode: str = _e("API_AUTH_MODE", "oauth2").lower()
    api_key: str = _e("API_KEY")
    api_key_header: str = _e("API_KEY_HEADER", "X-API-Key")
    api_token_url: str = _e("API_TOKEN_URL", "/oauth/token")
    api_client_id: str = _e("API_CLIENT_ID")
    api_client_secret: str = _e("API_CLIENT_SECRET")
    api_trips_path: str = _e("API_TRIPS_PATH", "/v1/trips")
    api_data_key: str = _e("API_DATA_KEY", "data")
    api_total_pages_key: str = _e("API_TOTAL_PAGES_KEY", "total_pages")
    api_page_size: int = int(_e("API_PAGE_SIZE", "100"))
    api_timeout: float = float(_e("API_TIMEOUT", "20"))
    api_max_retries: int = int(_e("API_MAX_RETRIES", "5"))

    sync_interval: int = int(_e("SYNC_INTERVAL_SECONDS", "60"))
    sync_overlap_minutes: int = int(_e("SYNC_OVERLAP_MINUTES", "5"))
    initial_sync_from: str = _e("INITIAL_SYNC_FROM", "2024-01-01T00:00:00+00:00")

    monitor_path: str = _e("MONITOR_PATH", "/health")
    monitor_interval: int = int(_e("MONITOR_INTERVAL_SECONDS", "30"))
    monitor_fail_threshold: int = int(_e("MONITOR_FAIL_THRESHOLD", "3"))
    telegram_token: str = _e("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = _e("TELEGRAM_CHAT_ID")

    dashboard_user: str = _e("DASHBOARD_USER", "admin")
    dashboard_password: str = _e("DASHBOARD_PASSWORD")


settings = Settings()


def setup_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
