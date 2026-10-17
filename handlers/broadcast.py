import html
import asyncio
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from filters.superadmin import IsSuperAdminFilter
from services.db_service import db_service
from services.broadcaster import safe_broadcast_message
from keyboards.broadcast_kb import get_broadcast_target_keyboard
from config import TARGET_BOT_TOKEN

router = Router(name="broadcast_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


class BroadcastState(StatesGroup):
    waiting_for_text = State()
    waiting_for_group_name = State()


@router.callback_query(F.data == "menu_broadcast")
async def cb_menu_broadcast(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BroadcastState.waiting_for_text)

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(text="❌ Отмена", callback_data="back_to_dashboard")

    text = (
        "📢 <b>ЭКСТРЕННАЯ РАССЫЛКА ОПОВЕЩЕНИЙ</b>\n"
        "────────────────────────\n"
        "✏️ <b>Отправьте в ответ текст сообщения</b>, которое необходимо разослать аудитории бота расписания.\n\n"
        "<i>Поддерживается разметка Telegram (жирный, курсив, ссылки). "
        "После ввода текста вы сможете выбрать целевую аудиторию и подтвердить запуск.</i>"
    )
    try:
        await call.message.edit_text(text, reply_markup=cancel_kb.as_markup())
    except Exception:
        await call.message.answer(text, reply_markup=cancel_kb.as_markup())
    await call.answer()


@router.message(BroadcastState.waiting_for_text)
async def handle_broadcast_text(message: types.Message, state: FSMContext):
    body = message.html_text or message.text or ""
    if not body.strip():
        await message.answer("⚠️ Текст сообщения не должен быть пустым. Отправьте текст:")
        return

    await state.update_data(broadcast_body=body)

    preview = (
        "📢 <b>ПРЕДПРОСМОТР СООБЩЕНИЯ РАССЫЛКИ:</b>\n"
        "────────────────────────\n"
        f"{body}\n"
        "────────────────────────\n"
        "🎯 <b>Выберите получателей рассылки:</b>"
    )
    await message.answer(preview, reply_markup=get_broadcast_target_keyboard())


@router.callback_query(F.data.in_(["bcast_target_all", "bcast_target_chats"]))
async def cb_broadcast_execute_general(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    target_type = "chats" if call.data == "bcast_target_chats" else "all"
    data = await state.get_data()
    body = data.get("broadcast_body")
    await state.clear()

    if not body:
        await call.answer("⚠️ Текст сообщения утерян. Начните заново.", show_alert=True)
        return

    recipients = await db_service.get_broadcast_recipients(target_type=target_type)
    if not recipients:
        await call.message.answer("⚠️ Получатели не найдены в базе данных.")
        await call.answer()
        return

    title = "ВСЕ БЕСЕДЫ" if target_type == "chats" else "ВСЕ ПОЛЬЗОВАТЕЛИ И БЕСЕДЫ"
    final_text = (
        f"📢 <b>ВАЖНОЕ ОПОВЕЩЕНИЕ АДМИНИСТРАЦИИ</b>\n"
        f"────────────────────────\n"
        f"{body}\n\n"
        f"<i>Колледж AITU</i>"
    )

    status_msg = await call.message.answer(
        f"⏳ <i>Запуск рассылки ({title}). Всего получателей: {len(recipients)}...</i>"
    )
    await call.answer()

    # Если задан токен основного бота — шлём от его имени
    dispatch_bot = bot
    if TARGET_BOT_TOKEN:
        try:
            dispatch_bot = Bot(token=TARGET_BOT_TOKEN)
        except Exception:
            dispatch_bot = bot

    async def update_progress(current: int, sent: int, failed: int):
        try:
            await status_msg.edit_text(
                f"⏳ <i>Рассылка в процессе ({title})...</i>\n\n"
                f"▫️ Обработано: <b>{current}/{len(recipients)}</b>\n"
                f"▫️ Успешно: <b>{sent}</b> · Ошибок: <b>{failed}</b>"
            )
        except Exception:
            pass

    sent, failed = await safe_broadcast_message(
        bot=dispatch_bot,
        chat_ids=recipients,
        text=final_text,
        on_progress=update_progress
    )

    if dispatch_bot != bot:
        await dispatch_bot.session.close()

    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="◀️ В дашборд", callback_data="back_to_dashboard")

    await status_msg.edit_text(
        f"✅ <b>Рассылка успешно завершена!</b>\n\n"
        f"▫️ Аудитория: <b>{title}</b>\n"
        f"▫️ Всего адресатов: <b>{len(recipients)}</b>\n"
        f"▫️ Доставлено: <b>{sent}</b>\n"
        f"▫️ Ошибок доставки: <b>{failed}</b>",
        reply_markup=back_kb.as_markup()
    )


@router.callback_query(F.data == "bcast_target_group_prompt")
async def cb_bcast_group_prompt(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_group_name)
    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(text="❌ Отмена", callback_data="back_to_dashboard")
    await call.message.edit_text(
        "🎓 <b>Укажите название группы</b> для целевой рассылки (например: <code>9ПО-43к</code>):",
        reply_markup=cancel_kb.as_markup()
    )
    await call.answer()


@router.message(BroadcastState.waiting_for_group_name)
async def handle_bcast_group_name(message: types.Message, state: FSMContext, bot: Bot):
    grp_name = (message.text or "").strip()
    data = await state.get_data()
    body = data.get("broadcast_body")
    await state.clear()

    recipients = await db_service.get_broadcast_recipients(target_type="group", group_name=grp_name)
    if not recipients:
        await message.answer(f"⚠️ Для группы <code>{grp_name}</code> не найдено зарегистрированных студентов и бесед.")
        return

    final_text = (
        f"📢 <b>ОБЪЯВЛЕНИЕ ДЛЯ ГРУППЫ {grp_name}</b>\n"
        f"────────────────────────\n"
        f"{body}\n\n"
        f"<i>Колледж AITU</i>"
    )

    status_msg = await message.answer(
        f"⏳ <i>Рассылаю для группы {grp_name}. Получателей: {len(recipients)}...</i>"
    )

    dispatch_bot = bot
    if TARGET_BOT_TOKEN:
        try:
            dispatch_bot = Bot(token=TARGET_BOT_TOKEN)
        except Exception:
            dispatch_bot = bot

    sent, failed = await safe_broadcast_message(
        bot=dispatch_bot,
        chat_ids=recipients,
        text=final_text
    )

    if dispatch_bot != bot:
        await dispatch_bot.session.close()

    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="◀️ В дашборд", callback_data="back_to_dashboard")

    await status_msg.edit_text(
        f"✅ <b>Рассылка для {grp_name} завершена!</b>\n\n"
        f"▫️ Доставлено: <b>{sent}</b>\n"
        f"▫️ Ошибок: <b>{failed}</b>",
        reply_markup=back_kb.as_markup()
    )


# Команда
@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        # Текст уже передан аргументом
        await state.update_data(broadcast_body=parts[1].strip())
        preview = (
            "📢 <b>ПРЕДПРОСМОТР СООБЩЕНИЯ РАССЫЛКИ:</b>\n"
            "────────────────────────\n"
            f"{parts[1].strip()}\n"
            "────────────────────────\n"
            "🎯 <b>Выберите получателей:</b>"
        )
        await message.answer(preview, reply_markup=get_broadcast_target_keyboard())
    else:
        await state.set_state(BroadcastState.waiting_for_text)
        await message.answer(
            "📢 <b>Рассылка сообщений</b>\n\n"
            "Отправьте текст сообщения для рассылки студентам бота расписания:"
        )
