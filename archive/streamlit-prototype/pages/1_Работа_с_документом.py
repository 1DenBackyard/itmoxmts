from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analyzer import analyze_document
from src.analyzer.blocks import DocBlock
from src.autofix import apply_finding_fix, build_suggested_fix
from src.config import (
    DATASET_DIR,
    DEMO_USER_ID,
    DOC_TYPES,
    LLM_MODE,
    REVIEWER_ROLES,
)
from src.llm import LLMClient
from src.pdf_extract import extract_text
from src.storage import Store
from src.ui_components import build_document_html, inject_styles, render_word_comment

st.set_page_config(
    page_title="Работа с документом",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()

store = Store()
llm = LLMClient()

with st.sidebar:
    st.markdown("**Документ**")
    reviewer_role = st.selectbox(
        "Роль",
        options=list(REVIEWER_ROLES.keys()),
        format_func=lambda k: REVIEWER_ROLES[k],
        label_visibility="collapsed",
    )
    st.caption("Роль ревьюера")
    doc_type = st.selectbox(
        "Тип ТЗ",
        options=list(DOC_TYPES.keys()),
        index=2,
        format_func=lambda k: DOC_TYPES[k],
    )

    sample_name = None
    if DATASET_DIR.exists():
        samples = ["— свой файл —"] + sorted(
            p.name for p in DATASET_DIR.glob("*.pdf") if "Шаблон" not in p.name
        )
        sample_choice = st.selectbox("Эталон ДатасетТЗ", samples)
        if sample_choice != "— свой файл —":
            sample_name = sample_choice

    uploaded = st.file_uploader("PDF / TXT / MD", type=["pdf", "txt", "md"])

    edit_mode = st.toggle("Редактировать ТЗ", value=False)
    show_optional_missing = st.toggle("Необязательные пустые блоки", value=False)
    show_resolved = st.toggle("Закрытые замечания", value=False)

    st.divider()
    run = st.button("Проверить", type="primary", use_container_width=True)
    recheck = st.button("Проверить снова", use_container_width=True)
    st.caption(f"LLM: {LLM_MODE}")

raw: Optional[bytes] = None
filename = ""
if sample_name:
    path = DATASET_DIR / sample_name
    raw = path.read_bytes()
    filename = sample_name
elif uploaded is not None:
    raw = uploaded.getvalue()
    filename = uploaded.name

if raw is None:
    st.info("Слева выберите ТЗ и нажмите **Проверить**.")
    st.stop()

text = extract_text(filename, raw)
if st.session_state.get("loaded_filename") != filename:
    st.session_state["doc_text"] = text
    st.session_state["loaded_filename"] = filename
    st.session_state.pop("analysis", None)
    st.session_state.pop("blocks", None)
    st.session_state.pop("last_fix_note", None)
    st.session_state.pop("pending_ai_fix", None)

st.session_state.setdefault("doc_text", text)

with st.sidebar:
    st.markdown(f"<div class='sidebar-file'>{filename}</div>", unsafe_allow_html=True)
    if st.session_state.get("current_doc_id"):
        open_n = sum(
            1
            for f in store.load_findings(doc_id=st.session_state["current_doc_id"])
            if f.status == "open"
        )
        st.markdown(
            f"<div class='sidebar-stat'>Открытых замечаний: <b>{open_n}</b></div>",
            unsafe_allow_html=True,
        )

if st.session_state.get("last_fix_note"):
    st.toast(st.session_state["last_fix_note"])
    st.session_state["last_fix_note"] = None

if edit_mode:
    st.session_state["doc_text"] = st.text_area(
        "Текст ТЗ",
        value=st.session_state["doc_text"],
        height=220,
        label_visibility="collapsed",
    )


def _run_analysis() -> None:
    result = analyze_document(
        filename=filename,
        raw=raw or st.session_state["doc_text"].encode("utf-8"),
        text=st.session_state["doc_text"],
        doc_type=doc_type,
        reviewer_role=reviewer_role,
        llm=llm,
    )
    store.replace_doc_findings(result.doc_id, result.findings)
    st.session_state["analysis"] = {
        "doc_id": result.doc_id,
        "demo_mode": result.demo_mode,
        "filename": filename,
        "doc_type": doc_type,
    }
    st.session_state["blocks"] = [b.to_dict() for b in result.blocks]
    st.session_state["current_doc_id"] = result.doc_id


if run or recheck:
    with st.spinner("Проверка…"):
        _run_analysis()

analysis_meta = st.session_state.get("analysis")
doc_id = st.session_state.get("current_doc_id")
blocks_raw = st.session_state.get("blocks")
if not analysis_meta or not doc_id or not blocks_raw:
    st.caption("Нажмите «Проверить» в панели слева.")
    if not edit_mode:
        st.text(st.session_state["doc_text"][:2000])
    st.stop()

blocks = [DocBlock.from_dict(b) for b in blocks_raw]
findings = store.load_findings(doc_id=doc_id)

doc_html, ordered_open = build_document_html(
    blocks,
    findings,
    filename=filename,
    show_optional_missing=show_optional_missing,
)

left, right = st.columns([1.85, 0.85], gap="small")

with left:
    st.markdown(doc_html, unsafe_allow_html=True)

with right:
    st.markdown(
        f"<div class='comments-head'>Замечания · {len(ordered_open)}</div>",
        unsafe_allow_html=True,
    )
    if not ordered_open and not show_resolved:
        st.caption("Нет открытых замечаний")

    for i, finding in enumerate(ordered_open, start=1):
        action = render_word_comment(finding, marker_no=i, key_prefix=f"c_{finding.id}")
        if action == "ai_fix":
            st.session_state["pending_ai_fix"] = {
                "finding_id": finding.id,
                "preview": build_suggested_fix(finding),
            }
            st.rerun()
        elif action in ("fixed", "rejected"):
            store.update_finding_status(finding.id, action, user_id=DEMO_USER_ID)
            st.rerun()

    if show_resolved:
        closed = [f for f in findings if f.status in ("fixed", "rejected")]
        if closed:
            st.caption("Закрытые")
            for j, finding in enumerate(closed, start=1):
                render_word_comment(finding, marker_no=j, key_prefix=f"cl_{finding.id}")

pending = st.session_state.get("pending_ai_fix")
if pending:
    finding = next((f for f in findings if f.id == pending["finding_id"]), None)
    if finding is None:
        st.session_state.pop("pending_ai_fix", None)
    else:
        st.markdown("---")
        st.caption(f"Правка ИИ · {finding.block}")
        st.code(pending["preview"], language=None)
        b1, b2 = st.columns([1, 1])
        if b1.button("Внести в ТЗ и принять", type="primary", key="ai_apply_main"):
            new_text, note = apply_finding_fix(st.session_state["doc_text"], finding)
            st.session_state["doc_text"] = new_text
            store.update_finding_status(finding.id, "fixed", user_id=DEMO_USER_ID)
            st.session_state["last_fix_note"] = note + " · принято"
            st.session_state.pop("pending_ai_fix", None)
            with st.spinner("Перепроверка…"):
                _run_analysis()
            st.rerun()
        if b2.button("Отмена", key="ai_cancel_main"):
            st.session_state.pop("pending_ai_fix", None)
            st.rerun()
