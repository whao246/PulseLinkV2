from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models after Base is defined so Base.metadata is populated on import.
from app.infrastructure.db import models  # noqa: E402,F401
