import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import SUPERADMIN_IDS

logger = logging.getLogger(__name__)


class SuperAdminAuthMiddleware(BaseMiddleware):
    """
    Middleware безопасности: блокирует доступ к контроллеру любым пользователям,
    кроме назначенных в SUPERADMIN_IDS.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        if user.id not in SUPERADMIN_IDS:
            logger.warning(
                f"🚨 [UNAUTHORIZED ACCESS ATTEMPT] User ID {user.id} "
                f"(@{user.username or 'none'}, {user.full_name}) tried to access the Controller Bot."
            )
            denied_msg = (
                "⛔️ <b>Доступ запрещён!</b>\n\n"
                "Этот бот является закрытым пультом супер-администратора (Controller Supervisor) "
                "и предназначен исключительно для авторизованных администраторов инфраструктуры AITU."
            )
            if isinstance(event, Message):
                await event.answer(denied_msg)
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔️ Доступ запрещён. Вы не являетесь супер-администратором.", show_alert=True)
            return None

        return await handler(event, data)
