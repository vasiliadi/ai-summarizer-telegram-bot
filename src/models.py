from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class UsersOrm(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    username: Mapped[str | None]
    approved: Mapped[bool] = mapped_column(server_default="False")
    use_transcription: Mapped[bool] = mapped_column(server_default="False")
    use_translator: Mapped[bool] = mapped_column(server_default="False")
    target_language: Mapped[str] =  mapped_column(server_default="English")
    use_yt_transcription: Mapped[bool] = mapped_column(server_default="False")
