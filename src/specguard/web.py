"""Same-origin HTML application and authenticated API. Run one worker per VM."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Float, String, Text, delete, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from starlette.concurrency import run_in_threadpool

from specguard.config import get_settings
from specguard.database import get_repository
from specguard.documents import DocumentExtractionError, extract_text
from specguard.review import ReviewOrchestrator
from specguard.storage import DocumentStorageError, StoredDocument, create_document_storage
from specguard.ui import CASEHOLDER_CHECKLIST, export_review

logger = logging.getLogger(__name__)
MAX_UPLOAD = 20 * 1024 * 1024
COOKIE = "specguard_session"


class WebBase(DeclarativeBase):
    pass


class WebSession(WebBase):
    __tablename__ = "web_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[float] = mapped_column(Float, index=True)


class WebUpload(WebBase):
    __tablename__ = "web_uploads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    stored: Mapped[str] = mapped_column(Text)


class WebJob(WebBase):
    __tablename__ = "web_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    stored: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), index=True)
    review_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[str] = mapped_column(Text, default="[]")
    created: Mapped[float] = mapped_column(Float)


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=512)


class ReviewInput(BaseModel):
    text: str = Field(min_length=1, max_length=120000)
    filename: str = Field(default="Техническое задание.txt", min_length=1, max_length=255)
    upload_id: str | None = Field(default=None, max_length=36)


class DecisionInput(BaseModel):
    decision: str


async def body_bytes(request: Request, limit: int) -> bytes:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(413, "Превышен допустимый размер запроса")
    return bytes(data)


async def payload(request: Request, schema, limit=600000):
    try:
        return schema.model_validate_json(await body_bytes(request, limit))
    except ValidationError as exc:
        raise HTTPException(422, "Проверьте заполнение полей и размер документа") from exc


def create_app(repository=None, orchestrator=None, storage=None, *, secure_cookie=None):
    settings = get_settings()
    repo = repository or get_repository()
    reviewer = orchestrator or ReviewOrchestrator(settings)
    documents = storage or create_document_storage(settings)
    secure = (
        secure_cookie
        if secure_cookie is not None
        else (os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true")
    )
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="review-job")
    lock = threading.Lock()
    attempts: dict[str, list[float]] = {}

    @asynccontextmanager
    async def lifespan(app):
        WebBase.metadata.create_all(repo.engine)  # Additive tables; existing tables untouched.
        with repo.session_factory() as db:
            db.execute(
                update(WebJob)
                .where(WebJob.status.in_(["queued", "running"]))
                .values(
                    status="failed",
                    error="Сервер перезапущен во время анализа. Запустите проверку снова.",
                )
            )
            db.execute(delete(WebSession).where(WebSession.expires < time.time()))
            db.commit()
        yield
        pool.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="NET SpecGuard", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.repository = repo

    @app.middleware("http")
    async def browser_security(request, call_next):
        if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD"}:
            if request.headers.get("x-specguard-request") != "1":
                return JSONResponse({"detail": "Недопустимый источник запроса"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    def session(request: Request):
        digest = hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()
        with repo.session_factory() as db:
            auth = db.get(WebSession, digest)
            if not auth or auth.expires < time.time() or not repo.get_user(auth.user_id):
                raise HTTPException(401, "Войдите в личный кабинет")
            if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), auth.csrf
            ):
                raise HTTPException(403, "Сессия изменилась. Обновите страницу")
            db.expunge(auth)
            return auth

    def user_response(auth):
        user = repo.get_user(auth.user_id)
        return {
            "id": user.id,
            "email": user.email,
            "name": user.full_name,
            "role": user.role,
            "csrf": auth.csrf,
        }

    def detail(review, text=None, warnings=None):
        data = json.loads(export_review(review))
        data.update(id=review.id, text=text, warnings=warnings or [])
        for entry, issue in zip(data["issues"], review.issues, strict=True):
            entry["id"] = issue.id
        return data

    def original_content(review):
        record = review.document
        if not record or record.backend != documents.backend:
            raise HTTPException(404, "Исходный файл недоступен в текущем хранилище")
        if record.backend == "s3" and record.bucket != getattr(documents, "bucket", None):
            raise HTTPException(404, "Хранилище исходного файла изменилось")
        try:
            return documents.read_document(record.object_key, limit=MAX_UPLOAD)
        except DocumentStorageError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/meta")
    def meta():
        return {
            "demo": settings.demo_password == "demo1234",
            "checklist": CASEHOLDER_CHECKLIST,
            "max_chars": min(settings.max_document_chars, 120000),
            "max_upload": MAX_UPLOAD,
        }

    @app.post("/api/login")
    async def login(request: Request, response: Response):
        values = await payload(request, LoginInput, 4096)
        key = f"{request.client.host}:{values.email.strip().casefold()}"
        now = time.time()
        with lock:
            for old in list(attempts):
                attempts[old] = [stamp for stamp in attempts[old] if now - stamp < 300]
                if not attempts[old]:
                    del attempts[old]
            if len(attempts) > 5000 or len(attempts.get(key, [])) >= 8:
                raise HTTPException(429, "Слишком много попыток. Повторите через 5 минут")
            attempts.setdefault(key, []).append(now)
        user = await run_in_threadpool(repo.authenticate, values.email, values.password)
        if not user:
            raise HTTPException(401, "Неверная почта или пароль")
        token = secrets.token_urlsafe(32)
        auth = WebSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            csrf=secrets.token_urlsafe(32),
            expires=now + 43200,
        )
        with repo.session_factory() as db:
            db.add(auth)
            db.commit()
        response.set_cookie(
            COOKIE, token, httponly=True, secure=secure, samesite="lax", max_age=43200, path="/"
        )
        return user_response(auth)

    @app.get("/api/me")
    def me(auth=Depends(session)):
        return user_response(auth)

    @app.post("/api/logout")
    def logout(response: Response, auth=Depends(session)):
        with repo.session_factory() as db:
            db.execute(delete(WebSession).where(WebSession.token_hash == auth.token_hash))
            db.commit()
        response.delete_cookie(COOKIE, path="/", secure=secure, httponly=True, samesite="lax")
        return {"ok": True}

    @app.post("/api/uploads")
    async def upload(request: Request, filename: str, auth=Depends(session)):
        name = Path(filename).name[:255]
        content = await body_bytes(request, MAX_UPLOAD)
        try:
            text = await run_in_threadpool(
                extract_text, name, content, max_chars=min(settings.max_document_chars, 120000)
            )
            stored = await run_in_threadpool(
                documents.put_document, user_id=auth.user_id, filename=name, content=content
            )
        except (DocumentExtractionError, DocumentStorageError) as exc:
            raise HTTPException(422, str(exc)) from exc
        item = WebUpload(
            id=str(uuid.uuid4()),
            user_id=auth.user_id,
            filename=name,
            text=text,
            stored=json.dumps(asdict(stored)),
        )
        with repo.session_factory() as db:
            db.add(item)
            db.commit()
        return {"id": item.id, "filename": name, "text": text}

    def run_job(job_id):
        try:
            with repo.session_factory() as db:
                job = db.get(WebJob, job_id)
                job.status = "running"
                db.commit()
                user_id, filename, text, stored_json = (
                    job.user_id,
                    job.filename,
                    job.text,
                    job.stored,
                )
            stored = (
                StoredDocument(**json.loads(stored_json))
                if stored_json
                else (
                    documents.put_document(
                        user_id=user_id,
                        filename=f"{filename}.txt",
                        content=text.encode(),
                        content_type="text/plain",
                    )
                )
            )
            result = reviewer.run(text)
            review_id = repo.save_review(
                user_id=user_id,
                filename=filename,
                document_text=text,
                result=result,
                document=stored,
            )
            with repo.session_factory() as db:
                job = db.get(WebJob, job_id)
                job.status, job.review_id = "completed", review_id
                job.warnings = json.dumps(result.warnings, ensure_ascii=False)
                db.commit()
            logger.info("Review job completed id=%s issues=%s", job_id, len(result.issues))
        except Exception as exc:
            logger.error("Review job failed id=%s type=%s", job_id, type(exc).__name__)
            with repo.session_factory() as db:
                job = db.get(WebJob, job_id)
                job.status = "failed"
                job.error = (
                    "Не удалось завершить проверку. Повторите запуск "
                    "или обратитесь к администратору."
                )
                db.commit()

    @app.post("/api/reviews", status_code=202)
    async def start_review(request: Request, auth=Depends(session)):
        values = await payload(request, ReviewInput)
        text = values.text.strip()
        if not text or len(text) > settings.max_document_chars:
            raise HTTPException(422, "Текст пуст или превышает лимит")
        with lock, repo.session_factory() as db:
            pending = list(
                db.scalars(select(WebJob).where(WebJob.status.in_(["queued", "running"])))
            )
            if any(item.user_id == auth.user_id for item in pending):
                raise HTTPException(409, "У вас уже выполняется проверка. Откройте историю")
            if len(pending) >= 4:
                raise HTTPException(429, "Все очереди заняты. Повторите чуть позже")
            stored = ""
            if values.upload_id:
                source = db.get(WebUpload, values.upload_id)
                if not source or source.user_id != auth.user_id:
                    raise HTTPException(404, "Документ не найден")
                if source.text == text:
                    stored = source.stored
            job = WebJob(
                id=str(uuid.uuid4()),
                user_id=auth.user_id,
                filename=values.filename,
                text=text,
                stored=stored,
                status="queued",
                created=time.time(),
            )
            db.add(job)
            db.commit()
            pool.submit(run_job, job.id)
        return {"id": job.id, "status": "queued"}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, auth=Depends(session)):
        with repo.session_factory() as db:
            job = db.get(WebJob, job_id)
            if not job or job.user_id != auth.user_id:
                raise HTTPException(404, "Проверка не найдена")
            return {
                "id": job.id,
                "status": job.status,
                "review_id": job.review_id,
                "error": job.error,
                "created": job.created,
                "filename": job.filename,
            }

    @app.get("/api/reviews")
    def history(auth=Depends(session)):
        with repo.session_factory() as db:
            jobs = list(
                db.scalars(
                    select(WebJob)
                    .where(WebJob.user_id == auth.user_id, WebJob.status != "completed")
                    .order_by(WebJob.created.desc())
                    .limit(10)
                )
            )
            pending = [
                {
                    "id": job.id,
                    "status": job.status,
                    "filename": job.filename,
                    "error": job.error,
                    "created": job.created,
                }
                for job in jobs
            ]
        return {
            "reviews": [detail(r) for r in repo.recent_reviews(auth.user_id, limit=100)],
            "jobs": pending,
        }

    @app.get("/api/reviews/{review_id}")
    def get_review(review_id: str, auth=Depends(session)):
        review = repo.get_review(review_id, auth.user_id)
        if not review:
            raise HTTPException(404, "Ревью не найдено")
        with repo.session_factory() as db:
            job = db.scalar(
                select(WebJob).where(WebJob.review_id == review_id, WebJob.user_id == auth.user_id)
            )
            text = job.text if job else None
            warnings = json.loads(job.warnings) if job else []
        if text is None and review.document:
            try:
                text = extract_text(
                    review.filename, original_content(review), max_chars=settings.max_document_chars
                )
            except (DocumentExtractionError, HTTPException):
                pass  # Historical review remains available even when original storage is offline.
        result = detail(review, text, warnings)
        result["has_original"] = review.document is not None
        return result

    @app.get("/api/reviews/{review_id}/original")
    def original(review_id: str, auth=Depends(session)):
        review = repo.get_review(review_id, auth.user_id)
        if not review:
            raise HTTPException(404, "Ревью не найдено")
        filename = review.filename
        if review.document and review.document.content_type == "text/plain":
            if Path(filename).suffix.lower() not in {".txt", ".md"}:
                filename += ".txt"
        disposition = f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
        return Response(
            original_content(review),
            media_type="application/octet-stream",
            headers={"Content-Disposition": disposition},
        )

    @app.post("/api/issues/{issue_id}/decision")
    async def decision(issue_id: str, request: Request, auth=Depends(session)):
        values = await payload(request, DecisionInput, 4096)
        if values.decision not in {"open", "accepted", "rejected", "fixed"}:
            raise HTTPException(422, "Неизвестное решение")
        if not repo.set_issue_decision(issue_id, auth.user_id, values.decision):
            raise HTTPException(404, "Замечание не найдено")
        return {"ok": True}

    @app.get("/api/progress")
    def progress(auth=Depends(session)):
        return repo.user_metrics(auth.user_id)

    @app.get("/api/system")
    def system(auth=Depends(session)):
        return {
            "model": settings.deepseek_model if settings.deepseek_api_key else settings.llm_model,
            "reviewers": [r.name for r in reviewer.reviewers],
            "controls": settings.llm_control_enabled,
            "storage": settings.document_storage_backend,
            "configured": bool(
                settings.llm_enabled and (settings.llm_api_key or settings.deepseek_api_key)
            ),
        }

    @app.get("/healthz")
    @app.get("/_stcore/health", include_in_schema=False)
    def health():
        return PlainTextResponse("ok")

    web_root = Path(os.getenv("WEB_ROOT", Path(__file__).resolve().parents[2] / "web"))

    @app.get("/")
    def index():
        return FileResponse(web_root / "index.html")

    app.mount("/assets", StaticFiles(directory=web_root / "assets"), name="assets")
    app.mount("/css", StaticFiles(directory=web_root / "css"), name="css")
    app.mount("/js", StaticFiles(directory=web_root / "js"), name="js")
    return app
