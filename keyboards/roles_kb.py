from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_roles_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления администраторами и старостами."""
    builder = InlineKeyboardBuilder()

    builder.button(text="👑 Список всех ролей", callback_data="roles_list_elevated")
    builder.button(text="🔍 Поиск пользователя", callback_data="roles_search_user")
    builder.button(text="🛡 Назначить Admin", callback_data="roles_assign_admin")
    builder.button(text="⭐️ Назначить Starosta", callback_data="roles_assign_starosta")
    builder.button(text="👨‍🎓 Снять роль (в Student)", callback_data="roles_demote_user")
    builder.button(text="◀️ В главное меню", callback_data="back_to_dashboard")

    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()
