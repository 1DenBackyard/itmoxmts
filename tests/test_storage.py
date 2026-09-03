from pathlib import Path

from specguard.storage import LocalDocumentStorage, S3DocumentStorage


class FakeS3Client:
    def __init__(self) -> None:
        self.request: dict[str, object] = {}

    def put_object(self, **kwargs: object) -> dict[str, str]:
        self.request = kwargs
        return {"ETag": '"demo-etag"'}


def test_local_storage_persists_document_under_user_prefix(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    stored = storage.put_document(
        user_id="user-1",
        filename="../Техническое задание.pdf",
        content=b"document",
        content_type="application/pdf",
    )

    assert stored.backend == "local"
    assert stored.object_key.startswith("user-1/")
    assert ".." not in stored.object_key
    assert (tmp_path / stored.object_key).read_bytes() == b"document"


def test_s3_storage_uses_cloud_compatible_put_object_contract() -> None:
    client = FakeS3Client()
    storage = S3DocumentStorage(
        bucket="specguard-documents",
        endpoint_url="https://s3.cloud.ru",
        region="ru-central-1",
        access_key_id="tenant:key",
        secret_access_key="secret",
        client=client,
    )

    stored = storage.put_document(
        user_id="user-1",
        filename="spec.txt",
        content=b"requirements",
        content_type="text/plain",
    )

    assert stored.bucket == "specguard-documents"
    assert stored.etag == "demo-etag"
    assert client.request["Bucket"] == "specguard-documents"
    assert client.request["Body"] == b"requirements"
    assert client.request["Metadata"] == {"sha256": stored.content_hash}
