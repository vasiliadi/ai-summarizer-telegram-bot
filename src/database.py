from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from config import DEFAULT_LANG, DSN, SUPPORTED_LANGUAGES
from models import Base, UsersOrm

engine = create_engine(DSN, echo=False, pool_pre_ping=True, poolclass=NullPool)  # type: ignore
Session = sessionmaker(engine)
Base.metadata.create_all(engine, checkfirst=True)


def register_user(  # noqa
    user_id: int,
    first_name: str,
    last_name: str,
    username: str,
    approved: bool = False,
    use_transcription: bool = False,
    use_translator: bool = False,
    target_language: str = DEFAULT_LANG,
    use_yt_transcription: bool = False,
) -> bool:
    with Session() as session:
        try:
            stmt = UsersOrm(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                username=username,
                approved=approved,
                use_transcription=use_transcription,
                use_translator=use_translator,
                target_language=target_language,
                use_yt_transcription=use_yt_transcription,
            )
            session.add(stmt)
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False  # already registered user


def select_user(user_id: int) -> UsersOrm:
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        if user is None:
            raise ValueError("User not found")
        return user


def check_auth(user_id: int) -> bool:
    user = select_user(user_id)
    return user.approved


def toggle_transcription(user_id: int) -> None:
    with Session() as session:
        user = select_user(user_id)
        user.use_transcription = not user.use_transcription
        session.add(user)
        session.commit()


def toggle_translation(user_id: int) -> None:
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        if user is not None:
            user.use_translator = not user.use_translator
            session.commit()


def set_target_language(user_id: int, target_language: str) -> bool:
    if target_language.title() not in SUPPORTED_LANGUAGES:
        return False  # language not supported
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        if user is not None:
            user.target_language = target_language
            session.commit()
            return True
        return False  # User not found


def toggle_yt_transcription(user_id: int) -> None:
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        if user is not None:
            user.use_yt_transcription = not user.use_yt_transcription
            session.commit()
