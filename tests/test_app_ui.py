from pathlib import Path

import streamlit as st
from conftest import make_issue, make_settings
from streamlit.testing.v1 import AppTest

from specguard.database import Repository
from specguard.review.schemas import ReviewResult


def test_real_history_decisions_progress_and_incomplete_review(tmp_path, monkeypatch):
    import specguard.config
    import specguard.database

    repository = Repository(f"sqlite:///{tmp_path / 'ui.db'}")
    repository.initialize("demo1234")
    user = repository.authenticate("analyst@example.com", "demo1234")
    review_id = repository.save_review(
        user_id=user.id,
        filename="real-test.txt",
        document_text="Тестовый документ",
        result=ReviewResult(status="Не готово", issues=[make_issue()]),
    )
    monkeypatch.setattr(specguard.database, "get_repository", lambda: repository)
    monkeypatch.setattr(specguard.config, "get_settings", make_settings)
    st.cache_resource.clear()
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"))
    app.run()
    app.text_input[1].set_value("demo1234")
    app.button[0].click().run()
    assert not app.exception
    assert app.title[0].value == "Новое ревью"

    app.sidebar.radio[0].set_value("История").run()
    assert not app.exception
    assert any(item.value == "real-test.txt" for item in app.subheader)
    next(button for button in app.button if button.label == "Принять").click().run()
    assert repository.user_metrics(user.id)["confirmed"] == 1

    app.sidebar.radio[0].set_value("Мой прогресс").run()
    assert not app.exception
    assert app.checkbox

    app.sidebar.radio[0].set_value("История").run()
    next(button for button in app.button if button.label == "Вернуть в открытые").click().run()
    assert repository.user_metrics(user.id)["confirmed"] == 0
    assert repository.get_review(review_id, user.id).issues[0].employee_decision == "open"

    app.sidebar.radio[0].set_value("Проверка ТЗ").run()
    next(radio for radio in app.radio if radio.label == "Источник").set_value("Текст").run()
    app.text_area[0].set_value("Короткое ТЗ без настроенной модели")
    next(button for button in app.button if button.label == "Запустить ревью").click().run()
    assert not app.exception
    assert not app.success
    assert any("Проверка не выполнена" in item.value for item in app.warning)
    next(button for button in app.button if button.label == "Выйти").click().run()
    assert "user_id" not in app.session_state
    assert "review_source_text" not in app.session_state
    st.cache_resource.clear()
