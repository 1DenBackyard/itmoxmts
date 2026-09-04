import threading
import time
from contextlib import contextmanager
from dataclasses import replace

import pytest
from conftest import make_issue
from fastapi.testclient import TestClient

from specguard.database import Repository
from specguard.review.schemas import ReviewResult
from specguard.storage import LocalDocumentStorage
from specguard.web import COOKIE, WebJob, create_app


def test_fix_proposal_authorization_and_no_mutation(repo, tmp_path, monkeypatch):
    import specguard.web as web

    settings = web.get_settings()
    monkeypatch.setattr(
        web,
        "get_settings",
        lambda: replace(settings, llm_enabled=True, llm_api_key="fake", deepseek_api_key=""),
    )
    calls = []

    def fake_proposal(gateway, text, issue, clarification):
        calls.append((text, clarification))
        return {
            "before": text,
            "replacement": "new",
            "needs_input": False,
            "mode": "replace",
            "explanation": "test",
            "question": "",
        }

    monkeypatch.setattr(web, "propose_fix", fake_proposal)
    with client_for(repo, tmp_path) as client:
        login(client)
        job = client.post("/api/reviews", json={"text": "old"}).json()
        rid = wait_job(client, job["id"])["review_id"]
        original = client.get("/api/reviews/" + rid).json()
        iid = original["issues"][0]["id"]
        path = f"/api/reviews/{rid}/issues/{iid}/suggestion"
        assert (
            client.post(path, json={"text": "old"}, headers={"X-CSRF-Token": "bad"}).status_code
            == 403
        )
        assert client.post(path, json={"text": "old", "clarification": "int"}).status_code == 200
        assert calls == [("old", "int")]
        assert client.get("/api/reviews/" + rid).json() == original
        login(client, "engineer@example.com")
        assert client.post(path, json={"text": "old"}).status_code == 404
        assert len(calls) == 1


class Reviewer:
    reviewers = []

    def run(self, text):
        return ReviewResult(status="Требует уточнения", issues=[make_issue()])


@pytest.fixture
def repo(tmp_path):
    repository = Repository(f"sqlite:///{tmp_path / 'web.db'}")
    repository.initialize("demo1234")
    return repository


@contextmanager
def client_for(repo, tmp_path, reviewer=None):
    application = create_app(
        repo, reviewer or Reviewer(), LocalDocumentStorage(tmp_path / "files"), secure_cookie=False
    )
    with TestClient(application) as client:
        yield client


def login(client, email="analyst@example.com"):
    response = client.post(
        "/api/login",
        json={"email": email, "password": "demo1234"},
        headers={"X-SpecGuard-Request": "1"},
    )
    assert response.status_code == 200, response.text
    client.headers.update({"X-SpecGuard-Request": "1", "X-CSRF-Token": response.json()["csrf"]})
    return response


def wait_job(client, job_id):
    for _ in range(200):
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] in {"completed", "failed"}:
            return data
        time.sleep(0.01)
    raise AssertionError("Job did not terminate")


