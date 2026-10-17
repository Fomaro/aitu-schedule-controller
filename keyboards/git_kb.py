from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_git_keyboard(behind_count: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура управления версиями и обновлениями Git."""
    builder = InlineKeyboardBuilder()

    pull_label = f"🚀 Pull & Рестарт ({behind_count} нов.)" if behind_count > 0 else "🚀 Pull & Рестарт"
    builder.button(text=pull_label, callback_data="git_pull_restart")
    builder.button(text="⬇️ Только Git Pull", callback_data="git_pull_only")
    builder.button(text="📋 Последние коммиты", callback_data="git_recent_commits")
    builder.button(text="🧹 Очистить (Hard Reset)", callback_data="git_reset_hard")
    builder.button(text="🔍 Проверить статус Git", callback_data="git_check_status")
    builder.button(text="◀️ В главное меню", callback_data="back_to_dashboard")

    builder.adjust(2, 2, 2)
    return builder.as_markup()
