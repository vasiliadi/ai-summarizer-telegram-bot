from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from config import (
    ALLOWED_MODELS_FOR_SUMMARY,
    ALLOWED_PROMPT_KEYS,
    DEFAULT_LANG,
    DEFAULT_MODEL_ID_FOR_SUMMARY,
    DEFAULT_PROMPT_KEY,
    DSN,
    SUPPORTED_LANGUAGES,
)
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
    target_language: str = DEFAULT_LANG,
    use_yt_transcription: bool = False,
    summarizing_model: str = DEFAULT_MODEL_ID_FOR_SUMMARY,
    prompt_key_for_summary: (str) = DEFAULT_PROMPT_KEY,
) -> bool:
    """Register a new user in the database.

    Args:
        user_id (int): Unique Telegram user ID
        first_name (str): User's first name
        last_name (str): User's last name
        username (str): Telegram username
        approved (bool, optional): Whether user is approved.
        use_transcription (bool, optional): Enable audio transcription.
        target_language (str, optional): Target language for translations.
        use_yt_transcription (bool, optional): Enable YouTube transcription.
        summarizing_model (str, optional): Model for summary.
        prompt_key_for_summary (str): Prompt key for summarization strategy.

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
                target_language=target_language,
                use_yt_transcription=use_yt_transcription,
                summarizing_model=summarizing_model,
                prompt_key_for_summary=prompt_key_for_summary,
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


def set_summarizing_model(user_id: int, summarizing_model: str) -> bool:
    """Set the summarizing model for a user.

    Args:
        user_id (int): Unique Telegram user ID
        summarizing_model (str): The model to use for summarization

    Returns:
        bool: True if model was set successfully, False if model is not supported
        or user not found

    Note:
        The summarizing_model string is checked against ALLOWED_MODELS_FOR_SUMMARY
        (case-insensitive)

    """
    if summarizing_model.lower() not in ALLOWED_MODELS_FOR_SUMMARY:
        return False  # model not supported
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        if user is not None:
            user.summarizing_model = summarizing_model
            session.commit()
            return True
        return False  # User not found


def set_prompt_strategy(user_id: int, prompt_key_for_summary: str) -> bool:
    """Set the prompt strategy for summarization for a user.

    Args:
        user_id (int): Unique Telegram user ID
        prompt_key_for_summary (str): The prompt key to use for summarization strategy

    Returns:
        bool: True if prompt strategy was set successfully, False if prompt key is not
        supported or user not found

    Note:
        The prompt_key_for_summary string is checked against ALLOWED_PROMPT_KEYS
        (case-insensitive)

    """
    if prompt_key_for_summary.lower() not in ALLOWED_PROMPT_KEYS:
        return False  # prompt key not supported
    with Session() as session:
        user = session.get(UsersOrm, user_id)
        if user is not None:
            user.prompt_key_for_summary = prompt_key_for_summary
            session.commit()
            return True
        return False  # User not found
