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
    issues: list[ReviewIssue] = Field(default_factory=list)


class ReviewResult(BaseModel):
    status: str
    issues: list[ReviewIssue]
    warnings: list[str] = Field(default_factory=list)
