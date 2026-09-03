from __future__ import annotations

import html
import re
from typing import Dict, List, Optional, Sequence, Tuple

import streamlit as st

from src.config import DONENESS_EMOJI, DONENESS_LABELS
from src.models import Finding


FOCUS_LABELS = {
    "sources_kafka": "Источники / Kafka",
    "fields_logic": "Поля и расчёт",
    "filtering": "Фильтрация",
    "refresh_volume": "Обновление / объём",
    "template": "Шаблон / полнота",
    "other": "Прочее",
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        /* --- убираем «белую шапку» Streamlit --- */
        header[data-testid="stHeader"] {
          background: transparent !important;
          height: 0 !important;
          min-height: 0 !important;
        }
        header[data-testid="stHeader"] * { display: none !important; }
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        .stAppDeployButton,
        #MainMenu,
        footer { display: none !important; visibility: hidden !important; }

        .block-container {
          padding-top: 0.4rem !important;
          padding-bottom: 0.4rem !important;
          padding-left: 0.8rem !important;
          padding-right: 0.8rem !important;
          max-width: 100% !important;
        }
        section.main > div { padding-top: 0 !important; }
        div[data-testid="stVerticalBlock"] { gap: 0.25rem !important; }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.4rem !important; }

        /* компактные кнопки в основной зоне (замечания) */
        .main .stButton > button {
          min-height: 26px !important;
          height: 26px !important;
          padding: 0 8px !important;
          font-size: 11px !important;
          font-weight: 500 !important;
          border-radius: 4px !important;
          line-height: 1 !important;
        }
        .main .stButton > button p { font-size: 11px !important; }

        /* кнопки в сайдбаре чуть крупнее, но всё равно компактные */
        [data-testid="stSidebar"] .stButton > button {
          min-height: 32px !important;
          height: 32px !important;
          padding: 0 10px !important;
          font-size: 13px !important;
        }

        .workspace {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 300px;
          border: 1px solid #c9cdd3;
          background: #dfe1e6;
          min-height: calc(100vh - 28px);
        }
        .doc-paper {
          background: #fff;
          margin: 0;
          padding: 22px 34px 32px 34px;
          border-right: 1px solid #c9cdd3;
          font-family: "Times New Roman", Times, Georgia, serif;
          font-size: 14.5px;
          line-height: 1.32;
          color: #111;
          height: calc(100vh - 28px);
          overflow-y: auto;
        }
        .doc-paper h1.doc-title {
          font-size: 16px;
          margin: 0 0 10px 0;
          font-family: Calibri, "Segoe UI", sans-serif;
          border-bottom: 1px solid #ddd;
          padding-bottom: 6px;
          color: #222;
          font-weight: 600;
        }
        .doc-section { margin: 0 0 10px 0; }
        .doc-section h2 {
          font-size: 13.5px;
          margin: 12px 0 4px 0;
          font-family: Calibri, "Segoe UI", sans-serif;
          color: #1f4e79;
          font-weight: 700;
        }
        .doc-section .body {
          white-space: pre-wrap;
          font-family: "Times New Roman", Times, Georgia, serif;
        }
        .doc-section.missing .body {
          color: #9b1c1c;
          font-style: italic;
          font-family: Calibri, "Segoe UI", sans-serif;
          font-size: 12.5px;
        }
        .doc-section.optional-missing { opacity: 0.5; }
        mark.cmt {
          background: #ffe599;
          color: inherit;
          padding: 0 1px;
          border-bottom: 2px solid #f4b400;
        }
        sup.cmt-num {
          font-family: Calibri, "Segoe UI", sans-serif;
          font-size: 9px;
          color: #c5221f;
          font-weight: 700;
          margin-left: 1px;
        }

        .comments-head {
          font-family: Calibri, "Segoe UI", sans-serif;
          font-size: 12px;
          font-weight: 700;
          color: #444;
          padding: 2px 0 6px 2px;
          border-bottom: 1px solid #ddd;
          margin-bottom: 6px;
        }
        .word-comment {
          background: #fff;
          border: 1px solid #dadce0;
          border-left: 3px solid #f4b400;
          border-radius: 2px;
          padding: 6px 8px 5px 8px;
          margin: 0 0 4px 0;
          font-family: Calibri, "Segoe UI", sans-serif;
          font-size: 12px;
          line-height: 1.3;
        }
        .word-comment.red { border-left-color: #d93025; }
        .word-comment.orange { border-left-color: #f4b400; }
        .word-comment.yellow { border-left-color: #fdd663; }
        .word-comment.green { border-left-color: #188038; }
        .word-comment.done { opacity: 0.5; }
        .word-comment .meta {
          color: #5f6368;
          font-size: 10.5px;
          margin-bottom: 2px;
        }
        .word-comment .num {
          display: inline-block;
          min-width: 16px;
          height: 16px;
          line-height: 16px;
          text-align: center;
          border-radius: 8px;
          background: #c5221f;
          color: #fff;
          font-size: 9px;
          font-weight: 700;
          margin-right: 3px;
        }
        .word-comment details {
          margin-top: 3px;
          color: #555;
          font-size: 11px;
        }
        .word-comment summary {
          cursor: pointer;
          color: #1a73e8;
          font-size: 11px;
          list-style: none;
        }
        .word-comment summary::-webkit-details-marker { display: none; }
        .doneness-pill {
            display: inline-block;
            padding: 0 5px;
            border-radius: 7px;
            font-weight: 600;
            font-size: 10px;
        }
        .doneness-well_done { background: #fde2e1; color: #8b0000; }
        .doneness-medium { background: #ffe8cc; color: #9a3412; }
        .doneness-medium_rare { background: #fef3c7; color: #92400e; }
        .doneness-rare { background: #dcfce7; color: #166534; }

        /* правая колонка — серый фон как у Word comments pane */
        [data-testid="stHorizontalBlock"] > div:nth-child(2) {
          background: #eceff3;
          padding: 6px 8px 10px 8px !important;
          border: 1px solid #c9cdd3;
          border-left: none;
          max-height: calc(100vh - 28px);
          overflow-y: auto;
        }
        [data-testid="stHorizontalBlock"] > div:nth-child(1) {
          padding: 0 !important;
          border: 1px solid #c9cdd3;
          max-height: calc(100vh - 28px);
          overflow: hidden;
        }

        /* сайдбар плотнее */
        [data-testid="stSidebar"] .block-container { padding-top: 0.8rem !important; }
        .sidebar-file {
          font-size: 12px;
          color: #333;
          word-break: break-all;
          margin: 0.2rem 0 0.5rem 0;
        }
        .sidebar-stat {
          font-size: 12px;
          color: #555;
          margin: 0.25rem 0 0.5rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def count_by_doneness(findings: List[Finding]) -> Dict[str, int]:
    out = {k: 0 for k in DONENESS_LABELS}
    for f in findings:
        out[f.doneness] = out.get(f.doneness, 0) + 1
    return out


def render_doneness_counters(findings: List[Finding]) -> None:
    counts = count_by_doneness(findings)
    cols = st.columns(4)
    order = ["well_done", "medium", "medium_rare", "rare"]
    for col, key in zip(cols, order):
        with col:
            st.metric(
                f"{DONENESS_EMOJI[key]} {DONENESS_LABELS[key]}",
                counts.get(key, 0),
            )


def _mark_quote(escaped_text: str, quote: str, marker_no: int) -> Tuple[str, bool]:
    if not quote:
        return escaped_text, False
    q = quote.strip().strip("…").strip()
    if len(q) < 4:
        return escaped_text, False

    repl_tpl = (
        '<mark class="cmt" id="cmt-{no}">{txt}</mark>'
        '<sup class="cmt-num">[{no}]</sup>'
    )

    candidates = []
    candidates.append(q)
    candidates.append(re.sub(r"\s+", " ", q).strip())
    if len(q) > 40:
        candidates.append(q[-60:])
        candidates.append(q[20:90])
    for m in re.finditer(r"[A-Za-zА-Яа-я_:][^.]{6,50}", q):
        candidates.append(m.group(0).strip())
    for token in (
        "Кластер: CLUSTER",
        "CLUSTER",
        "substring(imei, 1, 8)",
        "если lac = 0",
        "fallback",
        "без upsert",
        "полная перезагрузка",
        "FIELD_BIZ_DATE",
        "Шаг 1",
    ):
        if token.lower() in q.lower():
            candidates.append(token)

    seen = set()
    ordered = []
    for c in candidates:
        c2 = c.strip()
        if len(c2) < 4:
            continue
        key = c2.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(c2)
    ordered.sort(key=len, reverse=True)

    for cand in ordered:
        eq = html.escape(cand)
        pattern = re.compile(re.escape(eq), re.IGNORECASE)

        def _sub(m, no=marker_no):
            return repl_tpl.format(no=no, txt=m.group(0))

        new_text, n = pattern.subn(_sub, escaped_text, count=1)
        if n:
            return new_text, True
    return escaped_text, False


def build_document_html(
    blocks: Sequence,
    findings: Sequence[Finding],
    filename: str,
    show_optional_missing: bool = False,
) -> Tuple[str, List[Finding]]:
    open_or_all = [f for f in findings if f.status == "open"]
    ordered: List[Finding] = []
    by_block: Dict[str, List[Finding]] = {}
    for f in open_or_all:
        by_block.setdefault(f.block_id, []).append(f)
    for b in blocks:
        items = sorted(by_block.get(b.id, []), key=lambda x: -x.score)
        ordered.extend(items)

    marker_of = {f.id: i + 1 for i, f in enumerate(ordered)}

    parts = [
        f'<div class="doc-paper"><h1 class="doc-title">{html.escape(filename)}</h1>'
    ]
    for b in blocks:
        if not b.present and not b.important and not show_optional_missing:
            continue
        cls = "doc-section"
        if not b.present:
            cls += " missing" + ("" if b.important else " optional-missing")
        parts.append(f'<div class="{cls}">')
        parts.append(f"<h2>{html.escape(b.title)}</h2>")
        if not b.present:
            msg = (
                "Отсутствует информация в важном блоке."
                if b.important
                else "Раздел не заполнен (необязателен для этого типа ТЗ)."
            )
            miss = [f for f in by_block.get(b.id, []) if f.kind == "missing" and f.status == "open"]
            marks = "".join(
                f'<sup class="cmt-num">[{marker_of[f.id]}]</sup>' for f in miss if f.id in marker_of
            )
            parts.append(f'<div class="body">{msg}{marks}</div>')
        else:
            body = html.escape(b.content if b.content != "—" else "")
            for f in by_block.get(b.id, []):
                if f.status != "open" or f.kind == "missing":
                    continue
                no = marker_of.get(f.id)
                if not no:
                    continue
                body, _ = _mark_quote(body, f.anchor.excerpt if f.anchor else "", no)
            parts.append(f'<div class="body">{body}</div>')
        parts.append("</div>")
    parts.append("</div>")
    return "".join(parts), ordered


def render_word_comment(finding: Finding, marker_no: int, key_prefix: str) -> Optional[str]:
    """Компактный Word-like комментарий. Возвращает action."""
    color = {
        "red": "red",
        "orange": "orange",
        "yellow": "yellow",
        "green": "green",
    }.get(finding.traffic_light, "orange")
    done = finding.status in ("fixed", "rejected")
    done_cls = " done" if done else ""
    status = {"open": "открыто", "fixed": "принято", "rejected": "отклонено"}.get(
        finding.status, finding.status
    )

    questions = "".join(f"<li>{html.escape(q)}</li>" for q in finding.guiding_questions)
    details = (
        f"<details><summary>детали</summary>"
        f"<div style='margin-top:4px'>{html.escape(finding.recommendation)}</div>"
        f"<ul style='margin:4px 0 0 1rem;padding:0'>{questions}</ul>"
        f"<div style='color:#888;margin-top:4px'>score={finding.score} · "
        f"{FOCUS_LABELS.get(finding.focus_area, finding.focus_area)}</div>"
        f"</details>"
    )

    st.markdown(
        f"""
        <div class="word-comment {color}{done_cls}">
          <div class="meta">
            <span class="num">{marker_no}</span>
            <b>{html.escape(finding.agent)}</b>
            · <span class="doneness-pill doneness-{finding.doneness}">{DONENESS_LABELS.get(finding.doneness, '')}</span>
            · {status}
          </div>
          <div style="font-weight:600">{html.escape(finding.block)}</div>
          <div style="margin-top:2px">{html.escape(finding.problem)}</div>
          {details if not done else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if done:
        return None

    a1, a2, a3 = st.columns([1.15, 1, 1.05])
    action = None
    if a1.button("ИИ", key=f"{key_prefix}_ai", help="ИИ предложит и внесёт правку", use_container_width=True):
        action = "ai_fix"
    if a2.button("✓", key=f"{key_prefix}_ok", help="Принять замечание", use_container_width=True):
        action = "fixed"
    if a3.button("✕", key=f"{key_prefix}_no", help="Отклонить замечание", use_container_width=True):
        action = "rejected"
    return action
