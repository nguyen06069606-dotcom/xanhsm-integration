.RECIPEPREFIX = >
.PHONY: up down restart logs ps psql backup

up:
> docker compose up -d --build

down:
> docker compose down

restart:
> docker compose restart worker monitor dashboard

logs:
> docker compose logs -f --tail=100 worker monitor dashboard

ps:
> docker compose ps

psql:
> docker compose exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

backup:
> mkdir -p backups
> docker compose exec -T postgres sh -c 'pg_dump -U $$POSTGRES_USER $$POSTGRES_DB' | gzip > backups/xanhsm_$$(date +%F_%H%M).sql.gz
> @echo "Đã backup vào thư mục backups/"
