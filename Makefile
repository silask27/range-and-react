.PHONY: api-install api-dev web-install web-dev demo-seed smoke-test test-api docker-up docker-down db-migrate preflight launch-gate

api-install:
	cd api && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

api-dev:
	cd api && . .venv/bin/activate && uvicorn api.app.main:app --reload --port 8000

web-install:
	cd web && npm install

web-dev:
	cd web && npm run dev

demo-seed:
	cd . && python -m api.scripts.seed_demo_data --reset

smoke-test:
	cd . && python -m api.scripts.smoke_test

test-api:
	cd . && python -m api.scripts.regression_test

launch-gate:
	cd . && python -m api.scripts.smoke_test && python -m api.scripts.regression_test && python -m api.scripts.runtime_preflight

docker-up:
	docker compose up --build

docker-down:
	docker compose down


db-migrate:
	cd . && python -m api.scripts.migrate_sqlite_to_postgres --reset-target


preflight:
	cd . && python -m api.scripts.runtime_preflight
