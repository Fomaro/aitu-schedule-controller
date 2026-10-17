from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_process_keyboard(is_running: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура управления жизненным циклом бота."""
    builder = InlineKeyboardBuilder()

    if not is_running:
        builder.button(text="▶️ Запустить бота", callback_data="proc_start")
    else:
        builder.button(text="⏹ Остановить бота", callback_data="proc_stop")

    builder.button(text="⚡️ Перезапустить", callback_data="proc_restart")
    builder.button(text="💀 Завершить (Kill)", callback_data="proc_kill")
    builder.button(text="🔄 Обновить статус", callback_data="proc_status_refresh")
    builder.button(text="◀️ В главное меню", callback_data="back_to_dashboard")

    builder.adjust(2, 2, 1)
    return builder.as_markup()
