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
        """Register a new user; False if that user id is already present."""
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

    def _update_field(self, user_id: int, field: str, value: str) -> bool:
        """Persist a single validated settings field; False if the user is unknown."""
        with Session() as session:
            user = session.get(UsersOrm, user_id)
            if user is None:
                return False
            setattr(user, field, value)
            session.commit()
            return True

    def set_target_language(self, user_id: int, target_language: str) -> bool:
        """Set the user's target language; False if unsupported or user unknown."""
        normalized = target_language.title()
        if normalized not in SUPPORTED_LANGUAGES:
            return False
        return self._update_field(user_id, "target_language", normalized)

    def set_summarizing_model(self, user_id: int, summarizing_model: str) -> bool:
        """Set the user's summarizing model; False if unsupported or user unknown."""
        normalized = summarizing_model.lower()
        if normalized not in ALLOWED_MODELS_FOR_SUMMARY:
            return False
        return self._update_field(user_id, "summarizing_model", normalized)

    def set_thinking_level(self, user_id: int, thinking_level: str) -> bool:
        """Set the user's thinking level; False if unsupported or user unknown."""
        normalized = thinking_level.upper()
        if normalized not in ALLOWED_THINKING_LEVELS:
            return False
        return self._update_field(user_id, "thinking_level", normalized)

    def set_prompt_strategy(self, user_id: int, prompt_key_for_summary: str) -> bool:
        """Set the user's prompt strategy; False if unsupported or user unknown."""
        normalized = prompt_key_for_summary.lower()
        if normalized not in ALLOWED_PROMPT_KEYS:
            return False
        return self._update_field(user_id, "prompt_key_for_summary", normalized)


# Module-level singleton
user_repo = UserRepository()


# Module-level aliases — preserve the existing public API
register_user = user_repo.register_user
select_user = user_repo.select_user
check_auth = user_repo.check_auth
set_target_language = user_repo.set_target_language
set_summarizing_model = user_repo.set_summarizing_model
set_thinking_level = user_repo.set_thinking_level
set_prompt_strategy = user_repo.set_prompt_strategy