def test_authentication_csrf_and_logout(repo, tmp_path):
    with client_for(repo, tmp_path) as client:
        assert client.get("/api/me").status_code == 401
        assert client.post("/api/login", json={}).status_code == 403
        response = login(client)
        assert "HttpOnly" in response.headers["set-cookie"]
        token = client.cookies.get(COOKIE)
        assert client.get("/api/me").json()["email"] == "analyst@example.com"
        assert client.post("/api/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
        assert client.post("/api/logout").status_code == 200
        client.cookies.set(COOKIE, token)
        assert client.get("/api/me").status_code == 401


def test_full_flow_and_cross_user_isolation(repo, tmp_path):
    with client_for(repo, tmp_path) as client:
        login(client)
        text = "Общие сведения\nТестовый документ с контрактом полей."
        upload = client.post("/api/uploads?filename=test.txt", content=text.encode())
        assert upload.status_code == 200, upload.text
        job = client.post(
            "/api/reviews",
            json={"text": text, "filename": "test.txt", "upload_id": upload.json()["id"]},
        )
        assert job.status_code == 202, job.text
        result = wait_job(client, job.json()["id"])
        assert result["status"] == "completed"
        review_id = result["review_id"]
        review = client.get(f"/api/reviews/{review_id}").json()
        assert review["text"] == text
        assert client.get(f"/api/reviews/{review_id}/original").content == text.encode()
        issue_id = review["issues"][0]["id"]
        decision_url = f"/api/issues/{issue_id}/decision"
        assert client.post(decision_url, json={"decision": "accepted"}).status_code == 200
        assert client.get("/api/progress").json()["confirmed"] == 1
        assert client.post(decision_url, json={"decision": "open"}).status_code == 200
        assert client.get("/api/progress").json()["confirmed"] == 0
        assert len(client.get("/api/reviews").json()["reviews"]) == 1
        client.post("/api/logout")
        login(client, "engineer@example.com")
        assert client.get(f"/api/reviews/{review_id}").status_code == 404
        assert client.get(f"/api/reviews/{review_id}/original").status_code == 404
        assert client.get(f"/api/jobs/{job.json()['id']}").status_code == 404
        assert client.post(decision_url, json={"decision": "fixed"}).status_code == 404
        assert (
            client.post(
                "/api/reviews", json={"text": text, "upload_id": upload.json()["id"]}
            ).status_code
            == 404
        )


def test_input_limits_and_no_demo_data(repo, tmp_path, monkeypatch):
    import specguard.web

    monkeypatch.setattr(specguard.web, "MAX_UPLOAD", 64)
    with client_for(repo, tmp_path) as client:
        login(client)
        assert client.post("/api/uploads?filename=test.txt", content=b"a" * 65).status_code == 413
        assert client.post("/api/uploads?filename=test.exe", content=b"test").status_code == 422
        assert client.post("/api/reviews", json={"text": " "}).status_code == 422
        assert client.post("/api/reviews", json={"text": "a" * 120001}).status_code == 422
        assert client.get("/data/dataset.json").status_code == 404
        assert client.get("/.env").status_code == 404
        assert client.get("/_stcore/health").text == "ok"
        assert "js/app.js" in client.get("/").text


def test_failure_is_terminal_and_restart_preserves_old_reviews(repo, tmp_path):
    class Broken(Reviewer):
        def run(self, text):
            raise RuntimeError("private input must not leak")

    user = repo.authenticate("analyst@example.com", "demo1234")
    old_id = repo.save_review(
        user_id=user.id,
        filename="old.txt",
        document_text="old",
        result=ReviewResult(status="Готово к передаче", issues=[]),
    )
    with client_for(repo, tmp_path, Broken()) as client:
        login(client)
        job = client.post("/api/reviews", json={"text": "Тест"}).json()
        result = wait_job(client, job["id"])
        assert result["status"] == "failed"
        assert "private" not in result["error"]
        with repo.session_factory() as db:
            db.add(
                WebJob(
                    id="restart-test",
                    user_id=user.id,
                    filename="restart.txt",
                    text="test",
                    status="running",
                    created=time.time(),
                )
            )
            db.commit()
    with client_for(repo, tmp_path) as client:
        login(client)
        assert client.get("/api/jobs/restart-test").json()["status"] == "failed"
        assert client.get(f"/api/reviews/{old_id}").status_code == 200


def test_duplicate_job_blocked_while_running(repo, tmp_path):
    gate = threading.Event()

    class Slow(Reviewer):
        def run(self, text):
            gate.wait(5)
            return super().run(text)

    with client_for(repo, tmp_path, Slow()) as client:
        login(client)
        try:
            first = client.post("/api/reviews", json={"text": "Тест"})
            assert first.status_code == 202
            assert client.post("/api/reviews", json={"text": "Другой"}).status_code == 409
            assert client.get("/api/reviews").json()["jobs"]
        finally:
            gate.set()
        assert wait_job(client, first.json()["id"])["status"] == "completed"
