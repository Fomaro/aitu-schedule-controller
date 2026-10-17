import html
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_replacements_list_keyboard(replacements: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура списка активных замен с возможностью удаления каждой."""
    builder = InlineKeyboardBuilder()

    for rep in replacements[:15]:  # до 15 записей на странице
        rep_id = rep["id"]
        date_str = str(rep["date"])[5:]  # например '10-18'
        pair_num = rep["pair_num"]
        action = "❌ Отмена" if rep["action_type"] == "cancel" else "🔄 Замена"
        grp = rep["group_name"] or "Все"
        subj = (rep.get("subject") or rep.get("raw_text") or "")[:12]
        
        btn_label = f"🗑 {date_str} [{grp}] п.{pair_num}: {action} {subj}"
        builder.button(text=btn_label, callback_data=f"rep_del_{rep_id}")

    builder.adjust(1)

    # Кнопки управления
    controls = InlineKeyboardBuilder()
    controls.button(text="➕ Добавить замену", callback_data="rep_add_prompt")
    controls.button(text="🔄 Обновить список", callback_data="menu_replacements")
    controls.button(text="◀️ Назад в дашборд", callback_data="back_to_dashboard")
    controls.adjust(2, 1)

    builder.attach(controls)
    return builder.as_markup()


def get_cancel_action_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой отмены текущего действия."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить", callback_data="rep_cancel_fsm")
    return builder.as_markup()
