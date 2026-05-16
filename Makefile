PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
UVICORN ?= .venv/bin/uvicorn

.PHONY: api-install api-dev web-install web-dev demo-seed smoke-test test-api docker-up docker-down db-migrate preflight launch-gate

api-install:
	python3 -m venv .venv && $(PIP) install -r api/requirements.txt

api-dev:
	PYTHONPATH=. $(UVICORN) api.app.main:app --reload --port 8000

web-install:
	cd web && npm install

web-dev:
	cd web && npm run dev

demo-seed:
	PYTHONPATH=. $(PYTHON) -m api.scripts.seed_demo_data --reset

smoke-test:
	PYTHONPATH=. $(PYTHON) -m api.scripts.smoke_test

test-api:
	PYTHONPATH=. $(PYTHON) -m api.scripts.regression_test

launch-gate:
	PYTHONPATH=. $(PYTHON) -m api.scripts.smoke_test && PYTHONPATH=. $(PYTHON) -m api.scripts.regression_test && PYTHONPATH=. $(PYTHON) -m api.scripts.runtime_preflight

docker-up:
	docker compose up --build

docker-down:
	docker compose down


db-migrate:
	PYTHONPATH=. $(PYTHON) -m api.scripts.migrate_sqlite_to_postgres --reset-target


preflight:
	PYTHONPATH=. $(PYTHON) -m api.scripts.runtime_preflight
