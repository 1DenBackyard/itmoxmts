from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..llm.client import LLMClient, try_llm_enrichment
from ..models import Finding
from .blocks import DocBlock, parse_document_blocks
from .checklist import (
    build_content_hits,
    build_missing_block_hits,
    hits_to_findings,
    make_doc_id,
)


@dataclass
class AnalysisResult:
    doc_id: str
    findings: List[Finding]
    blocks: List[DocBlock]
    demo_mode: bool
    llm_summary: str = ""
    agents_used: Optional[List[str]] = None


def analyze_document(
    *,
    filename: str,
    raw: bytes,
    text: str,
    doc_type: str,
    reviewer_role: str,
    llm: Optional[LLMClient] = None,
) -> AnalysisResult:
    """Оркестратор: нарезка по эталонным блокам + ревью."""
    client = llm or LLMClient()
    doc_id = make_doc_id(filename, raw)
    blocks = parse_document_blocks(text, doc_type=doc_type)
    hits = build_missing_block_hits(blocks, doc_type) + build_content_hits(blocks, doc_type)
    findings = hits_to_findings(
        hits,
        blocks,
        doc_id=doc_id,
        doc_type=doc_type,
        reviewer_role=reviewer_role,
    )
    agents = sorted({f.agent for f in findings})
    summary_lines = [f"- [{f.doneness}] {f.block}: {f.problem}" for f in findings[:8]]
    llm_summary = try_llm_enrichment(client, text, "\n".join(summary_lines))
    return AnalysisResult(
        doc_id=doc_id,
        findings=findings,
        blocks=blocks,
        demo_mode=client.demo_mode or client.mode == "mock",
        llm_summary=llm_summary,
        agents_used=agents,
    )
