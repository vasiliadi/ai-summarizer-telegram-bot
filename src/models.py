from sqlalchemy import BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


class UsersOrm(Base):
    """The `users` table: identity, approval, per-user settings, and daily cap.

    Server defaults must stay in step with the matching constants in `config.py`.
    A `daily_limit` of 0 blocks the user.
    """

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    username: Mapped[str | None]
    approved: Mapped[bool] = mapped_column(server_default="False")
    target_language: Mapped[str] = mapped_column(server_default="English")
    summarizing_model: Mapped[str] = mapped_column(
        server_default="gemini-3.7-flash",
    )
    prompt_key_for_summary: Mapped[str] = mapped_column(
        server_default="basic_prompt_for_transcript",
    )
    daily_limit: Mapped[int] = mapped_column(server_default="0")
    thinking_level: Mapped[str] = mapped_column(server_default="medium")
