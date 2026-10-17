from aiogram.filters import Filter
from aiogram import types
from config import SUPERADMIN_IDS


class IsSuperAdminFilter(Filter):
    """
    Строгий фильтр доступа к боту-контроллеру.
    Пропускает только тех пользователей, чей ID есть в SUPERADMIN_IDS.
    """
    def __init__(self, is_superadmin: bool = True):
        self.is_superadmin = is_superadmin

    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        user = event.from_user
        if not user:
            return False
        user_is_superadmin = user.id in SUPERADMIN_IDS
        return user_is_superadmin == self.is_superadmin
