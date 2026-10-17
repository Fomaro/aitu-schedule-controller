import html
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from filters.superadmin import IsSuperAdminFilter
from keyboards.dashboard import get_dashboard_keyboard
from services.supervisor import supervisor
from services.system_metrics import get_system_metrics
from services.git_service import git_service
from services.db_service import db_service
from config import WATCHDOG_ENABLED, AUTO_RESTART_ON_CRASH

router = Router(name="dashboard_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


async def render_dashboard_text() -> tuple[str, bool]:
    """Генерирует подробную сводку для главного экрана панели супер-администратора."""
    bot_stat = await supervisor.get_status()
    sys_metrics = get_system_metrics()
    git_info = await git_service.get_info()
    db_stats = await db_service.get_stats()

    is_running = bot_stat["is_running"]
    mode_str = bot_stat["mode"].upper()

    # Секция целевого бота
    pid_str = f"<code>{bot_stat['pid']}</code>" if bot_stat['pid'] else "—"
    cpu_str = f"{bot_stat['cpu_percent']}%" if is_running else "—"
    mem_str = f"{bot_stat['memory_mb']} МБ" if is_running else "—"
    uptime_str = f"<code>{bot_stat['uptime']}</code>" if is_running else "—"

    # Секция Git
    git_status_icon = "⚠️ Есть незакоммиченные файлы" if git_info.get("is_dirty") else "Чисто ✅"
    behind_text = ""
    if git_info.get("behind_count", 0) > 0:
        behind_text = f" (⬇️ Отстаёт на <b>{git_info['behind_count']}</b> коммитов)"

    # Секция БД
    db_text = (
        f"▫️ Студентов в базе: <b>{db_stats['total_users']}</b>\n"
        f"▫️ Групп: <b>{db_stats['total_groups']}</b> · Бесед: <b>{db_stats['total_chats']}</b>\n"
        f"▫️ Напоминания (10м / Утро): <b>{db_stats['sub_10min']}</b> / <b>{db_stats['sub_morning']}</b>\n"
        f"▫️ Активных замен в БД: <b>{db_stats['total_replacements']}</b>"
    ) if db_stats["is_available"] else "▫️ <i>База данных schedule_bot.db недоступна</i>"

    # Watchdog
    wd_state = "Включён 🟢" if WATCHDOG_ENABLED else "Выключен ⚪️"
    auto_heal = " (Авто-рестарт: Да)" if AUTO_RESTART_ON_CRASH else ""

    text = (
        f"👑 <b>СУПЕР-АДМИНКА · ПУЛЬТ УПРАВЛЕНИЯ БОТОМ</b>\n"
        f"────────────────────────\n"
        f"🤖 <b>Целевой бот (aitu-schedule-bot):</b>\n"
        f"▫️ Статус: <b>{bot_stat['status_text']}</b>\n"
        f"▫️ Режим: <code>{mode_str}</code> · PID: {pid_str}\n"
        f"▫️ Время непрерывной работы: {uptime_str}\n"
        f"▫️ Нагрузка процесса: CPU: <b>{cpu_str}</b> · RAM: <b>{mem_str}</b>\n"
        f"▫️ Watchdog монитор: <b>{wd_state}</b>{auto_heal}\n\n"
        f"📦 <b>Версия и Git репозиторий:</b>\n"
        f"▫️ Ветка: <code>{git_info['branch']}</code>{behind_text}\n"
        f"▫️ Коммит: <code>{git_info['commit']}</code> ({git_info['date']})\n"
        f"▫️ Сообщение: <i>{html.escape(git_info['message'])}</i>\n"
        f"▫️ Рабочее дерево: {git_status_icon}\n\n"
        f"🗄 <b>База данных и аудитория:</b>\n"
        f"{db_text}\n\n"
        f"🖥 <b>Серверная инфраструктура:</b>\n"
        f"▫️ ОС: <code>{sys_metrics['os']}</code> · Py {sys_metrics['python_version']}\n"
        f"▫️ CPU хоста: <b>{sys_metrics['cpu_usage']}%</b> ({sys_metrics['cpu_cores']} cores)\n"
        f"▫️ RAM хоста: <b>{sys_metrics['ram_used_gb']}</b> / {sys_metrics['ram_total_gb']} ГБ ({sys_metrics['ram_percent']}%)\n"
        f"▫️ Диск свободно: <b>{sys_metrics['disk_free_gb']} ГБ</b> из {sys_metrics['disk_total_gb']} ГБ\n"
        f"▫️ Серверное время: <code>{sys_metrics['server_time']}</code>\n"
    )
    return text, is_running


@router.message(Command("dashboard", "status", "panel"))
async def cmd_dashboard(message: types.Message):
    """Отображает главный дашборд."""
    text, is_running = await render_dashboard_text()
    kb = get_dashboard_keyboard(is_running=is_running)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.in_(["refresh_dashboard", "back_to_dashboard"]))
async def cb_dashboard(call: types.CallbackQuery):
    """Обновляет содержимое дашборда на месте."""
    text, is_running = await render_dashboard_text()
    kb = get_dashboard_keyboard(is_running=is_running)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            await call.message.answer(text, reply_markup=kb)
    await call.answer("Дашборд обновлён 🔄", show_alert=False)
