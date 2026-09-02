from __future__ import annotations

import hashlib
import mimetypes
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from specguard.config import Settings


class DocumentStorageError(RuntimeError):
    """Raised when an original document cannot be persisted."""


@dataclass(frozen=True)
class StoredDocument:
    backend: str
    object_key: str
    bucket: str | None
    content_type: str
    size_bytes: int
    content_hash: str
    etag: str | None = None


class DocumentStorage(Protocol):
    backend: str

    def put_document(
        self,
        *,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> StoredDocument: ...


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "document.bin"
    return re.sub(r"[^\w.()-]+", "_", name, flags=re.UNICODE)[:180]


def _object_key(prefix: str, user_id: str, filename: str) -> str:
    now = datetime.now(UTC)
    parts = [
        prefix.strip("/"),
        user_id,
        now.strftime("%Y/%m/%d"),
        f"{uuid.uuid4()}-{_safe_filename(filename)}",
    ]
    return "/".join(part for part in parts if part)


def _content_type(filename: str, supplied: str | None) -> str:
    if supplied and supplied != "application/octet-stream":
        return supplied
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


class LocalDocumentStorage:
    backend = "local"

    def __init__(self, root: str | Path, prefix: str = "") -> None:
        self.root = Path(root)
        self.prefix = prefix

    def put_document(
        self,
        *,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> StoredDocument:
        key = _object_key(self.prefix, user_id, filename)
        target = self.root / key
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        except OSError as exc:
            raise DocumentStorageError("Не удалось сохранить исходный документ локально") from exc
        return StoredDocument(
            backend=self.backend,
            object_key=key,
            bucket=None,
            content_type=_content_type(filename, content_type),
            size_bytes=len(content),
            content_hash=hashlib.sha256(content).hexdigest(),
        )


class S3DocumentStorage:
    backend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        prefix: str = "documents",
        server_side_encryption: str = "",
        client: Any | None = None,
    ) -> None:
        if not bucket or not access_key_id or not secret_access_key:
            raise DocumentStorageError(
                "Для S3 задайте S3_BUCKET, S3_ACCESS_KEY_ID и S3_SECRET_ACCESS_KEY"
            )
        self.bucket = bucket
        self.prefix = prefix
        self.server_side_encryption = server_side_encryption
        self.client = client or self._create_client(
            endpoint_url=endpoint_url,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )

    @staticmethod
    def _create_client(
        *, endpoint_url: str, region: str, access_key_id: str, secret_access_key: str
    ) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise DocumentStorageError("Для S3 установите зависимость boto3") from exc

        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def put_document(
        self,
        *,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> StoredDocument:
        key = _object_key(self.prefix, user_id, filename)
        digest = hashlib.sha256(content).hexdigest()
        request: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": content,
            "ContentType": _content_type(filename, content_type),
            "Metadata": {"sha256": digest},
        }
        if self.server_side_encryption:
            request["ServerSideEncryption"] = self.server_side_encryption
        try:
            response = self.client.put_object(**request)
        except Exception as exc:
            raise DocumentStorageError("Не удалось загрузить документ в Object Storage") from exc

        etag = response.get("ETag")
        return StoredDocument(
            backend=self.backend,
            object_key=key,
            bucket=self.bucket,
            content_type=request["ContentType"],
            size_bytes=len(content),
            content_hash=digest,
            etag=etag.strip('"') if etag else None,
        )


def create_document_storage(settings: Settings) -> DocumentStorage:
    backend = settings.document_storage_backend.strip().lower()
    if backend == "local":
        return LocalDocumentStorage(settings.document_storage_path)
    if backend == "s3":
        return S3DocumentStorage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            prefix=settings.s3_prefix,
            server_side_encryption=settings.s3_server_side_encryption,
        )
    raise DocumentStorageError("DOCUMENT_STORAGE_BACKEND должен быть local или s3")
