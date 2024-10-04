from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase
from pydantic import BaseModel


class Base(DeclarativeBase):
    pass


class UsersOrm(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    username: Mapped[str | None]
    approved: Mapped[bool]
    use_transcription: Mapped[bool]


class Summary(BaseModel):
    summary: str
