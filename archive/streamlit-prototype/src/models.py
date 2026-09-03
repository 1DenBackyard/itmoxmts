from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
import uuid

Doneness = Literal["well_done", "medium", "medium_rare", "rare"]
Status = Literal["open", "in_progress", "fixed", "rejected"]
DocType = Literal["flow", "source", "aggregate_mart"]
ReviewerRole = Literal["analyst", "developer", "qa"]
FindingKind = Literal["content", "missing"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Anchor:
    page: Optional[int] = None
    excerpt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Anchor":
        return cls(page=data.get("page"), excerpt=data.get("excerpt", ""))


@dataclass
class Finding:
    id: str
    doc_id: str
    doc_type: DocType
    reviewer_role: ReviewerRole
    block: str
    problem: str
    guiding_questions: List[str]
    recommendation: str
    probability: float
    impact: float
    score: float
    doneness: Doneness
    traffic_light: str
    status: Status = "open"
    anchor: Anchor = field(default_factory=Anchor)
    agent: str = "mock"
    focus_area: str = ""
    block_id: str = ""
    kind: FindingKind = "content"
    created_at: str = field(default_factory=utc_now_iso)
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Finding":
        anchor = Anchor.from_dict(data.get("anchor") or {})
        return cls(
            id=data["id"],
            doc_id=data["doc_id"],
            doc_type=data["doc_type"],
            reviewer_role=data["reviewer_role"],
            block=data["block"],
            problem=data["problem"],
            guiding_questions=list(data.get("guiding_questions") or []),
            recommendation=data["recommendation"],
            probability=float(data["probability"]),
            impact=float(data["impact"]),
            score=float(data["score"]),
            doneness=data["doneness"],
            traffic_light=data["traffic_light"],
            status=data.get("status", "open"),
            anchor=anchor,
            agent=data.get("agent", "mock"),
            focus_area=data.get("focus_area", ""),
            block_id=data.get("block_id", ""),
            kind=data.get("kind", "content"),
            created_at=data.get("created_at", utc_now_iso()),
            resolved_at=data.get("resolved_at"),
        )


@dataclass
class LearningEvent:
    event_id: str
    user_id: str
    finding_id: str
    block: str
    doneness: Doneness
    score: float
    doc_type: DocType
    focus_area: str
    fixed_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningEvent":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def new_finding_id() -> str:
    return f"f_{uuid.uuid4().hex[:8]}"


def new_event_id() -> str:
    return f"e_{uuid.uuid4().hex[:8]}"
