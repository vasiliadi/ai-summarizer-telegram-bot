import os

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase


if os.getenv("ENV") != "PROD":
    from dotenv import load_dotenv

    load_dotenv()


DSN = os.getenv("DSN")
engine = create_engine(DSN, echo=True, poolclass=NullPool)


class Base(DeclarativeBase):
    pass


class UsersOrm(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    username: Mapped[str | None]
    approved: Mapped[bool] = mapped_column(server_default="False")


Base.metadata.create_all(engine, checkfirst=True)
