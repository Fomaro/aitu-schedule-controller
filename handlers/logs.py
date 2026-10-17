import html
from aiogram import Router, F, types
from aiogram.filters import Command
from filters.superadmin import IsSuperAdminFilter
from services.log_reader import log_reader
from keyboards.logs_kb import get_logs_keyboard

router = Router(name="logs_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


async def _render_logs_view(event: types.Message | types.CallbackQuery, level_filter: str = "all"):
    logs_text = await log_reader.get_logs(limit=35, level_filter=level_filter)
    kb = get_logs_keyboard(current_filter=level_filter)

    title = {
        "all": "📋 ВСЕ ПОСЛЕДНИЕ СОБЫТИЯ",
        "error": "❌ ТОЛЬКО ОШИБКИ И ИСКЛЮЧЕНИЯ",
        "warning": "⚠️ ТОЛЬКО ПРЕДУПРЕЖДЕНИЯ"
    }.get(level_filter, "ЖУРНАЛ ЛОГОВ")

    text = (
        f"📜 <b>{title}</b>\n"
        f"────────────────────────\n"
        f"<pre><code>{html.escape(logs_text[-3500:])}</code></pre>"
    )

    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except Exception:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu_logs")
async def cb_menu_logs(call: types.CallbackQuery):
    await _render_logs_view(call, level_filter="all")


@router.callback_query(F.data.startswith("logs_filter_"))
async def cb_logs_filter(call: types.CallbackQuery):
    filt = call.data.replace("logs_filter_", "")
    await _render_logs_view(call, level_filter=filt)


@router.callback_query(F.data.startswith("logs_refresh_"))
async def cb_logs_refresh(call: types.CallbackQuery):
    filt = call.data.replace("logs_refresh_", "")
    await _render_logs_view(call, level_filter=filt)


@router.message(Command("logs"))
async def cmd_logs(message: types.Message):
    parts = message.text.split(maxsplit=1)
    filter_val = parts[1].strip().lower() if len(parts) > 1 else "all"
    if filter_val not in ("all", "error", "warning"):
        filter_val = "all"
    await _render_logs_view(message, level_filter=filter_val)
