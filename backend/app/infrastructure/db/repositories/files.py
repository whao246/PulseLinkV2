from __future__ import annotations

from hashlib import sha256 as sha256_hash
from uuid import uuid4

from app.infrastructure.db.models import File, User


class FileRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def ensure_user(self, user_id: str) -> User:
        existing = self.db_session.query(User).filter(User.id == user_id).one_or_none()
        if existing is not None:
            return existing
        user = User(
            id=user_id,
            email=f"{user_id}@local.pulselink",
            display_name=user_id,
            is_active=True,
        )
        self.db_session.add(user)
        return user

    def get_by_user_sha256(self, *, user_id: str, sha256: str) -> File | None:
        return (
            self.db_session.query(File)
            .filter(File.user_id == user_id, File.sha256 == sha256)
            .one_or_none()
        )

    def create_file(
        self,
        *,
        user_id: str,
        sha256: str,
        filename: str,
        content_type: str | None,
        size_bytes: int | None,
        storage_uri: str,
        metadata: dict | None = None,
    ) -> File:
        file = File(
            id=f"file_{uuid4().hex}",
            user_id=user_id,
            sha256=sha256,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_uri=storage_uri,
            metadata_json=metadata or {},
        )
        self.db_session.add(file)
        return file

    def compute_file_hash(
        self,
        *,
        filename: str,
        storage_uri: str,
        size_bytes: int | None,
    ) -> str:
        value = f"{filename}\0{storage_uri}\0{size_bytes or 0}".encode("utf-8")
        return sha256_hash(value).hexdigest()
