from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_broadcast_target_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора аудитории для рассылки сообщения."""
    builder = InlineKeyboardBuilder()

    builder.button(text="📢 Во все группы (беседы и студенты)", callback_data="bcast_target_all")
    builder.button(text="💬 Во все беседы (только чаты групп)", callback_data="bcast_target_chats")
    builder.button(text="🎓 В определенную группу...", callback_data="bcast_pick_course")
    builder.button(text="❌ Отмена", callback_data="bcast_cancel")

    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()


def get_course_selection_keyboard(courses: list[int] | None = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора курса для быстрой фильтрации групп."""
    builder = InlineKeyboardBuilder()
    if not courses:
        courses = [1, 2, 3, 4]

    for c in sorted(courses):
        builder.button(text=f"🎓 {c} курс", callback_data=f"bcast_course:{c}")

    builder.button(text="⌨️ Ввести название вручную", callback_data="bcast_manual_group_prompt")
    builder.button(text="◀️ Назад к выбору аудитории", callback_data="bcast_back_to_targets")

    # 2 курса в строке, затем по одной кнопке
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def get_groups_selection_keyboard(course: int, groups: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура выбора конкретной группы внутри выбранного курса."""
    builder = InlineKeyboardBuilder()

    for grp in groups:
        builder.button(text=grp, callback_data=f"bcast_grp:{grp}")

    # Сетка групп по 3 в ряд
    grid_sizes = [3] * (len(groups) // 3)
    if len(groups) % 3 != 0:
        grid_sizes.append(len(groups) % 3)

    builder.button(text="⌨️ Ввести название вручную", callback_data="bcast_manual_group_prompt")
    builder.button(text="◀️ Назад к курсам", callback_data="bcast_pick_course")
    grid_sizes.extend([1, 1])

    builder.adjust(*grid_sizes)
    return builder.as_markup()


def get_broadcast_confirm_keyboard(with_frame: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения перед отправкой рассылки."""
    builder = InlineKeyboardBuilder()

    frame_label = "🏷 Формат: Официальный ✅" if with_frame else "🏷 Формат: Без рамки ✉️"

    builder.button(text="🚀 Подтвердить и отправить", callback_data="bcast_confirm_send")
    builder.button(text=frame_label, callback_data="bcast_toggle_frame")
    builder.button(text="🎯 Сменить аудиторию / группу", callback_data="bcast_change_target")
    builder.button(text="✏️ Изменить текст", callback_data="bcast_edit_text")
    builder.button(text="❌ Отмена", callback_data="bcast_cancel")

    builder.adjust(1, 1, 1, 1, 1)
    return builder.as_markup()
