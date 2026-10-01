# Xanh SM Integration

Hệ thống đồng bộ dữ liệu chuyến đi từ API Xanh SM vào PostgreSQL, có dashboard và API monitor.
Hiện chạy với **Fake API**; khi Xanh SM cấp API thật chỉ cần đổi cấu hình, không đổi kiến trúc.

```
Xanh SM API (thật hoặc fake)
        │  httpx + retry + tự làm mới token
        ▼
   worker  ──►  PostgreSQL  ◄──  dashboard (FastAPI)  ◄──  Caddy (HTTPS, tên miền)
                    ▲
   monitor ─────────┘  (ghi độ trễ/uptime, cảnh báo Telegram)
```

| Service | Vai trò |
|---|---|
| `fake-api` | Giả lập API Xanh SM (profile `fake`) |
| `worker` | Đồng bộ định kỳ, incremental theo `updated_since`, upsert không trùng |
| `postgres` | Lưu dữ liệu (volume `pgdata`) |
| `dashboard` | Giao diện thống kê, bảo vệ bằng Basic Auth |
| `monitor` | Kiểm tra API mỗi 30 giây, cảnh báo khi lỗi liên tiếp |
| `caddy` | HTTPS tự động cho dashboard (profile `proxy`) |

## 1. Cài đặt trên Ubuntu

```bash
# Cài Docker (bỏ qua nếu đã có)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

git clone <repo-của-bạn> xanhsm-integration && cd xanhsm-integration
cp .env.example .env
nano .env            # ĐỔI POSTGRES_PASSWORD và DASHBOARD_PASSWORD
make up              # hoặc: docker compose up -d --build
make logs
```

Dashboard: `https://<DASHBOARD_DOMAIN>` (khi bật `proxy`), hoặc đặt `DASHBOARD_BIND=0.0.0.0` rồi vào `http://<IP>:8000`.

**Tên miền:** tạo bản ghi `A` cho `dashboard.sacogroup.vn` trỏ về IP tĩnh của server, mở cổng 80/443 ở firewall
(`sudo ufw allow 80,443/tcp`). Chưa có tên miền thì bỏ `proxy` khỏi `COMPOSE_PROFILES`.

## 2. Chuyển sang API thật (chỉ vài phút)

1. Trong `.env`:
   - `COMPOSE_PROFILES=proxy` (bỏ `fake`)
   - `API_BASE_URL=https://<host-api-xanh-sm>`
   - `API_AUTH_MODE` = `bearer` / `header` / `oauth2` / `none` và điền `API_KEY` hoặc `API_CLIENT_ID/SECRET`, `API_TOKEN_URL`
   - `API_TRIPS_PATH`, `API_DATA_KEY`, `API_TOTAL_PAGES_KEY` khớp tài liệu API
   - `MONITOR_PATH` = endpoint nhẹ để kiểm tra sống/chết
2. Sửa **`app/core/mapper.py`**: đổi đường dẫn field cho khớp JSON thật (ví dụ `trip_id` → `id`).
3. Nếu API dùng tên tham số khác (`updated_since`, `page`...), sửa trong `app/core/client.py` hàm `iter_trips`.
4. `docker compose up -d --build` rồi xem dashboard.

Toàn bộ JSON gốc luôn nằm trong cột `trips.payload`, nên đổi mapper sau này vẫn không mất dữ liệu.

## 3. Cơ chế chống trùng dữ liệu

- `trips.external_id` có ràng buộc **UNIQUE**: DB không bao giờ có hai dòng cùng chuyến đi.
- Ghi bằng `INSERT ... ON CONFLICT (external_id) DO UPDATE ... WHERE content_hash khác`:
  chưa có thì thêm, có và dữ liệu đổi thì cập nhật, không đổi thì bỏ qua (không ghi thừa).
- Mỗi lượt sync lùi cursor `SYNC_OVERLAP_MINUTES` phút để không sót dữ liệu, phần lấy lặp được DB loại tự động.
- Advisory lock đảm bảo không có hai worker sync cùng lúc.
- Trang "Lịch sử đồng bộ" hiển thị số bản ghi mới / cập nhật / không đổi mỗi lượt.

## 4. Vận hành

```bash
make ps            # trạng thái
make logs          # log worker, monitor, dashboard
make restart       # khởi động lại app
make psql          # vào PostgreSQL
make backup        # dump vào ./backups
docker compose pull && make up   # cập nhật image
```

Cập nhật code: `git pull && make up`. Schema tạo tự động khi khởi động (`app/core/schema.sql`, idempotent).
Khi cần đổi cấu trúc bảng, thêm câu lệnh `ALTER TABLE ... IF NOT EXISTS` vào cuối file này.

**Bảo mật:** không commit `.env`; PostgreSQL không mở cổng ra ngoài; dashboard có Basic Auth và nên chạy sau HTTPS.
**Telegram:** điền `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` để nhận cảnh báo khi API lỗi và khi phục hồi.
