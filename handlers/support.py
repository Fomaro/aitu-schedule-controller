import html
import logging
from aiogram import Router, F, types, Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from filters.superadmin import IsSuperAdminFilter
from config import TARGET_BOT_TOKEN

logger = logging.getLogger(__name__)

router = Router(name="support_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


class SupportAdminReplyState(StatesGroup):
    waiting_reply = State()


@router.callback_query(F.data.startswith("support_reply_"))
async def handle_support_reply_button(call: types.CallbackQuery, state: FSMContext):
    """Открывает диалог ответа пользователю на обращение в поддержку."""
    try:
        target_uid = int(call.data.replace("support_reply_", ""))
    except ValueError:
        await call.answer("Некорректный ID пользователя", show_alert=True)
        return

    await state.set_state(SupportAdminReplyState.waiting_reply)
    await state.update_data(target_uid=target_uid)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить ответ", callback_data="support_reply_cancel")]
    ])

    await call.message.answer(
        f"✉️ <b>Ответ пользователю</b> [<code>{target_uid}</code>]\n"
        f"──────────────────────────────\n"
        f"Введите текст сообщения (он будет отправлен пользователю в ЛС от имени бота расписания):\n\n"
        f"<i>Для отмены нажмите кнопку ниже:</i>",
        reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data == "support_reply_cancel")
async def handle_support_reply_cancel(call: types.CallbackQuery, state: FSMContext):
    """Отменяет ввод ответа."""
    await state.clear()
    await call.answer("Ответ отменён")
    try:
        await call.message.edit_text("ℹ️ Ответ пользователю отменён.")
    except Exception:
        pass


@router.message(SupportAdminReplyState.waiting_reply)
async def handle_support_reply_message(message: types.Message, state: FSMContext):
    """Отправляет ответ студенту через целевого бота расписания."""
    if (message.text or "").strip() in ("/cancel", "отмена", "Отмена"):
        await state.clear()
        await message.answer("ℹ️ Ответ пользователю отменён.")
        return

    data = await state.get_data()
    target_uid = data.get("target_uid")
    if not target_uid:
        await state.clear()
        await message.answer("⚠️ Ошибка: ID пользователя не найден.")
        return

    reply_body = (
        "📩 <b>Ответ от службы поддержки / разработчиков:</b>\n"
        "──────────────────────\n"
        f"<blockquote>{html.escape(message.text or '')}</blockquote>\n\n"
        "<i>Если у вас есть дополнительные вопросы или уточнения, вы можете написать в «💬 Поддержка / Ошибка».</i>"
    )

    if not TARGET_BOT_TOKEN:
        await message.answer(
            f"❌ <b>Ошибка конфигурации:</b> <code>TARGET_BOT_TOKEN</code> не найден.\n"
            f"Укажите токен основного бота в <code>.env</code> или убедитесь, что он есть в <code>aitu-schedule-bot/.env</code>."
        )
        await state.clear()
        return

    try:
        dispatch_bot = Bot(
            token=TARGET_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        await dispatch_bot.send_message(chat_id=target_uid, text=reply_body)
        await dispatch_bot.session.close()
        await message.answer(f"✅ <b>Ответ успешно доставлен студенту [<code>{target_uid}</code>]!</b>")
    except Exception as e:
        logger.error(f"Ошибка отправки ответа пользователю {target_uid}: {e}")
        await message.answer(f"❌ <b>Не удалось доставить сообщение пользователю [<code>{target_uid}</code>]:</b>\n<code>{e}</code>")

    await state.clear()
