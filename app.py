from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from specguard.config import get_settings
from specguard.database import IssueRecord, Review, get_repository
from specguard.documents import DocumentExtractionError, extract_text
from specguard.review import ReviewOrchestrator

st.set_page_config(page_title="NET SpecGuard", page_icon="🔎", layout="wide")

SEVERITY_LABELS = {
    "blocker": "🔴 Blocker",
    "major": "🟠 Major",
    "minor": "🟡 Minor",
    "suggestion": "🔵 Suggestion",
}
DECISION_LABELS = {
    "open": "Открыто",
    "accepted": "Принято",
    "rejected": "Отклонено",
    "fixed": "Исправлено",
}


@st.cache_resource
def services():
    return get_repository(), ReviewOrchestrator()


repository, orchestrator = services()
settings = get_settings()


def login_page() -> None:
    st.title("NET SpecGuard")
    st.subheader("Предварительное ревью технических заданий")
    st.caption("Мультиагентная проверка глазами аналитика, инженера, архитектора и QA")

    with st.form("login", clear_on_submit=False):
        email = st.text_input("Корпоративная почта", value="analyst@example.com")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти", use_container_width=True)
    if submitted:
        user = repository.authenticate(email, password)
        if user:
            st.session_state.user_id = user.id
            st.rerun()
        st.error("Неверная почта или пароль")

    if settings.demo_password == "demo1234":
        st.info("Демо: analyst@example.com / demo1234")


def render_issue(issue: IssueRecord, user_id: str) -> None:
    label = f"{SEVERITY_LABELS.get(issue.severity, issue.severity)} · {issue.title}"
    with st.expander(label, expanded=issue.employee_decision == "open"):
        st.caption(
            f"{issue.agent} · {issue.category} · уверенность {issue.confidence:.0%} · "
            f"{DECISION_LABELS.get(issue.employee_decision, issue.employee_decision)}"
        )
        st.markdown("**Основание**")
        for quote in issue.evidence.split("\n---\n"):
            st.code(quote, language=None)
        st.markdown(f"**Проблема:** {issue.problem}")
        st.markdown(f"**Влияние:** {issue.impact}")
        st.markdown(f"**Вопрос аналитику:** {issue.question}")
        st.markdown(f"**Рекомендация:** {issue.recommendation}")

        accepted, rejected, fixed = st.columns(3)
        if accepted.button("Принять", key=f"accept-{issue.id}", use_container_width=True):
            repository.set_issue_decision(issue.id, user_id, "accepted")
            st.rerun()
        if rejected.button("Отклонить", key=f"reject-{issue.id}", use_container_width=True):
            repository.set_issue_decision(issue.id, user_id, "rejected")
            st.rerun()
        if fixed.button("Исправлено", key=f"fix-{issue.id}", use_container_width=True):
            repository.set_issue_decision(issue.id, user_id, "fixed")
            st.rerun()


def render_review(review: Review, user_id: str) -> None:
    st.subheader(review.filename)
    st.caption(f"Статус готовности: {review.result_status}")
    if not review.issues:
        st.success("Существенных замечаний не найдено")
    for issue in review.issues:
        render_issue(issue, user_id)


def dashboard(user_id: str) -> None:
    st.title("Обзор")
    metrics = repository.user_metrics(user_id)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Проверено ТЗ", metrics["reviews"])
    col2.metric("Открытые замечания", metrics["open"])
    col3.metric("Подтверждённые ошибки", metrics["confirmed"])
    col4.metric("Исправлено", metrics["fixed"])

    st.subheader("Последние проверки")
    recent = repository.recent_reviews(user_id)
    if not recent:
        st.info("Загрузите первое ТЗ, чтобы начать формировать персональную статистику.")
        return
    frame = pd.DataFrame(
        [
            {
                "Документ": review.filename,
                "Статус": review.result_status,
                "Замечаний": len(review.issues),
                "Дата": review.created_at.strftime("%d.%m.%Y %H:%M"),
            }
            for review in recent
        ]
    )
    st.dataframe(frame, hide_index=True, use_container_width=True)


