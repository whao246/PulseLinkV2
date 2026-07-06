from __future__ import annotations

from app.infrastructure.db.repositories.files import FileRepository


class AuthService:
    def __init__(self, *, db_session):
        self.db_session = db_session
        self.files = FileRepository(db_session)

    def ensure_test_user(self, *, user_id: str):
        user = self.files.ensure_user(user_id)
        self.db_session.commit()
        return user

    def ensure_wechat_user(self, *, openid: str):
        user = self.files.ensure_user(f"wechat:{openid}")
        self.db_session.commit()
        return user
