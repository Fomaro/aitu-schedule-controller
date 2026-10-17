from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_logs_keyboard(current_filter: str = "all") -> InlineKeyboardMarkup:
    """Клавиатура управления просмотром логов."""
    builder = InlineKeyboardBuilder()

    all_mark = "✅ " if current_filter == "all" else ""
    err_mark = "✅ " if current_filter == "error" else ""
    warn_mark = "✅ " if current_filter == "warning" else ""

    builder.button(text=f"{all_mark}📋 Все", callback_data="logs_filter_all")
    builder.button(text=f"{err_mark}❌ Ошибки", callback_data="logs_filter_error")
    builder.button(text=f"{warn_mark}⚠️ Варнинги", callback_data="logs_filter_warning")
    builder.button(text="🔄 Обновить", callback_data=f"logs_refresh_{current_filter}")
    builder.button(text="◀️ В главное меню", callback_data="back_to_dashboard")

    builder.adjust(3, 1, 1)
    return builder.as_markup()
