from __future__ import annotations

from collections.abc import Iterable, Iterator, MutableMapping

from .models import Recipe, Session, VoiceSession
from .repositories.favorite_repository import FavoriteRepository
from .repositories.recipe_repository import RecipeRepository
from .repositories.session_repository import SessionRepository
from .repositories.voice_session_repository import VoiceSessionRepository
from .services.favorite_service import FavoriteService
from .services.rag_service import RagService
from .services.recipe_service import RecipeService
from .services.session_service import SessionService
from .services.stt_service import STTService
from .services.tts_service import TTSService
from .services.voice_orchestrator import VoiceOrchestrator
from .services.voice_session_service import VoiceSessionService


class _RecipeMapping(MutableMapping[str, Recipe]):
    def __init__(self, repository: RecipeRepository) -> None:
        self.repository = repository

    def __getitem__(self, key: str) -> Recipe:
        recipe = self.repository.get(key)
        if recipe is None:
            raise KeyError(key)
        return recipe

    def __setitem__(self, key: str, value: Recipe) -> None:
        if key != value.id:
            raise KeyError(key)
        self.repository.add(value)

    def __delitem__(self, key: str) -> None:
        raise NotImplementedError("Recipe deletion is not supported through the store facade.")

    def __iter__(self) -> Iterator[str]:
        return (recipe.id for recipe in self.repository.list())

    def __len__(self) -> int:
        return len(self.repository.list())


class _SessionMapping(MutableMapping[str, Session]):
    def __init__(self, repository: SessionRepository) -> None:
        self.repository = repository

    def __getitem__(self, key: str) -> Session:
        session = self.repository.get(key)
        if session is None:
            raise KeyError(key)
        return session

    def __setitem__(self, key: str, value: Session) -> None:
        if key != value.id:
            raise KeyError(key)
        self.repository.upsert(value)

    def __delitem__(self, key: str) -> None:
        self.repository.delete(key)

    def __iter__(self) -> Iterator[str]:
        return (session.id for session in self.repository.list())

    def __len__(self) -> int:
        return len(self.repository.list())

    def pop(self, key: str, default: Session | None = None) -> Session | None:
        session = self.repository.get(key)
        if session is None:
            return default
        self.repository.delete(key)
        return session


class _VoiceSessionMapping(MutableMapping[str, VoiceSession]):
    def __init__(self, repository: VoiceSessionRepository) -> None:
        self.repository = repository

    def __getitem__(self, key: str) -> VoiceSession:
        voice_session = self.repository.get(key)
        if voice_session is None:
            raise KeyError(key)
        return voice_session

    def __setitem__(self, key: str, value: VoiceSession) -> None:
        if key != value.id:
            raise KeyError(key)
        self.repository.upsert(value)

    def __delitem__(self, key: str) -> None:
        self.repository.delete(key)

    def __iter__(self) -> Iterator[str]:
        return (voice_session.id for voice_session in self.repository.list())

    def __len__(self) -> int:
        return len(self.repository.list())


class StoreFacade:
    def __init__(self) -> None:
        self.recipe_repository = RecipeRepository()
        self.session_repository = SessionRepository()
        self.voice_session_repository = VoiceSessionRepository()
        self.favorite_repository = FavoriteRepository()
        self.recipe_service = RecipeService(self.recipe_repository)
        self.session_service = SessionService(self.session_repository)
        self.favorite_service = FavoriteService(
            self.favorite_repository, self.recipe_repository
        )
        self.voice_session_service = VoiceSessionService(self.voice_session_repository)
        self.rag_service = RagService(
            recipe_service=self.recipe_service,
            session_service=self.session_service,
        )
        self.stt_service = STTService()
        self.tts_service = TTSService()
        self.voice_orchestrator = VoiceOrchestrator(
            recipe_service=self.recipe_service,
            session_service=self.session_service,
            voice_session_service=self.voice_session_service,
            rag_service=self.rag_service,
            stt_service=self.stt_service,
            tts_service=self.tts_service,
        )
        self.recipes = _RecipeMapping(self.recipe_repository)
        self.sessions = _SessionMapping(self.session_repository)
        self.voice_sessions = _VoiceSessionMapping(self.voice_session_repository)

    def is_empty(self) -> bool:
        return self.recipe_service.is_empty()

    def clear(self) -> None:
        self.voice_session_service.clear()
        self.session_service.clear()
        self.recipe_service.clear()
        self.rag_service.invalidate_index()

    def add_recipe(self, recipe: Recipe) -> Recipe:
        saved = self.recipe_service.add_recipe(recipe)
        self.rag_service.invalidate_index()
        return saved

    def list_recipes(self) -> Iterable[Recipe]:
        return self.recipe_service.list_recipes()

    def get_recipe(self, recipe_id: str) -> Recipe | None:
        return self.recipe_service.get_recipe(recipe_id)

    def add_session(self, session: Session) -> Session:
        return self.session_service.create_session(session)

    def get_session(self, session_id: str) -> Session | None:
        return self.session_service.get_session(session_id)

    def update_session(self, session: Session) -> Session:
        return self.session_service.update_session(session)


store = StoreFacade()
