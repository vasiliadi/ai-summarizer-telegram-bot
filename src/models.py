from sqlalchemy import BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


class UsersOrm(Base):
    """SQLAlchemy ORM model representing users in the database.

    This class defines the structure of the 'users' table, storing user preferences
    and settings for various features of the application.

    Attributes:
        user_id (int): Primary key identifier for the user.
        first_name (str | None): User's first name, optional.
        last_name (str | None): User's last name, optional.
        username (str | None): User's username, optional.
        approved (bool): Flag indicating if the user is approved, defaults to False.
        target_language (str): Language for translations, defaults to "English".
        summarizing_model (str): Model for summary.
        prompt_key_for_summary (str): Prompt key for summarization strategy.
        daily_limit (int): Max requests per day for this user, defaults to 0 (blocked).
        thinking_level (str): AI thinking level

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
        server_default="gemini-3.5-flash-lite",
    )
    prompt_key_for_summary: Mapped[str] = mapped_column(
        server_default="basic_prompt_for_transcript",
    )
    daily_limit: Mapped[int] = mapped_column(server_default="0")
    thinking_level: Mapped[str] = mapped_column(server_default="HIGH")