def review_page(user_id: str) -> None:
    st.title("Проверка ТЗ")
    st.caption("Полный текст документа не сохраняется: только hash, метаданные и замечания.")

    uploaded = st.file_uploader("Загрузите документ", type=["pdf", "docx", "txt", "md"])
    pasted = st.text_area(
        "Или вставьте текст", height=220, placeholder="Текст технического задания"
    )

    if st.button("Запустить ревью", type="primary", use_container_width=True):
        try:
            if uploaded is not None:
                filename = uploaded.name
                document_text = extract_text(
                    uploaded.name,
                    uploaded.getvalue(),
                    max_chars=settings.max_document_chars,
                )
            elif pasted.strip():
                filename = "Вставленный текст"
                document_text = pasted.strip()
            else:
                st.warning("Загрузите документ или вставьте текст")
                return

            with st.spinner("Агенты анализируют документ…"):
                result = orchestrator.run(document_text)
                review_id = repository.save_review(
                    user_id=user_id,
                    filename=filename,
                    document_text=document_text,
                    result=result,
                )
            st.session_state.last_review_id = review_id
            if result.warnings:
                st.warning("; ".join(result.warnings))
            st.success(f"Ревью завершено: {result.status}")
        except DocumentExtractionError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Не удалось выполнить проверку: {type(exc).__name__}")

    review_id = st.session_state.get("last_review_id")
    if review_id:
        review = repository.get_review(review_id, user_id)
        if review:
            render_review(review, user_id)


def errors_page(user_id: str) -> None:
    st.title("Мои ошибки")
    metrics = repository.user_metrics(user_id)
    categories: Counter[str] = metrics["categories"]

    st.caption(
        "В профиль входят только принятые или исправленные замечания. "
        "Открытые гипотезы LLM не считаются ошибками сотрудника."
    )
    if not categories:
        st.info("Подтверждённых ошибок пока нет.")
        return

    frame = pd.DataFrame(
        [{"Категория": category, "Количество": count} for category, count in categories.items()]
    ).sort_values("Количество", ascending=False)
    st.bar_chart(frame.set_index("Категория"))
    st.dataframe(frame, hide_index=True, use_container_width=True)

    most_common = frame.iloc[0]["Категория"]
    st.subheader("Персональная рекомендация")
    st.info(
        f"Чаще всего повторяется категория «{most_common}». "
        "Перед следующим ревью проверьте соответствующий раздел по персональному чек-листу."
    )


def architecture_page() -> None:
    st.title("Как работает система")
    st.markdown(
        """
1. Документ преобразуется в общий контекст и карту фактов.
2. Аналитик, Data Engineer, архитектор и QA проверяют свои зоны параллельно.
3. Критик отбрасывает замечания без доказательства в тексте.
4. Судья объединяет дубли и назначает итоговый приоритет.
5. Сотрудник принимает или отклоняет замечания.
6. Только подтверждённые проблемы формируют персональную статистику.
"""
    )
    mode = "Cloud.ru Foundation Models" if settings.llm_enabled else "локальные правила"
    st.success(f"Текущий режим ревью: {mode}")


if "user_id" not in st.session_state:
    login_page()
    st.stop()

user = repository.get_user(st.session_state.user_id)
if not user:
    st.session_state.clear()
    st.rerun()

with st.sidebar:
    st.title("NET SpecGuard")
    st.write(user.full_name)
    st.caption(user.role)
    page = st.radio("Навигация", ["Обзор", "Проверка ТЗ", "Мои ошибки", "Архитектура"])
    if st.button("Выйти", use_container_width=True):
        st.session_state.clear()
        st.rerun()

if page == "Обзор":
    dashboard(user.id)
elif page == "Проверка ТЗ":
    review_page(user.id)
elif page == "Мои ошибки":
    errors_page(user.id)
else:
    architecture_page()
