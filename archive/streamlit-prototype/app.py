from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DATASET_DIR, DOC_TYPES, LLM_MODE  # noqa: E402
from src.ui_components import inject_styles  # noqa: E402

st.set_page_config(
    page_title="МТС · Анализ ТЗ",
    page_icon="🥩",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_styles()

st.title("МТС · Прожарка документации")
st.caption(
    "Прототип мультиагентного ревью ТЗ объектов данных для аналитика, разработчика и тестировщика."
)

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Работа с документом")
    st.write(
        "Загрузите ТЗ, получите замечания с **прожаркой** (Well done → Rare), "
        "подсказками и конкретными рекомендациями."
    )
    st.page_link("pages/1_Работа_с_документом.py", label="Открыть разбор документа", icon="📄")

with col2:
    st.subheader("2. Дашборд самообучения")
    st.write(
        "Статистика только по **реально исправленным** замечаниям: где часто ошибаетесь и где сильны."
    )
    st.page_link("pages/2_Дашборд_самообучения.py", label="Открыть дашборд", icon="📊")

st.divider()
st.markdown("### Контекст прототипа")
m1, m2, m3 = st.columns(3)
m1.metric("Режим LLM", LLM_MODE)
m2.metric("Типы документов", len(DOC_TYPES))
m3.metric("Датасет", "ДатасетТЗ" if DATASET_DIR.exists() else "не найден")

st.info(
    "Модели и прод-агенты настраивает отдельный участник команды. "
    "Здесь — UI, контракты findings/learning events и mock multi-agent оркестратор."
)

if DATASET_DIR.exists():
    files = sorted(p.name for p in DATASET_DIR.glob("*.pdf"))
    with st.expander("Файлы в ДатасетТЗ"):
        for name in files:
            st.write(f"- {name}")
