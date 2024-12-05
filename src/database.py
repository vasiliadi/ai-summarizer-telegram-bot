from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from config import DEFAULT_LANG, DSN, SUPPORTED_LANGUAGES
from models import UsersOrm

engine = create_engine(DSN, echo=False, pool_pre_ping=True)
Session = sessionmaker(engine)


def register_user(  # noqa: PLR0913
    user_id: int,
    first_name: str,
    last_name: str,
    username: str,
    approved: bool = False,
    use_transcription: bool = False,
    use_translator: bool = False,
    target_language: str = DEFAULT_LANG,
    use_yt_transcription: bool = False,
    parsing_strategy: str = "requests",
) -> bool:
    """Register a new user in the database.

    Args:
        user_id (int): Unique Telegram user ID
        first_name (str): User's first name
        last_name (str): User's last name
        username (str): Telegram username
        approved (bool, optional): Whether user is approved.
        use_transcription (bool, optional): Enable audio transcription.
        use_translator (bool, optional): Enable translation.
        target_language (str, optional): Target language for translations.
        use_yt_transcription (bool, optional): Enable YouTube transcription.
        parsing_strategy (str, optional): Strategy for parsing messages.

    Returns:
        bool: True if registration successful, False if user already exists

    Raises:
        IntegrityError: Handled internally when user already exists

    """
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
                parsing_strategy=parsing_strategy,
            )
            session.add(stmt)
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False  # already registered user


def select_user(user_id: int) -> UsersOrm:
    """Retrieve a user from the database by their ID.

    Args:
        user_id (int): Unique Telegram user ID

    Returns:
        UsersOrm: User object from the database

    Raises:
        ValueError: If user with given ID is not found in the database

    """
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        if user is None:
            msg = "User not found"
            raise ValueError(msg)
        return user


def check_auth(user_id: int) -> bool:
    """Check if a user is approved in the database.

    Args:
        user_id (int): Unique Telegram user ID

    Returns:
        bool: True if user is approved, False otherwise

    Raises:
        ValueError: If user with given ID is not found in the database

    """
    user = select_user(user_id)
    return user.approved


def toggle_transcription(user_id: int) -> None:
    """Toggle the transcription setting for a user.

    Args:
        user_id (int): Unique Telegram user ID

    Returns:
        None

    Raises:
        ValueError: If user with given ID is not found in the database

    """
    with Session() as session:
        user = select_user(user_id)
        user.use_transcription = not user.use_transcription
        session.add(user)
        session.commit()


def toggle_translation(user_id: int) -> None:
    """Toggle the translation setting for a user.

    Args:
        user_id (int): Unique Telegram user ID

    Returns:
        None

    Raises:
        No exceptions raised - silently fails if user not found

    """
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        if user is not None:
            user.use_translator = not user.use_translator
            session.commit()


def set_target_language(user_id: int, target_language: str) -> bool:
    """Set the target language for translations for a user.

    Args:
        user_id (int): Unique Telegram user ID
        target_language (str): The language to set as target for translations

    Returns:
        bool: True if language was set successfully, False if language is not supported
        or user not found

    Note:
        The target_language string is checked against SUPPORTED_LANGUAGES
        (case-insensitive)

    """
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
    """Toggle YouTube transcription setting for a user.

    Args:
        user_id (int): Unique Telegram user ID

    Returns:
        None

    Note:
        Silently fails if user is not found in the database.

    """
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        if user is not None:
            user.use_yt_transcription = not user.use_yt_transcription
            session.commit()
