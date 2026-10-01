-- Idempotent: chạy lại bao nhiêu lần cũng an toàn.
CREATE TABLE IF NOT EXISTS trips (
    id             BIGSERIAL PRIMARY KEY,
    external_id    TEXT        NOT NULL UNIQUE,   -- ID bên Xanh SM: chặn trùng ở mức DB
    driver_id      TEXT,
    driver_name    TEXT,
    vehicle_plate  TEXT,
    pickup_address TEXT,
    dropoff_address TEXT,
    distance_km    NUMERIC(10,2),
    fare_vnd       BIGINT,
    status         TEXT,
    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    payload        JSONB       NOT NULL,          -- dữ liệu gốc nguyên vẹn từ API
    content_hash   TEXT        NOT NULL,          -- hash payload: bỏ qua ghi nếu không đổi
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_trips_started_at ON trips (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_trips_status     ON trips (status);

CREATE TABLE IF NOT EXISTS sync_state (
    key        TEXT PRIMARY KEY,
    value      TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id          BIGSERIAL PRIMARY KEY,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status      TEXT        NOT NULL,
    fetched     INT NOT NULL DEFAULT 0,
    inserted    INT NOT NULL DEFAULT 0,
    updated     INT NOT NULL DEFAULT 0,
    unchanged   INT NOT NULL DEFAULT 0,
    skipped     INT NOT NULL DEFAULT 0,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS api_health (
    id          BIGSERIAL PRIMARY KEY,
    checked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ok          BOOLEAN     NOT NULL,
    status_code INT,
    latency_ms  INT,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_health_checked_at ON api_health (checked_at DESC);
