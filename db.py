import os

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from src.models import Base


DSN = os.getenv("DSN")
engine = create_engine(DSN, echo=True, pool_pre_ping=True, poolclass=NullPool)
Base.metadata.create_all(engine, checkfirst=True)
