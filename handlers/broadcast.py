import html
import asyncio
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from filters.superadmin import IsSuperAdminFilter
from services.db_service import db_service
from services.broadcaster import safe_broadcast_message
from services.excel_parser import canonical_group_name
from keyboards.broadcast_kb import (
    get_broadcast_target_keyboard,
    get_course_selection_keyboard,
    get_groups_selection_keyboard,
    get_broadcast_confirm_keyboard
)
from config import TARGET_BOT_TOKEN

router = Router(name="broadcast_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


class BroadcastState(StatesGroup):
    waiting_for_text = State()
    waiting_for_manual_group = State()
    confirm_send = State()


def format_broadcast_message(
    body: str,
    target_type: str,
    group_name: str | None = None,
    with_frame: bool = True
) -> str:
    """Форматирует итоговое сообщение для отправки (с рамкой или без)."""
    if not with_frame:
        return body

    if target_type == "group" and group_name:
        title = f"📢 <b>ОБЪЯВЛЕНИЕ ДЛЯ ГРУППЫ {group_name}</b>"
    elif target_type == "chats":
        title = "📢 <b>ОПОВЕЩЕНИЕ ДЛЯ БЕСЕД КОЛЛЕДЖА</b>"
    else:
        title = "📢 <b>ВАЖНОЕ ОПОВЕЩЕНИЕ АДМИНИСТРАЦИИ</b>"

    return (
        f"{title}\n"
        f"────────────────────────\n"
        f"{body}\n\n"
        f"<i>Колледж AITU</i>"
    )


async def render_confirm_view(data: dict) -> tuple[str, types.InlineKeyboardMarkup]:
    """Формирует текст и клавиатуру экрана подтверждения рассылки."""
    body = data.get("broadcast_body", "")
    target_type = data.get("target_type", "all")
    group_name = data.get("group_name")
    with_frame = data.get("with_frame", True)

    stats = await db_service.get_target_stats(target_type=target_type, group_name=group_name)

    if target_type == "group" and group_name:
        target_title = f"🎓 Группа <b>{group_name}</b>"
    elif target_type == "chats":
        target_title = "💬 <b>Все беседы (групповые чаты)</b>"
    else:
        target_title = "🌐 <b>Все группы (беседы и студенты)</b>"

    formatted_text = format_broadcast_message(body, target_type, group_name, with_frame)

    stats_desc = (
        f"▫️ Всего адресатов: <b>{stats['total']}</b> "
        f"(💬 чатов: <b>{stats['chats']}</b> · 👤 студентов: <b>{stats['users']}</b>)"
    )

    frame_mode_desc = "Официальная рамка ✅" if with_frame else "Чистый текст ✉️"

    text = (
        "📢 <b>ПОДТВЕРЖДЕНИЕ ОТПРАВКИ СООБЩЕНИЯ</b>\n"
        "────────────────────────\n"
        f"🎯 <b>Целевая аудитория:</b> {target_title}\n"
        f"{stats_desc}\n"
        f"🏷 <b>Формат:</b> <code>{frame_mode_desc}</code>\n"
        "────────────────────────\n"
        "👁 <b>Предпросмотр сообщения:</b>\n\n"
        f"{formatted_text}\n"
        "────────────────────────\n"
        "⚠️ <i>Нажмите «Подтвердить и отправить» для запуска рассылки:</i>"
    )

    kb = get_broadcast_confirm_keyboard(with_frame=with_frame)
    return text, kb


# Вход в рассылку через дашборд
@router.callback_query(F.data == "menu_broadcast")
async def cb_menu_broadcast(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BroadcastState.waiting_for_text)

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(text="❌ Отмена", callback_data="bcast_cancel")

    text = (
        "📢 <b>ОТПРАВКА СООБЩЕНИЯ В ГРУППЫ</b>\n"
        "────────────────────────\n"
        "✏️ <b>Отправьте в ответ текст сообщения</b>, которое необходимо отправить студентам или в беседы.\n\n"
        "▫️ <i>Поддерживается разметка Telegram (жирный, курсив, ссылки, списки).</i>\n"
        "▫️ <i>После ввода текста вы сможете выбрать целевую группу (или все группы) и подтвердить отправку.</i>"
    )
    try:
        await call.message.edit_text(text, reply_markup=cancel_kb.as_markup())
    except Exception:
        await call.message.answer(text, reply_markup=cancel_kb.as_markup())
    await call.answer()


# Получение текста сообщения
@router.message(BroadcastState.waiting_for_text)
async def handle_broadcast_text(message: types.Message, state: FSMContext):
    body = message.html_text or message.text or ""
    if not body.strip():
        await message.answer("⚠️ Текст сообщения не должен быть пустым. Пожалуйста, напишите сообщение:")
        return

    await state.update_data(broadcast_body=body, with_frame=True)

    preview = (
        "📢 <b>ПРЕДПРОСМОТР СООБЩЕНИЯ:</b>\n"
        "────────────────────────\n"
        f"{body}\n"
        "────────────────────────\n"
        "🎯 <b>Куда отправить сообщение?</b>\n"
        "Выберите целевую аудиторию:"
    )
    await message.answer(preview, reply_markup=get_broadcast_target_keyboard())


# Выбор общей аудитории ("Во все группы" или "Во все беседы")
@router.callback_query(F.data.in_(["bcast_target_all", "bcast_target_chats"]))
async def cb_target_general(call: types.CallbackQuery, state: FSMContext):
    target_type = "chats" if call.data == "bcast_target_chats" else "all"
    data = await state.get_data()
    if not data.get("broadcast_body"):
        await call.answer("⚠️ Текст сообщения утерян. Начните заново.", show_alert=True)
        return

    await state.update_data(target_type=target_type, group_name=None)
    await state.set_state(BroadcastState.confirm_send)

    data = await state.get_data()
    confirm_text, confirm_kb = await render_confirm_view(data)
    await call.message.edit_text(confirm_text, reply_markup=confirm_kb)
    await call.answer()


# Переход к выбору курса / группы
@router.callback_query(F.data.in_(["bcast_pick_course", "bcast_change_target"]))
async def cb_pick_course(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("broadcast_body"):
        await call.answer("⚠️ Текст сообщения утерян. Начните заново.", show_alert=True)
        return

    courses = await db_service.get_courses()
    kb = get_course_selection_keyboard(courses)

    text = (
        "🎓 <b>ОТПРАВКА В ОПРЕДЕЛЕННУЮ ГРУППУ</b>\n"
        "────────────────────────\n"
        "Выберите курс для быстрого списка групп или введите название вручную:"
    )
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# Выбор курса -> показ списка групп
@router.callback_query(F.data.startswith("bcast_course:"))
async def cb_course_selected(call: types.CallbackQuery, state: FSMContext):
    course_str = call.data.split(":", 1)[1]
    try:
        course_num = int(course_str)
    except ValueError:
        course_num = 1

    groups = await db_service.get_groups_by_course(course_num)
    if not groups:
        await call.answer(f"⚠️ Для {course_num} курса не найдено зарегистрированных групп.", show_alert=True)
        return

    kb = get_groups_selection_keyboard(course=course_num, groups=groups)
    text = (
        f"🎓 <b>ГРУППЫ {course_num} КУРСА</b>\n"
        "────────────────────────\n"
        "Нажмите на нужную группу для целевой отправки сообщения:"
    )
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# Выбор конкретной группы из кнопок
@router.callback_query(F.data.startswith("bcast_grp:"))
async def cb_group_selected(call: types.CallbackQuery, state: FSMContext):
    grp_name = call.data.split(":", 1)[1].strip()
    data = await state.get_data()
    if not data.get("broadcast_body"):
        await call.answer("⚠️ Текст сообщения утерян. Начните заново.", show_alert=True)
        return

    await state.update_data(target_type="group", group_name=grp_name)
    await state.set_state(BroadcastState.confirm_send)

    data = await state.get_data()
    confirm_text, confirm_kb = await render_confirm_view(data)
    await call.message.edit_text(confirm_text, reply_markup=confirm_kb)
    await call.answer()


# Ручной ввод названия группы
@router.callback_query(F.data == "bcast_manual_group_prompt")
async def cb_manual_group_prompt(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_manual_group)

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(text="◀️ Назад к выбору курса", callback_data="bcast_pick_course")
    cancel_kb.button(text="❌ Отмена", callback_data="bcast_cancel")
    cancel_kb.adjust(1, 1)

    text = (
        "⌨️ <b>РУЧНОЙ ВВОД НАЗВАНИЯ ГРУППЫ</b>\n"
        "────────────────────────\n"
        "Отправьте в ответ название группы (например: <code>9ПО-43к</code>, <code>9ис21</code>, <code>9ТМ-11</code>):"
    )
    await call.message.edit_text(text, reply_markup=cancel_kb.as_markup())
    await call.answer()


# Обработка ручного ввода названия группы
@router.message(BroadcastState.waiting_for_manual_group)
async def handle_manual_group_name(message: types.Message, state: FSMContext):
    raw_name = (message.text or "").strip()
    canon_name = canonical_group_name(raw_name) or raw_name

    stats = await db_service.get_target_stats("group", canon_name)
    all_groups = await db_service.get_all_groups()

    if canon_name not in all_groups and stats["total"] == 0:
        suggest_kb = InlineKeyboardBuilder()
        suggest_kb.button(text="🎓 Выбрать из списка курсов", callback_data="bcast_pick_course")
        suggest_kb.button(text="❌ Отмена", callback_data="bcast_cancel")
        suggest_kb.adjust(1, 1)

        await message.answer(
            f"⚠️ Группа <code>{raw_name}</code> не найдена в базе данных и для неё нет подписчиков.\n\n"
            f"Проверьте правильность написания или выберите группу из списка:",
            reply_markup=suggest_kb.as_markup()
        )
        return

    await state.update_data(target_type="group", group_name=canon_name)
    await state.set_state(BroadcastState.confirm_send)

    data = await state.get_data()
    confirm_text, confirm_kb = await render_confirm_view(data)
    await message.answer(confirm_text, reply_markup=confirm_kb)


# Переключение оформления (с рамкой / чистый текст)
@router.callback_query(F.data == "bcast_toggle_frame")
async def cb_toggle_frame(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    curr_frame = data.get("with_frame", True)
    new_frame = not curr_frame
    await state.update_data(with_frame=new_frame)

    data = await state.get_data()
    confirm_text, confirm_kb = await render_confirm_view(data)
    try:
        await call.message.edit_text(confirm_text, reply_markup=confirm_kb)
    except Exception:
        pass
    await call.answer("Оформление переключено 🔄")


# Возврат к списку аудиторий
@router.callback_query(F.data == "bcast_back_to_targets")
async def cb_back_to_targets(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    body = data.get("broadcast_body", "")

    preview = (
        "📢 <b>ПРЕДПРОСМОТР СООБЩЕНИЯ:</b>\n"
        "────────────────────────\n"
        f"{body}\n"
        "────────────────────────\n"
        "🎯 <b>Куда отправить сообщение?</b>\n"
        "Выберите целевую аудиторию:"
    )
    await call.message.edit_text(preview, reply_markup=get_broadcast_target_keyboard())
    await call.answer()


# Изменение текста сообщения
@router.callback_query(F.data == "bcast_edit_text")
async def cb_edit_text(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_text)
    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(text="❌ Отмена", callback_data="bcast_cancel")

    text = "✏️ <b>Отправьте новый текст сообщения</b> взамен предыдущего:"
    await call.message.edit_text(text, reply_markup=cancel_kb.as_markup())
    await call.answer()


# Отмена рассылки
@router.callback_query(F.data == "bcast_cancel")
async def cb_cancel_broadcast(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="◀️ В дашборд", callback_data="back_to_dashboard")
    await call.message.edit_text("❌ <b>Отправка сообщения отменена.</b>", reply_markup=back_kb.as_markup())
    await call.answer()


# Подтверждение и запуск отправки
@router.callback_query(F.data == "bcast_confirm_send")
async def cb_confirm_send(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    body = data.get("broadcast_body")
    target_type = data.get("target_type", "all")
    group_name = data.get("group_name")
    with_frame = data.get("with_frame", True)

    await state.clear()

    if not body:
        await call.answer("⚠️ Текст сообщения утерян. Начните заново.", show_alert=True)
        return

    recipients = await db_service.get_broadcast_recipients(target_type=target_type, group_name=group_name)
    if not recipients:
        await call.message.answer(
            f"⚠️ Получатели не найдены "
            f"({'для группы ' + group_name if group_name else 'в базе данных'})."
        )
        await call.answer()
        return

    final_text = format_broadcast_message(
        body=body,
        target_type=target_type,
        group_name=group_name,
        with_frame=with_frame
    )

    if target_type == "group" and group_name:
        title = f"ГРУППА {group_name}"
    elif target_type == "chats":
        title = "ВСЕ БЕСЕДЫ"
    else:
        title = "ВСЕ ГРУППЫ (беседы и студенты)"

    status_msg = await call.message.answer(
        f"⏳ <i>Запуск отправки сообщения ({title}). Адресатов: {len(recipients)}...</i>"
    )
    await call.answer()

    # Если задан токен основного бота — отправляем от его имени с parse_mode=HTML
    dispatch_bot = bot
    if TARGET_BOT_TOKEN:
        try:
            dispatch_bot = Bot(
                token=TARGET_BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
        except Exception:
            dispatch_bot = bot

    async def update_progress(current: int, sent: int, failed: int):
        try:
            await status_msg.edit_text(
                f"⏳ <i>Отправка в процессе ({title})...</i>\n\n"
                f"▫️ Обработано: <b>{current}/{len(recipients)}</b>\n"
                f"▫️ Доставлено: <b>{sent}</b> · Ошибок: <b>{failed}</b>"
            )
        except Exception:
            pass

    sent, failed = await safe_broadcast_message(
        bot=dispatch_bot,
        chat_ids=recipients,
        text=final_text,
        parse_mode="HTML",
        on_progress=update_progress
    )

    if dispatch_bot != bot:
        await dispatch_bot.session.close()

    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="◀️ В дашборд", callback_data="back_to_dashboard")

    await status_msg.edit_text(
        f"✅ <b>Сообщение успешно отправлено!</b>\n\n"
        f"▫️ Аудитория: <b>{title}</b>\n"
        f"▫️ Всего адресатов: <b>{len(recipients)}</b>\n"
        f"▫️ Успешно доставлено: <b>{sent}</b>\n"
        f"▫️ Ошибок доставки: <b>{failed}</b>",
        reply_markup=back_kb.as_markup()
    )


# Поддержка команд: /broadcast, /send, /message, /msg
@router.message(Command("broadcast", "send", "message", "msg"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        # Текст уже передан аргументом команды
        await state.update_data(broadcast_body=parts[1].strip(), with_frame=True)
        preview = (
            "📢 <b>ПРЕДПРОСМОТР СООБЩЕНИЯ:</b>\n"
            "────────────────────────\n"
            f"{parts[1].strip()}\n"
            "────────────────────────\n"
            "🎯 <b>Куда отправить сообщение?</b>\n"
            "Выберите целевую аудиторию:"
        )
        await message.answer(preview, reply_markup=get_broadcast_target_keyboard())
    else:
        await state.clear()
        await state.set_state(BroadcastState.waiting_for_text)
        cancel_kb = InlineKeyboardBuilder()
        cancel_kb.button(text="❌ Отмена", callback_data="bcast_cancel")

        await message.answer(
            "📢 <b>Отправка сообщения в группы</b>\n\n"
            "✏️ Напишите и отправьте текст сообщения, которое необходимо разослать:\n\n"
            "<i>(Вы сможете выбрать: отправить во все группы или в определенную группу, "
            "а также настроить оформление перед отправкой)</i>",
            reply_markup=cancel_kb.as_markup()
        )
