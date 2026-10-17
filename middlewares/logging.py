import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger("controller.audit")


class AuditLoggingMiddleware(BaseMiddleware):
    """
    Middleware аудит-логирования действий супер-администраторов.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        user_info = f"UID:{user.id} (@{user.username})" if user else "UNKNOWN_USER"

        if isinstance(event, Message):
            text_preview = (event.text or event.caption or "<media>")[:80]
            logger.info(f"👑 [AUDIT COMMAND] {user_info} -> {text_preview}")
        elif isinstance(event, CallbackQuery):
            logger.info(f"👑 [AUDIT BUTTON] {user_info} -> callback_data='{event.data}'")

        return await handler(event, data)
