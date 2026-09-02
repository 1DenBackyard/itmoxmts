from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    demo_password: str
    llm_enabled: bool
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    max_document_chars: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/specguard.db"),
        demo_password=os.getenv("DEMO_PASSWORD", "demo1234"),
        llm_enabled=_as_bool(os.getenv("LLM_ENABLED")),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://foundation-models.api.cloud.ru/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "ai-sage/GigaChat3-10B-A1.8B"),
        max_document_chars=int(os.getenv("MAX_DOCUMENT_CHARS", "120000")),
    )
