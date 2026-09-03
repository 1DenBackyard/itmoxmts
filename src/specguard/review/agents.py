from __future__ import annotations

from abc import ABC, abstractmethod

from .schemas import ReviewIssue


class Reviewer(ABC):
    """Интерфейс ролевого агента ревью. Все реализации — LLM-агенты, см. llm.py."""

    name: str

    @abstractmethod
    def review(self, text: str) -> list[ReviewIssue]:
        raise NotImplementedError
