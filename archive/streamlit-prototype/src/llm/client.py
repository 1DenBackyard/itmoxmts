"""Абстракция LLM — бэкенд/ML может подменить endpoint без переписывания UI."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..config import (
    LLM_MODE,
    LOG_DIR,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)


class LLMClient:
    def __init__(self, mode: Optional[str] = None) -> None:
        self.mode = (mode or LLM_MODE or "mock").lower()
        self.last_error: Optional[str] = None
        self.demo_mode = self.mode == "mock"

    def available(self) -> bool:
        if self.mode == "mock":
            return False
        try:
            _ = self.complete("ping", system="Reply with OK only.", max_tokens=8)
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.demo_mode = True
            return False

    def complete(
        self,
        prompt: str,
        system: str = "You are a helpful assistant.",
        max_tokens: int = 800,
    ) -> str:
        if self.mode == "mock":
            self.demo_mode = True
            return ""
        if self.mode == "ollama":
            text = self._ollama(prompt, system, max_tokens)
        elif self.mode == "openai_compatible":
            text = self._openai(prompt, system, max_tokens)
        else:
            self.demo_mode = True
            return ""
        self._log({"mode": self.mode, "system": system, "prompt": prompt, "response": text})
        return text

    def _ollama(self, prompt: str, system: str, max_tokens: int) -> str:
        payload = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "options": {"num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        data = self._post_json(f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat", payload)
        return (data.get("message") or {}).get("content", "")

    def _openai(self, prompt: str, system: str, max_tokens: int) -> str:
        payload = {
            "model": OPENAI_MODEL,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
        data = self._post_json(
            f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
            payload,
            headers=headers,
        )
        choices = data.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content", "")

    def _post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers=headers or {"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            self.last_error = str(exc)
            self.demo_mode = True
            raise

    def _log(self, payload: Dict[str, Any]) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = LOG_DIR / f"llm_{stamp}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def try_llm_enrichment(client: LLMClient, text: str, findings_summary: str) -> str:
    """Опциональный комментарий модели поверх mock-анализа."""
    if client.mode == "mock":
        return ""
    system = (
        "Ты — senior data analyst МТС. Кратко (3–5 пунктов) дополни ревью "
        "документации витрины/потока. Пиши по-русски."
    )
    prompt = (
        f"Краткое резюме найденных замечаний:\n{findings_summary}\n\n"
        f"Фрагмент документа:\n{text[:3500]}\n\n"
        "Дай короткий executive summary."
    )
    try:
        return client.complete(prompt, system=system, max_tokens=400).strip()
    except Exception:  # noqa: BLE001
        return ""
