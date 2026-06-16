from __future__ import annotations

from app.infrastructure.db.repositories.files import FileRepository


class FileService:
    def __init__(self, *, db_session):
        self.db_session = db_session
        self.files = FileRepository(db_session)

    def register_file(
        self,
        *,
        user_id: str,
        filename: str,
        storage_uri: str,
        content_type: str | None = None,
        size_bytes: int | None = None,
        sha256: str | None = None,
        idempotency_key: str | None = None,
    ):
        self.files.ensure_user(user_id)
        file_hash = sha256 or self.files.compute_file_hash(
            filename=filename,
            storage_uri=storage_uri,
            size_bytes=size_bytes,
        )
        existing = self.files.get_by_user_sha256(user_id=user_id, sha256=file_hash)
        if existing is not None:
            return existing

        file = self.files.create_file(
            user_id=user_id,
            sha256=file_hash,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_uri=storage_uri,
            metadata={
                "idempotency_key": idempotency_key,
            },
        )
        self.db_session.commit()
        return file
