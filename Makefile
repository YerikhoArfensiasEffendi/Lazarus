.PHONY: setup sync-skills audit-skills libraries test lint build dev-backend dev-frontend

setup:
	uv sync --project backend
	pnpm --dir frontend install
	uv run --project backend lazarus skills sync

sync-skills:
	uv run --project backend lazarus skills sync

audit-skills:
	uv run --project backend lazarus skills audit

libraries:
	uv run --project backend lazarus skills libraries

test:
	uv run --project backend pytest
	pnpm --dir frontend test

lint:
	uv run --project backend ruff check backend
	pnpm --dir frontend typecheck

build:
	pnpm --dir frontend build

dev-backend:
	uv run --project backend lazarus serve --host 127.0.0.1 --port 8000

dev-frontend:
	pnpm --dir frontend dev
