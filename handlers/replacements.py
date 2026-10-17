import html
import re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import BOT_TZ
from services.db_service import db_service
from keyboards.replacements_kb import get_replacements_list_keyboard, get_cancel_action_keyboard

router = Router(name="replacements")


class AddReplacementState(StatesGroup):
    waiting_for_details = State()


def parse_date_quick(raw: str) -> date | None:
    """Парсит дату из '18.10', '18.10.2026', 'сегодня', 'завтра'."""
    clean = raw.strip().lower()
    today = datetime.now(BOT_TZ).date()
    if clean in ("сегодня", "today"):
        return today
    if clean in ("завтра", "tomorrow"):
        return today + timedelta(days=1)
    
    parts = clean.split(".")
    try:
        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2]) if len(parts) > 2 else today.year
        return date(year, month, day)
    except Exception:
        return None


@router.message(Command("replacements", "zameny"))
@router.callback_query(F.data == "menu_replacements")
async def show_replacements_menu(event: types.Message | types.CallbackQuery, state: FSMContext):
    """Отображает список замен и панель управления."""
    await state.clear()
    replacements = await db_service.get_active_replacements()

    text_lines = [
        "⚠️ <b>Центр управления заменами и переменами</b>",
        "──────────────────────────────"
    ]

    if not replacements:
        text_lines.append("<i>Активных замен и отмен пар на ближайшие дни нет.</i>")
    else:
        text_lines.append(f"Всего активных записей: <b>{len(replacements)}</b>\n")
        for i, rep in enumerate(replacements[:10], 1):
            action_badge = "❌ <b>ОТМЕНА</b>" if rep["action_type"] == "cancel" else "🔄 <b>ЗАМЕНА</b>"
            grp = rep["group_name"] or "Для всех групп"
            subj = html.escape(rep.get("subject") or rep.get("raw_text") or "Без названия")
            room = f", каб. {rep['room']}" if rep.get("room") and rep["room"] != "—" else ""
            teacher = f" ({rep['teacher']})" if rep.get("teacher") and rep["teacher"] != "—" else ""
            text_lines.append(
                f"{i}. 📅 <code>{rep['date']}</code> · Пара <b>#{rep['pair_num']}</b>\n"
                f"   👥 <code>{grp}</code>: {action_badge} — {subj}{room}{teacher}"
            )

    text_lines.append("\n💡 <i>Нажмите на кнопку с корзиной ниже, чтобы удалить конкретную запись.</i>")
    text = "\n".join(text_lines)
    kb = get_replacements_list_keyboard(replacements)

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("rep_del_"))
async def handle_delete_replacement(call: types.CallbackQuery):
    """Удаляет замену по ID."""
    rep_id = int(call.data.replace("rep_del_", ""))
    success = await db_service.delete_replacement(rep_id)

    if success:
        await call.answer("✅ Замена успешно удалена!", show_alert=False)
    else:
        await call.answer("❌ Не удалось удалить запись.", show_alert=True)

    # Обновляем список
    replacements = await db_service.get_active_replacements()
    kb = get_replacements_list_keyboard(replacements)
    try:
        await call.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data == "rep_add_prompt")
async def start_add_replacement(call: types.CallbackQuery, state: FSMContext):
    """Запрашивает текст для добавления замены."""
    await state.set_state(AddReplacementState.waiting_for_details)
    await call.answer()

    text = (
        "➕ <b>Добавление новой замены или отмены пары</b>\n"
        "──────────────────────────────\n"
        "Отправьте команду в одном из следующих форматов:\n\n"
        "1️⃣ <b>Отмена пары:</b>\n"
        "<code>18.10 2 9ПО-43к отмена</code>\n"
        "<i>(или для всего колледжа: <code>завтра 1 все отмена</code>)</i>\n\n"
        "2️⃣ <b>Замена / перенос:</b>\n"
        "<code>18.10 3 9ПО-43к МДК 07.01, каб. 305, Иванов</code>\n\n"
        "Нажмите кнопку ниже для отмены."
    )
    await call.message.edit_text(text, reply_markup=get_cancel_action_keyboard())


@router.callback_query(F.data == "rep_cancel_fsm")
async def cancel_fsm(call: types.CallbackQuery, state: FSMContext):
    """Отменяет добавление и возвращает в список."""
    await state.clear()
    await show_replacements_menu(call, state)


@router.message(AddReplacementState.waiting_for_details)
async def process_add_replacement_input(message: types.Message, state: FSMContext):
    """Обрабатывает введенную строку замены."""
    raw = message.text.strip()
    parts = raw.split()

    if len(parts) < 3:
        await message.answer(
            "⚠️ <b>Неверный формат!</b>\n"
            "Пример: <code>18.10 2 9ПО-43к отмена</code> или <code>завтра 3 9ПО-43к Предмет, каб. 305</code>",
            reply_markup=get_cancel_action_keyboard()
        )
        return

    parsed_date = parse_date_quick(parts[0])
    if not parsed_date:
        await message.answer("❌ Не удалось распознать дату (используйте ДД.ММ или 'завтра').")
        return

    try:
        pair_num = int(parts[1])
        if not (1 <= pair_num <= 6):
            raise ValueError()
    except ValueError:
        await message.answer("❌ Номер пары должен быть числом от 1 до 6.")
        return

    grp = parts[2]
    group_name = None if grp.lower() in ("все", "all", "all_groups", "—", "-") else grp

    rest = " ".join(parts[3:]).strip()
    if not rest or rest.lower() in ("отмена", "отменена", "cancel"):
        action_type = "cancel"
        subject = "Пара отменена"
        room = "—"
        teacher = "—"
    else:
        action_type = "replace"
        # Проверяем наличие кабинета и преподавателя
        room_match = re.search(r'(?:каб\.?|ауд\.?)\s*(\d{2,4}[а-яА-Я]?)', rest, re.IGNORECASE)
        room = room_match.group(1) if room_match else "—"
        subject = re.sub(r'(?:каб\.?|ауд\.?)\s*\d{2,4}[а-яА-Я]?', '', rest, flags=re.IGNORECASE).strip().rstrip(",")
        teacher = "—"

    success, msg = await db_service.add_replacement(
        date_str=parsed_date.isoformat(),
        pair_num=pair_num,
        action_type=action_type,
        group_name=group_name,
        subject=subject,
        room=room,
        teacher=teacher,
        raw_text=raw,
        created_by=message.from_user.id
    )

    await state.clear()
    if success:
        await message.answer(
            f"✅ <b>Замена успешно внесена!</b>\n\n"
            f"📅 Дата: <code>{parsed_date.isoformat()}</code>\n"
            f"🔢 Пара: <b>#{pair_num}</b>\n"
            f"👥 Группа: <code>{group_name or 'Все группы'}</code>\n"
            f"📝 Тип: <b>{'❌ Отмена' if action_type == 'cancel' else '🔄 Замена'}</b>\n"
            f"📚 Описание: {html.escape(subject)} (каб. {room})"
        )
    else:
        await message.answer(f"❌ Ошибка сохранения: {html.escape(msg)}")

    # Показываем обновленный список
    await show_replacements_menu(message, state)
