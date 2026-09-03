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
    llm_fallback_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 0
    document_storage_backend: str = "local"
    document_storage_path: str = "data/documents"
    s3_endpoint_url: str = "https://s3.cloud.ru"
    s3_region: str = "ru-central-1"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_prefix: str = "documents"
    s3_server_side_encryption: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/specguard.db"),
        demo_password=os.getenv("DEMO_PASSWORD", "demo1234"),
        llm_enabled=_as_bool(os.getenv("LLM_ENABLED")),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://foundation-models.api.cloud.ru/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "zai-org/GLM-5.1"),
        max_document_chars=int(os.getenv("MAX_DOCUMENT_CHARS", "120000")),
        llm_fallback_model=os.getenv("LLM_FALLBACK_MODEL", "openai/gpt-oss-120b"),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "0")),
        document_storage_backend=os.getenv("DOCUMENT_STORAGE_BACKEND", "local"),
        document_storage_path=os.getenv("DOCUMENT_STORAGE_PATH", "data/documents"),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", "https://s3.cloud.ru"),
        s3_region=os.getenv("S3_REGION", "ru-central-1"),
        s3_bucket=os.getenv("S3_BUCKET", ""),
        s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID", ""),
        s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY", ""),
        s3_prefix=os.getenv("S3_PREFIX", "documents"),
        s3_server_side_encryption=os.getenv("S3_SERVER_SIDE_ENCRYPTION", ""),
    )
