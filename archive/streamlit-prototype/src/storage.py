from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .config import EVENTS_PATH, FINDINGS_PATH
from .models import Finding, LearningEvent, new_event_id, utc_now_iso


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


class Store:
    """Простое файловое хранилище для handoff бэкенду."""

    def __init__(
        self,
        findings_path: Path = FINDINGS_PATH,
        events_path: Path = EVENTS_PATH,
    ) -> None:
        self.findings_path = findings_path
        self.events_path = events_path

    # --- findings ---
    def load_findings(self, doc_id: Optional[str] = None) -> List[Finding]:
        raw = _read_json(self.findings_path, {"findings": []})
        items = [Finding.from_dict(x) for x in raw.get("findings", [])]
        if doc_id:
            items = [f for f in items if f.doc_id == doc_id]
        return items

    def save_findings(self, findings: List[Finding]) -> None:
        existing = {f.id: f for f in self.load_findings()}
        for f in findings:
            existing[f.id] = f
        _write_json(
            self.findings_path,
            {"findings": [f.to_dict() for f in existing.values()]},
        )

    def replace_doc_findings(self, doc_id: str, findings: List[Finding]) -> None:
        others = [f for f in self.load_findings() if f.doc_id != doc_id]
        _write_json(
            self.findings_path,
            {"findings": [f.to_dict() for f in others + findings]},
        )

    def update_finding_status(
        self,
        finding_id: str,
        status: str,
        user_id: str,
    ) -> Optional[Finding]:
        findings = self.load_findings()
        target = None
        for f in findings:
            if f.id == finding_id:
                prev = f.status
                f.status = status  # type: ignore[assignment]
                if status == "fixed" and prev != "fixed":
                    f.resolved_at = utc_now_iso()
                    self.add_learning_event(f, user_id)
                elif status != "fixed":
                    f.resolved_at = None
                target = f
                break
        if target is not None:
            self.save_findings(findings)
        return target

    # --- learning events ---
    def load_events(self, user_id: Optional[str] = None) -> List[LearningEvent]:
        raw = _read_json(self.events_path, {"events": []})
        items = [LearningEvent.from_dict(x) for x in raw.get("events", [])]
        if user_id:
            items = [e for e in items if e.user_id == user_id]
        return items

    def add_learning_event(self, finding: Finding, user_id: str) -> LearningEvent:
        """В статистику только реально исправленные правки."""
        events = self.load_events()
        # не дублируем одно и то же finding
        for e in events:
            if e.finding_id == finding.id:
                return e
        event = LearningEvent(
            event_id=new_event_id(),
            user_id=user_id,
            finding_id=finding.id,
            block=finding.block,
            doneness=finding.doneness,
            score=finding.score,
            doc_type=finding.doc_type,
            focus_area=finding.focus_area,
        )
        events.append(event)
        _write_json(self.events_path, {"events": [e.to_dict() for e in events]})
        return event

    def dashboard_stats(self, user_id: str) -> Dict:
        events = self.load_events(user_id=user_id)
        by_block: Dict[str, Dict] = {}
        by_doneness: Dict[str, int] = {
            "well_done": 0,
            "medium": 0,
            "medium_rare": 0,
            "rare": 0,
        }
        by_focus: Dict[str, int] = {}
        for e in events:
            by_doneness[e.doneness] = by_doneness.get(e.doneness, 0) + 1
            by_focus[e.focus_area or "other"] = by_focus.get(e.focus_area or "other", 0) + 1
            slot = by_block.setdefault(
                e.block,
                {"block": e.block, "count": 0, "score_sum": 0.0},
            )
            slot["count"] += 1
            slot["score_sum"] += e.score

        ranked = sorted(
            (
                {
                    **v,
                    "avg_score": round(v["score_sum"] / max(v["count"], 1), 3),
                }
                for v in by_block.values()
            ),
            key=lambda x: (x["count"], x["avg_score"]),
            reverse=True,
        )
        return {
            "total_fixed": len(events),
            "by_doneness": by_doneness,
            "by_focus": by_focus,
            "blocks_ranked": ranked,
            "events": events,
        }
