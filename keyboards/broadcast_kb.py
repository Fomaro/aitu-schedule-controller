from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_broadcast_target_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора аудитории для экстренной рассылки."""
    builder = InlineKeyboardBuilder()

    builder.button(text="👥 Всем студентам колледжа", callback_data="bcast_target_all")
    builder.button(text="💬 Во все беседы (групповые чаты)", callback_data="bcast_target_chats")
    builder.button(text="🎓 Конкретной группе", callback_data="bcast_target_group_prompt")
    builder.button(text="❌ Отмена", callback_data="back_to_dashboard")

    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()
