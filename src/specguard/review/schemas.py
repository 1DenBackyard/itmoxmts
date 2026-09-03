from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


class Evidence(BaseModel):
    section: str = "Документ"
    quote: str = Field(min_length=1, max_length=1200)


class ReviewIssue(BaseModel):
    agent: str
    category: str
    severity: Severity
    title: str
    evidence: list[Evidence] = Field(min_length=1)
    problem: str
    impact: str
    question: str
    recommendation: str
    confidence: float = Field(ge=0, le=1)


class AgentResponse(BaseModel):
    issues: list[ReviewIssue]


class Verdict(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class CriticVerdict(BaseModel):
    """Решение агента-критика по одному замечанию ролевого агента."""

    issue_id: str
    verdict: Verdict
    reason: str
    confidence: float = Field(ge=0, le=1)


class CriticResponse(BaseModel):
    verdicts: list[CriticVerdict]


class JudgeDecision(BaseModel):
    """Решение агента-судьи: оставить, объединить с дублем, переоценить severity."""

    issue_id: str
    keep: bool
    severity: Severity
    duplicate_of: str = ""
    reason: str = ""


class JudgeResponse(BaseModel):
    decisions: list[JudgeDecision]


class ReviewResult(BaseModel):
    status: str
    issues: list[ReviewIssue]
    warnings: list[str] = Field(default_factory=list)
