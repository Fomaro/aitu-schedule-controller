import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from filters.superadmin import IsSuperAdminFilter
from services.supervisor import supervisor
from services.db_service import db_service
from services.git_service import git_service
from config import TARGET_DB_PATH, TARGET_PID_PATH, TARGET_STATUS_PATH, TARGET_BOT_DIR

router = Router(name="diagnostics_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


async def run_diagnostics() -> str:
    """Выполняет полную проверку работоспособности компонентов системы."""
    checks = []

    # 1. Проверка директории целевого бота
    if TARGET_BOT_DIR.exists():
        checks.append("✅ <b>Директория проекта:</b> обнаружена и доступна")
    else:
        checks.append(f"❌ <b>Директория проекта:</b> путь <code>{TARGET_BOT_DIR}</code> не существует!")

    # 2. Проверка базы данных
    if TARGET_DB_PATH.exists():
        size_kb = round(os.path.getsize(TARGET_DB_PATH) / 1024, 1)
        db_ok = await db_service.is_db_available()
        if db_ok:
            checks.append(f"✅ <b>База данных SQLite:</b> исправна ({size_kb} КБ)")
        else:
            checks.append("⚠️ <b>База данных SQLite:</b> файл есть, но не отвечает на запросы")
    else:
        checks.append("❌ <b>База данных SQLite:</b> файл schedule_bot.db отсутствует")

    # 3. Проверка процесса
    proc_stat = await supervisor.get_status()
    if proc_stat["is_running"]:
        checks.append(f"✅ <b>Процесс бота:</b> активен (PID: <code>{proc_stat['pid']}</code>, Uptime: {proc_stat['uptime']})")
    else:
        checks.append(f"⚠️ <b>Процесс бота:</b> в настоящее время остановлен ({proc_stat['mode']})")

    # 4. Проверка Heartbeat
    if TARGET_STATUS_PATH.exists():
        checks.append(f"✅ <b>Файл Heartbeat:</b> активен (статус: <code>{proc_stat.get('heartbeat_status', 'ok')}</code>)")
    else:
        checks.append("⚪️ <b>Файл Heartbeat:</b> .bot_status.json пока не создан")

    # 5. Проверка Git репозитория
    git_info = await git_service.get_info()
    if git_info.get("is_git"):
        checks.append(f"✅ <b>Git репозиторий:</b> валиден (ветка <code>{git_info['branch']}</code>, коммит <code>{git_info['commit']}</code>)")
    else:
        checks.append("⚠️ <b>Git репозиторий:</b> целевая папка не инициализирована как git")

    # 6. Проверка локального HTTP Healthcheck сервера (порт 8080)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.0)) as session:
            async with session.get("http://127.0.0.1:8080/health") as resp:
                if resp.status == 200:
                    checks.append("✅ <b>HTTP Health Check (порт 8080):</b> отвечает 200 OK")
                else:
                    checks.append(f"⚠️ <b>HTTP Health Check:</b> ответил кодом {resp.status}")
    except Exception:
        checks.append("⚪️ <b>HTTP Health Check (порт 8080):</b> сервер не отвечает (нормально, если бот выключен)")

    report = (
        "🧪 <b>ДИАГНОСТИЧЕСКИЙ ОТЧЁТ СИСТЕМЫ</b>\n"
        "────────────────────────\n" +
        "\n".join(checks) +
        "\n────────────────────────\n"
        "💡 <i>Все ключевые подсистемы протестированы.</i>"
    )
    return report


@router.callback_query(F.data == "menu_diagnostics")
async def cb_menu_diagnostics(call: types.CallbackQuery):
    await call.answer("Запускаю тесты...", show_alert=False)
    report_text = await run_diagnostics()

    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="🔄 Повторить диагностику", callback_data="menu_diagnostics")
    back_kb.button(text="◀️ В дашборд", callback_data="back_to_dashboard")
    back_kb.adjust(1, 1)

    try:
        await call.message.edit_text(report_text, reply_markup=back_kb.as_markup())
    except Exception:
        await call.message.answer(report_text, reply_markup=back_kb.as_markup())


@router.message(Command("test", "diagnostics"))
async def cmd_diagnostics(message: types.Message):
    wait_msg = await message.answer("⏳ <i>Выполняю диагностику компонентов системы...</i>")
    report_text = await run_diagnostics()
    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="◀️ В дашборд", callback_data="back_to_dashboard")
    await wait_msg.edit_text(report_text, reply_markup=back_kb.as_markup())
