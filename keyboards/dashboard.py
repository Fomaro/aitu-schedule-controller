from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_dashboard_keyboard(is_running: bool = True) -> InlineKeyboardMarkup:
    """Главная клавиатура центра управления (Dashboard)."""
    builder = InlineKeyboardBuilder()

    builder.button(text="⚡️ Управление процессом", callback_data="menu_process")
    builder.button(text="📦 Git & Обновления", callback_data="menu_git")
    builder.button(text="👥 Роли и старосты", callback_data="menu_roles")
    builder.button(text="📜 Журнал логов", callback_data="menu_logs")
    builder.button(text="📢 Экстренная рассылка", callback_data="menu_broadcast")
    builder.button(text="🧪 Диагностика системы", callback_data="menu_diagnostics")
    builder.button(text="🔄 Обновить дашборд", callback_data="refresh_dashboard")

    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()
