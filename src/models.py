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
        use_transcription (bool): Flag for transcription feature, defaults to False.
        use_translator (bool): Flag for translation feature, defaults to False.
        target_language (str): Language for translations, defaults to "English".
        use_yt_transcription (bool): Flag for YouTube transcription, defaults to False.
        summarizing_model (str): Model for summary.
        prompt_key_for_summary (str): Prompt key for summarization strategy.

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
    use_transcription: Mapped[bool] = mapped_column(server_default="False")
    use_translator: Mapped[bool] = mapped_column(server_default="False")
    target_language: Mapped[str] = mapped_column(server_default="English")
    use_yt_transcription: Mapped[bool] = mapped_column(server_default="False")
    summarizing_model: Mapped[str] = mapped_column(
        server_default="gemini-2.5-flash",
    )
    prompt_key_for_summary: Mapped[str] = mapped_column(
        server_default="basic_prompt_for_transcript",
    )
