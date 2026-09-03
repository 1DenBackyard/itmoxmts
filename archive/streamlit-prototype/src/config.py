from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
DATA_DIR = ROOT / "data"
DATASET_DIR = PROJECT_ROOT / "ДатасетТЗ"
FINDINGS_PATH = DATA_DIR / "findings_store.json"
EVENTS_PATH = DATA_DIR / "learning_events.json"
LOG_DIR = DATA_DIR / "llm_logs"

load_dotenv(ROOT / ".env")

LLM_MODE = os.getenv("LLM_MODE", "mock").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "local-model")
DEMO_USER_ID = os.getenv("DEMO_USER_ID", "analyst_demo")

DOC_TYPES = {
    "flow": "Описание потоков данных",
    "source": "Описание данных системы-источника",
    "aggregate_mart": "Описание витрины-агрегата",
}

REVIEWER_ROLES = {
    "analyst": "Аналитик",
    "developer": "Разработчик",
    "qa": "Тестировщик",
}

DONENESS_LABELS = {
    "well_done": "Well done",
    "medium": "Medium",
    "medium_rare": "Medium rare",
    "rare": "Rare",
}

DONENESS_EMOJI = {
    "well_done": "🔴",
    "medium": "🟠",
    "medium_rare": "🟡",
    "rare": "🟢",
}

TRAFFIC_BY_DONENESS = {
    "well_done": "red",
    "medium": "orange",
    "medium_rare": "yellow",
    "rare": "green",
}

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
