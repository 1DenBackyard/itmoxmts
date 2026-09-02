.PHONY: run test lint

run:
	PYTHONPATH=src .venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8501

test:
	PYTHONPATH=src .venv/bin/pytest

lint:
	.venv/bin/ruff check .
