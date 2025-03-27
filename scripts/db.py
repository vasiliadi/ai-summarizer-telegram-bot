import os

from sqlalchemy import create_engine, BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

if os.environ.get("ENV") != "BUILD":
    from dotenv import load_dotenv

    load_dotenv()


DSN = os.environ["DSN"]
engine = create_engine(DSN, echo=True, poolclass=NullPool)


class Base(DeclarativeBase):
    pass


class UsersOrm(Base):
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


try:
    Base.metadata.create_all(engine, checkfirst=True)
finally:
    engine.dispose()
