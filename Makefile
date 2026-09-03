.PHONY: run test lint

run:
	SESSION_COOKIE_SECURE=false PYTHONPATH=src .venv/bin/uvicorn specguard.web:create_app --factory --host 127.0.0.1 --port 8501

test:
	PYTHONPATH=src .venv/bin/pytest

lint:
	.venv/bin/ruff check .
