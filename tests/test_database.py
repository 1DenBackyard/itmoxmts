from pathlib import Path

from specguard.config import Settings
from specguard.database import Repository
from specguard.review import ReviewOrchestrator


def settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        demo_password="demo",
        llm_enabled=False,
        llm_base_url="https://example.test/v1",
        llm_api_key="",
        llm_model="test",
        max_document_chars=10_000,
    )


def test_review_and_confirmed_issue_are_persisted(tmp_path: Path) -> None:
    repository = Repository(f"sqlite:///{tmp_path / 'test.db'}")
    repository.initialize("demo")
    user = repository.authenticate("analyst@example.com", "demo")
    assert user is not None

    text = "Способ загрузки: инкремент. Обновление: только полная перезагрузка месяца."
    result = ReviewOrchestrator(settings()).run(text)
    review_id = repository.save_review(
        user_id=user.id,
        filename="spec.txt",
        document_text=text,
        result=result,
    )

    stored = repository.get_review(review_id, user.id)
    assert stored is not None
    assert len(stored.issues) == 1
    assert repository.set_issue_decision(stored.issues[0].id, user.id, "accepted")

    metrics = repository.user_metrics(user.id)
    assert metrics["reviews"] == 1
    assert metrics["confirmed"] == 1
    assert repository.recent_reviews(user.id)[0].filename == "spec.txt"
