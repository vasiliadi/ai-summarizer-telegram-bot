from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from config import (
    ALLOWED_MODELS_FOR_SUMMARY,
    ALLOWED_PROMPT_KEYS,
    ALLOWED_THINKING_LEVELS,
    DEFAULT_LANG,
    DEFAULT_MODEL_ID_FOR_SUMMARY,
    DEFAULT_PROMPT_KEY,
    DEFAULT_THINKING_LEVEL,
    DSN,
    SUPPORTED_LANGUAGES,
)
from models import UsersOrm

engine = create_engine(DSN, echo=False, pool_pre_ping=True)
Session = sessionmaker(engine)


class UserRepository:
    """Data-access object for the users table."""

    def register_user(
        self,
        user_id: int,
        first_name: str,
        last_name: str,
        username: str,
        approved: bool = False,
        target_language: str = DEFAULT_LANG,
        summarizing_model: str = DEFAULT_MODEL_ID_FOR_SUMMARY,
        prompt_key_for_summary: str = DEFAULT_PROMPT_KEY,
        thinking_level: str = DEFAULT_THINKING_LEVEL,
    ) -> bool:
        """Register a new user in the database.

        Returns:
            bool: True if registration is successful, False if already registered.

        """
        with Session() as session:
            try:
                stmt = UsersOrm(
                    user_id=user_id,
                    first_name=first_name,
                    last_name=last_name,
                    username=username,
                    approved=approved,
                    target_language=target_language,
                    summarizing_model=summarizing_model,
                    prompt_key_for_summary=prompt_key_for_summary,
                    thinking_level=thinking_level,
                )
                session.add(stmt)
                session.commit()
            except IntegrityError:
                session.rollback()
                return False
            else:
                return True

    def select_user(self, user_id: int) -> UsersOrm:
        """Retrieve a user from the database by their ID.

        Raises:
            ValueError: If the user is not found.

        """
        with Session() as session:
            user = session.get(UsersOrm, user_id)
            if user is None:
                msg = "User not found"
                raise ValueError(msg)
            return user

    def check_auth(self, user_id: int) -> bool:
        """Return True if the user exists and is approved."""
        user = self.select_user(user_id)
        return user.approved

    def set_target_language(self, user_id: int, target_language: str) -> bool:
        """Set the target language for a user.

        Returns:
            bool: True on success, False if language unsupported or user not found.

        """
        if target_language.title() not in SUPPORTED_LANGUAGES:
            return False
        with Session() as session:
            user = session.get(UsersOrm, user_id)
            if user is not None:
                user.target_language = target_language
                session.commit()
                return True
            return False

    def set_summarizing_model(self, user_id: int, summarizing_model: str) -> bool:
        """Set the summarizing model for a user.

        Returns:
            bool: True on success, False if model unsupported or user not found.

        """
        if summarizing_model.lower() not in ALLOWED_MODELS_FOR_SUMMARY:
            return False
        with Session() as session:
            user = session.get(UsersOrm, user_id)
            if user is not None:
                user.summarizing_model = summarizing_model
                session.commit()
                return True
            return False

    def set_thinking_level(self, user_id: int, thinking_level: str) -> bool:
        """Set the AI thinking level for a user.

        Returns:
            bool: True on success, False if level unsupported or user not found.

        """
        normalized = thinking_level.upper()
        if normalized not in ALLOWED_THINKING_LEVELS:
            return False
        with Session() as session:
            user = session.get(UsersOrm, user_id)
            if user is not None:
                user.thinking_level = normalized
                session.commit()
                return True
            return False

    def set_prompt_strategy(self, user_id: int, prompt_key_for_summary: str) -> bool:
        """Set the prompt strategy for a user.

        Returns:
            bool: True on success, False if key unsupported or user not found.

        """
        if prompt_key_for_summary.lower() not in ALLOWED_PROMPT_KEYS:
            return False
        with Session() as session:
            user = session.get(UsersOrm, user_id)
            if user is not None:
                user.prompt_key_for_summary = prompt_key_for_summary
                session.commit()
                return True
            return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

user_repo = UserRepository()


# ---------------------------------------------------------------------------
# Module-level aliases — preserve the existing public API
# ---------------------------------------------------------------------------

register_user = user_repo.register_user
select_user = user_repo.select_user
check_auth = user_repo.check_auth
set_target_language = user_repo.set_target_language
set_summarizing_model = user_repo.set_summarizing_model
set_thinking_level = user_repo.set_thinking_level
set_prompt_strategy = user_repo.set_prompt_strategy
