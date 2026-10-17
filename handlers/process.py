from aiogram import Router, F, types
from aiogram.filters import Command
from filters.superadmin import IsSuperAdminFilter
from services.supervisor import supervisor
from keyboards.process import get_process_keyboard

router = Router(name="process_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


async def _render_process_menu(event: types.Message | types.CallbackQuery, alert_msg: str | None = None):
    status = await supervisor.get_status()
    is_running = status["is_running"]
    kb = get_process_keyboard(is_running=is_running)

    lines = [
        "⚡️ <b>УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ БОТА</b>",
        "────────────────────────",
        f"▫️ Текущее состояние: <b>{status['status_text']}</b>",
        f"▫️ Эффективный режим: <code>{status['mode'].upper()}</code>",
        f"▫️ Идентификатор процесса (PID): <code>{status['pid'] or 'не запущен'}</code>",
        f"▫️ Время непрерывной работы: <code>{status['uptime']}</code>",
        f"▫️ Память процесса: <b>{status['memory_mb']} МБ</b>",
        f"▫️ Нагрузка CPU: <b>{status['cpu_percent']}%</b>",
        f"▫️ Статус Heartbeat: <code>{status['heartbeat_status']}</code>",
        f"▫️ Рабочая папка: <code>{status['target_dir']}</code>"
    ]
    if alert_msg:
        lines.insert(2, f"\n📢 <i>{alert_msg}</i>\n")

    text = "\n".join(lines)

    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except Exception:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data.in_(["menu_process", "proc_status_refresh"]))
async def cb_menu_process(call: types.CallbackQuery):
    await _render_process_menu(call)


@router.callback_query(F.data == "proc_start")
async def cb_proc_start(call: types.CallbackQuery):
    await call.answer("Запускаю бота...", show_alert=False)
    ok, msg = await supervisor.start()
    await _render_process_menu(call, alert_msg=msg)


@router.callback_query(F.data == "proc_stop")
async def cb_proc_stop(call: types.CallbackQuery):
    await call.answer("Останавливаю бота...", show_alert=False)
    ok, msg = await supervisor.stop()
    await _render_process_menu(call, alert_msg=msg)


@router.callback_query(F.data == "proc_restart")
async def cb_proc_restart(call: types.CallbackQuery):
    await call.answer("Перезапуск бота...", show_alert=False)
    ok, msg = await supervisor.restart()
    await _render_process_menu(call, alert_msg=msg)


@router.callback_query(F.data == "proc_kill")
async def cb_proc_kill(call: types.CallbackQuery):
    await call.answer("Завершаю процесс (Kill)...", show_alert=False)
    ok, msg = await supervisor.kill()
    await _render_process_menu(call, alert_msg=msg)


# Команды
@router.message(Command("restart"))
async def cmd_restart(message: types.Message):
    wait_msg = await message.answer("⏳ <i>Выполняю перезапуск целевого бота...</i>")
    ok, msg = await supervisor.restart()
    await wait_msg.edit_text(f"{msg}\n\nИспользуйте /status для проверки состояния.")


@router.message(Command("start_bot"))
async def cmd_start_bot(message: types.Message):
    ok, msg = await supervisor.start()
    await message.answer(msg)


@router.message(Command("stop_bot"))
async def cmd_stop_bot(message: types.Message):
    ok, msg = await supervisor.stop()
    await message.answer(msg)


@router.message(Command("kill_bot"))
async def cmd_kill_bot(message: types.Message):
    ok, msg = await supervisor.kill()
    await message.answer(msg)
