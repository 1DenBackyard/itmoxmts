from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from specguard.auth import hash_password, verify_password
from specguard.config import get_settings
from specguard.review.schemas import ReviewResult
from specguard.storage import StoredDocument


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="analyst")
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    reviews: Mapped[list[Review]] = relationship(back_populates="user")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    result_status: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship(back_populates="reviews")
    document: Mapped[DocumentObject | None] = relationship(
        back_populates="review", cascade="all, delete-orphan", uselist=False
    )
    issues: Mapped[list[IssueRecord]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class DocumentObject(Base):
    __tablename__ = "document_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), unique=True, index=True)
    backend: Mapped[str] = mapped_column(String(20))
    bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_key: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    review: Mapped[Review] = relationship(back_populates="document")


class IssueRecord(Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), index=True)
    agent: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(500))
    evidence: Mapped[str] = mapped_column(Text)
    problem: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    employee_decision: Mapped[str] = mapped_column(String(30), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    review: Mapped[Review] = relationship(back_populates="issues")


class Repository:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self, demo_password: str) -> None:
        Base.metadata.create_all(self.engine)
        with self.session_factory() as session:
            existing = session.scalar(select(User.id).limit(1))
            if existing:
                return
            for email, name, role in [
                ("analyst@example.com", "Анна Аналитик", "analyst"),
                ("engineer@example.com", "Вадим Инженер", "engineer"),
            ]:
                session.add(
                    User(
                        email=email,
                        full_name=name,
                        role=role,
                        password_hash=hash_password(demo_password),
                    )
                )
            session.commit()

    def authenticate(self, email: str, password: str) -> User | None:
        with self.session_factory() as session:
            user = session.scalar(select(User).where(User.email == email.strip().casefold()))
            if user and verify_password(password, user.password_hash):
                session.expunge(user)
                return user
            return None

    def get_user(self, user_id: str) -> User | None:
        with self.session_factory() as session:
            user = session.get(User, user_id)
            if user:
                session.expunge(user)
            return user

    def save_review(
        self,
        *,
        user_id: str,
        filename: str,
        document_text: str,
        result: ReviewResult,
        document: StoredDocument | None = None,
    ) -> str:
        with self.session_factory() as session:
            review = Review(
                user_id=user_id,
                filename=filename[:255],
                content_hash=hashlib.sha256(document_text.encode()).hexdigest(),
                result_status=result.status,
            )
            session.add(review)
            session.flush()
            if document:
                session.add(
                    DocumentObject(
                        review_id=review.id,
                        backend=document.backend,
                        bucket=document.bucket,
                        object_key=document.object_key,
                        content_type=document.content_type,
                        size_bytes=document.size_bytes,
                        content_hash=document.content_hash,
                        etag=document.etag,
                    )
                )
            for issue in result.issues:
                session.add(
                    IssueRecord(
                        review_id=review.id,
                        agent=issue.agent,
                        category=issue.category,
                        severity=issue.severity.value,
                        title=issue.title,
                        evidence="\n---\n".join(item.quote for item in issue.evidence),
                        problem=issue.problem,
                        impact=issue.impact,
                        question=issue.question,
                        recommendation=issue.recommendation,
                        confidence=issue.confidence,
                    )
                )
            session.commit()
            return review.id

    def get_review(self, review_id: str, user_id: str) -> Review | None:
        with self.session_factory() as session:
            review = session.scalar(
                select(Review).where(Review.id == review_id, Review.user_id == user_id)
            )
            if not review:
                return None
            _ = review.document
            _ = list(review.issues)
            return review

    def set_issue_decision(self, issue_id: str, user_id: str, decision: str) -> bool:
        if decision not in {"open", "accepted", "rejected", "fixed"}:
            raise ValueError("Unsupported decision")
        with self.session_factory() as session:
            issue = session.scalar(
                select(IssueRecord)
                .join(Review)
                .where(IssueRecord.id == issue_id, Review.user_id == user_id)
            )
            if not issue:
                return False
            issue.employee_decision = decision
            session.commit()
            return True

    def recent_reviews(self, user_id: str, limit: int = 10) -> list[Review]:
        with self.session_factory() as session:
            rows = list(
                session.scalars(
                    select(Review)
                    .where(Review.user_id == user_id)
                    .order_by(Review.created_at.desc())
                    .limit(limit)
                )
            )
            for row in rows:
                _ = len(row.issues)
            return rows

    def user_metrics(self, user_id: str) -> dict[str, object]:
        with self.session_factory() as session:
            reviews = list(session.scalars(select(Review).where(Review.user_id == user_id)))
            review_ids = [review.id for review in reviews]
            issues = (
                list(
                    session.scalars(
                        select(IssueRecord).where(IssueRecord.review_id.in_(review_ids))
                    )
                )
                if review_ids
                else []
            )
            confirmed = [item for item in issues if item.employee_decision in {"accepted", "fixed"}]
            return {
                "reviews": len(reviews),
                "open": sum(item.employee_decision == "open" for item in issues),
                "confirmed": len(confirmed),
                "fixed": sum(item.employee_decision == "fixed" for item in issues),
                "categories": Counter(item.category for item in confirmed),
            }


@lru_cache(maxsize=1)
def get_repository() -> Repository:
    settings = get_settings()
    repository = Repository(settings.database_url)
    repository.initialize(settings.demo_password)
    return repository
