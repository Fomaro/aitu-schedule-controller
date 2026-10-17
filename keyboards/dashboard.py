from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_dashboard_keyboard(is_running: bool = True) -> InlineKeyboardMarkup:
    """Главная клавиатура центра управления (Dashboard)."""
    builder = InlineKeyboardBuilder()

    builder.button(text="⚡️ Процесс бота", callback_data="menu_process")
    builder.button(text="📦 Git & Обновления", callback_data="menu_git")
    builder.button(text="⚠️ Замены пар", callback_data="menu_replacements")
    builder.button(text="📄 Загрузка (.xlsx/.docx)", callback_data="menu_schedule_upload")
    builder.button(text="👥 Роли и старосты", callback_data="menu_roles")
    builder.button(text="📢 Рассылка объявлений", callback_data="menu_broadcast")
    builder.button(text="📜 Журнал логов", callback_data="menu_logs")
    builder.button(text="🧪 Тесты алертов", callback_data="menu_test_alerts")
    builder.button(text="🔬 Диагностика", callback_data="menu_diagnostics")
    builder.button(text="🔄 Обновить статус", callback_data="refresh_dashboard")

    builder.adjust(2, 2, 2, 2, 2)
    return builder.as_markup()
