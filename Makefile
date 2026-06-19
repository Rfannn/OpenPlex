.PHONY: run test lint format clean docker-build

# ── Development ──────────────────────────────────────────────────────────────

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8185 --reload

run-prod:
	uvicorn app.main:app --host 0.0.0.0 --port 8185 --workers 4

# ── Testing ──────────────────────────────────────────────────────────────────

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=app --cov-report=term-missing

# ── Linting & Formatting ────────────────────────────────────────────────────

lint:
	ruff check app/

lint-fix:
	ruff check app/ --fix

format:
	ruff format app/

# ── Docker ───────────────────────────────────────────────────────────────────

docker-build:
	docker build -t media-server .

docker-run:
	docker compose up -d

docker-stop:
	docker compose down

# ── Cleanup ──────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage

# ── Database ─────────────────────────────────────────────────────────────────

db-migrate:
	alembic upgrade head

db-revision:
	alembic revision --autogenerate -m "$(msg)"
