import logging
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from filters.superadmin import IsSuperAdminFilter
from services.api_health_service import api_health_service

logger = logging.getLogger("controller.api_health")

router = Router(name="api_health_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


def get_api_health_keyboard() -> types.InlineKeyboardMarkup:
    """Клавиатура для окна проверки API Health."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Повторить проверку", callback_data="refresh_api_health")
    builder.button(text="🔬 Общая диагностика", callback_data="menu_diagnostics")
    builder.button(text="◀️ В дашборд", callback_data="back_to_dashboard")
    builder.adjust(1, 2)
    return builder.as_markup()


@router.callback_query(F.data.in_(["menu_api_health", "refresh_api_health"]))
async def cb_api_health(call: types.CallbackQuery):
    """Интерактивная проверка здоровья API из меню."""
    await call.answer("Проверяю API и Mini App...", show_alert=False)
    
    health_data = await api_health_service.check_full_health()
    report_text = api_health_service.format_report_text(health_data)
    kb = get_api_health_keyboard()

    try:
        await call.message.edit_text(report_text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            await call.message.answer(report_text, reply_markup=kb)


@router.message(Command("api_health", "health"))
async def cmd_api_health(message: types.Message):
    """Команда /api_health и /health для супер-администраторов."""
    wait_msg = await message.answer("⏳ <i>Опрашиваю REST API и проверяю статус Mini App...</i>")
    health_data = await api_health_service.check_full_health()
    report_text = api_health_service.format_report_text(health_data)
    kb = get_api_health_keyboard()

    await wait_msg.edit_text(report_text, reply_markup=kb)
