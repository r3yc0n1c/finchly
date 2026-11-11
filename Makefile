.PHONY: all setup check format lint typecheck test-unit test test-security test-integration migrate secret-scan openapi schema-export up down logs clean

all: check

setup:
	uv sync
	pnpm --dir apps/web install

format:
	uv run ruff format .
	uv run ruff check --fix .
	pnpm --dir apps/web format

lint:
	uv run ruff check .
	uv run python scripts/lint_docs.py
	uv run python scripts/migration_lint.py
	uv run lint-imports
	pnpm --dir apps/web check

typecheck:
	uv run mypy packages apps/api tests
	pnpm --dir apps/web typecheck

secret-scan:
	uv run detect-secrets scan --baseline .secrets.baseline

test-unit:
	uv run pytest -v
	pnpm --dir apps/web test

test: test-unit

migrate:
	uv run alembic upgrade head

test-security:
	uv run pytest tests/security -v

test-integration:
	uv run pytest tests/contract tests/security -v

check: lint typecheck secret-scan test-unit
	@echo "========================================"
	@echo "All Finchly quality gates passed (OK)."
	@echo "========================================"

openapi:
	uv run python -m finchly_contracts.generator

schema-export:
	uv run python -m finchly_domain.schemas.exporter

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .importlinter_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
