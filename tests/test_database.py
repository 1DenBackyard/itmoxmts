from pathlib import Path

from conftest import FakeGateway, make_issue, make_settings

from specguard.database import Repository
from specguard.review.llm import CloudRuLLMReviewer
from specguard.review.pipeline import ReviewOrchestrator
from specguard.review.schemas import AgentResponse
from specguard.storage import StoredDocument


def test_review_and_confirmed_issue_are_persisted(tmp_path: Path) -> None:
    repository = Repository(f"sqlite:///{tmp_path / 'test.db'}")
    repository.initialize("demo")
    user = repository.authenticate("analyst@example.com", "demo")
    assert user is not None

    text = "Способ загрузки: инкремент. Обновление: только полная перезагрузка месяца."
    gateway = FakeGateway(AgentResponse(issues=[make_issue()]))
    reviewer = CloudRuLLMReviewer("Аналитик", gateway)
    result = ReviewOrchestrator(make_settings(), reviewers=[reviewer]).run(text)
    review_id = repository.save_review(
        user_id=user.id,
        filename="spec.txt",
        document_text=text,
        result=result,
        document=StoredDocument(
            backend="s3",
            object_key="documents/user/spec.txt",
            bucket="specguard-documents",
            content_type="text/plain",
            size_bytes=len(text.encode()),
            content_hash="hash",
            etag="etag",
        ),
    )

    stored = repository.get_review(review_id, user.id)
    assert stored is not None
    assert stored.document is not None
    assert stored.document.object_key == "documents/user/spec.txt"
    assert stored.document.content_hash == "hash"
    assert len(stored.issues) == 1
    assert repository.set_issue_decision(stored.issues[0].id, user.id, "accepted")

    metrics = repository.user_metrics(user.id)
    assert metrics["reviews"] == 1
    assert metrics["confirmed"] == 1
    assert repository.recent_reviews(user.id)[0].filename == "spec.txt"
