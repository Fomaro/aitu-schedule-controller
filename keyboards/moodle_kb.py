from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_moodle_keyboard(has_latest_file: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура управления синхронизацией с Moodle (do.eduhouse.ru)."""
    builder = InlineKeyboardBuilder()

    builder.button(text="🔍 Проверить сайт сейчас", callback_data="moodle_check_now")
    builder.button(text="📋 Документы на сайте", callback_data="moodle_list_files")
    if has_latest_file:
        builder.button(text="📥 Скачать последний приказ (.docx)", callback_data="moodle_download_last")
    builder.button(text="🔄 Обновить статус", callback_data="menu_moodle_sync")
    builder.button(text="◀️ В главное меню", callback_data="back_to_dashboard")

    builder.adjust(2, 1, 1, 1) if has_latest_file else builder.adjust(2, 1, 1)
    return builder.as_markup()
