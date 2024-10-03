from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from config import DSN
from models import Base, UsersOrm


engine = create_engine(DSN, echo=True, pool_pre_ping=True, poolclass=NullPool)
Session = sessionmaker(engine)
Base.metadata.create_all(engine, checkfirst=True)


def register_user(
    user_id, first_name, last_name, username, approved=False, use_transcription=False
):
    with Session() as session:
        try:
            stmt = UsersOrm(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                username=username,
                approved=approved,
                use_transcription=use_transcription,
            )
            session.add(stmt)
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False  # already registered user


def select_user(user_id):
    with Session() as session:
        return session.get(UsersOrm, user_id)


def enable_transcription(user_id):
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        user.use_transcription = True
        session.commit()


def disable_transcription(user_id):
        with Session() as session:
            user = session.get(UsersOrm, user_id)
            user.use_transcription = False
            session.commit()
