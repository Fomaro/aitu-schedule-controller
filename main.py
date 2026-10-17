import sys
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions

from config import (
    CONTROLLER_BOT_TOKEN,
    SUPERADMIN_IDS,
    TARGET_BOT_DIR,
    RUN_MODE,
    BOT_TZ,
    WATCHDOG_CHECK_INTERVAL
)
from middlewares.auth import SuperAdminAuthMiddleware
from middlewares.logging import AuditLoggingMiddleware
from handlers import setup_handlers
from services.watchdog import watchdog
from services.moodle_service import moodle_service
from services.system_metrics import get_system_metrics

# Настройка красивого логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("controller.main")


async def register_controller_commands(bot: Bot):
    """Регистрирует подсказки команд в меню Telegram."""
    commands = [
        types.BotCommand(command="dashboard", description="👑 Главный пульт супер-администратора"),
        types.BotCommand(command="api_health", description="🩺 Проверка REST API & Mini App"),
        types.BotCommand(command="sync", description="🌐 Синхронизация с do.eduhouse.ru"),
        types.BotCommand(command="restart", description="⚡️ Перезапустить бота расписания"),
        types.BotCommand(command="pull", description="📦 Подтянуть обновления из Git (Pull)"),
        types.BotCommand(command="replacements", description="⚠️ Управление заменами пар"),
        types.BotCommand(command="upload", description="📄 Загрузка расписания (.docx / .xlsx)"),
        types.BotCommand(command="roles", description="👥 Управление администраторами и старостами"),
        types.BotCommand(command="broadcast", description="📢 Экстренная рассылка студентам"),
        types.BotCommand(command="logs", description="📜 Просмотр последних логов и ошибок"),
        types.BotCommand(command="test_alerts", description="🧪 Тестирование рассылок"),
        types.BotCommand(command="diagnostics", description="🔬 Диагностика систем и компонентов"),
        types.BotCommand(command="status", description="🔍 Экспресс-проверка статуса"),
    ]
    try:
        await bot.set_my_commands(commands)
    except Exception as e:
        logger.warning(f"Не удалось зарегистрировать команды в меню: {e}")


async def on_startup(bot: Bot):
    """Действия при старте бота-контроллера."""
    logger.info("=" * 60)
    logger.info("🚀 Запуск AITU Schedule Supervisor (Бот-контроллер)")
    logger.info(f"▫️ Целевая папка бота: {TARGET_BOT_DIR}")
    logger.info(f"▫️ Режим управления: {RUN_MODE.upper()}")
    logger.info(f"▫️ Авторизованные Superadmins: {sorted(list(SUPERADMIN_IDS))}")
    logger.info("=" * 60)

    # Регистрация меню команд
    await register_controller_commands(bot)

    # Запуск фонового мониторинга Watchdog
    await watchdog.start(bot)

    # Запуск почасовой синхронизации с do.eduhouse.ru (с 14:00 до 21:00)
    await moodle_service.start_scheduler(bot)

    # Оповещение супер-админов о запуске контроллера
    metrics = get_system_metrics()
    startup_time = datetime.now(BOT_TZ).strftime("%d.%m.%Y · %H:%M:%S")

    start_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Открыть Дашборд", callback_data="dashboard"),
            InlineKeyboardButton(text="⚡️ Жизненный цикл", callback_data="menu_process")
        ]
    ])

    startup_text = (
        "🚀 <b>[СЕРВЕР МОНИТОРИНГА АКТИВИРОВАН]</b>\n"
        "──────────────────────────────\n"
        "👑 <b>AITU Schedule Supervisor запущен и взял систему под контроль</b>\n\n"
        "<blockquote>"
        f"🤖 <b>Целевой бот:</b> <code>{TARGET_BOT_DIR.name}</code>\n"
        f"⚙️ <b>Режим управления:</b> <code>{RUN_MODE.upper()}</code>\n"
        f"🛡 <b>Watchdog:</b> проверка каждые <code>{WATCHDOG_CHECK_INTERVAL} сек</code>\n"
        f"🌐 <b>Синхронизация Moodle:</b> <code>do.eduhouse.ru</code> (14:00 – 21:00)\n"
        f"🖥 <b>Сервер:</b> RAM <code>{metrics['ram_used_gb']} / {metrics['ram_total_gb']} ГБ</code> ({metrics['ram_percent']}%)\n"
        f"💾 <b>Swap:</b> <code>{metrics['swap_used_gb']} / {metrics['swap_total_gb']} ГБ</code> | Диск: <code>{metrics['disk_free_gb']} ГБ свободно</code>\n"
        f"⏱ <b>Аптайм VPS:</b> <code>{metrics['system_uptime']}</code>\n"
        f"🕒 <b>Время запуска:</b> <code>{startup_time}</code>"
        "</blockquote>\n\n"
        "🔕 <i>Все сервисные уведомления настроены без звука.</i>"
    )

    for admin_id in SUPERADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=startup_text,
                reply_markup=start_kb,
                disable_notification=True,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о старте админу {admin_id}: {e}")


async def on_shutdown(bot: Bot):
    """Действия при остановке бота-контроллера."""
    logger.info("Остановка бота-контроллера и очистка ресурсов...")

    stop_time = datetime.now(BOT_TZ).strftime("%d.%m.%Y · %H:%M:%S")
    shutdown_text = (
        "🛑 <b>[СЕРВЕР МОНИТОРИНГА ОСТАНОВЛЕН]</b>\n"
        "──────────────────────────────\n"
        "⚠️ <b>AITU Schedule Supervisor переведён в оффлайн-режим.</b>\n\n"
        "<blockquote>"
        f"⏱ <b>Время остановки:</b> <code>{stop_time}</code>\n"
        "ℹ️ <b>Статус:</b> Плановое завершение процесса службы (Shutdown)"
        "</blockquote>"
    )
    for admin_id in SUPERADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=shutdown_text,
                disable_notification=True,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        except Exception:
            pass

    await watchdog.stop()
    await moodle_service.stop_scheduler()
    if bot and bot.session:
        await bot.session.close()
    logger.info("Бот-контроллер успешно остановлен.")


async def main():
    if not CONTROLLER_BOT_TOKEN:
        logger.error(
            "❌ ОШИБКА: Переменная CONTROLLER_BOT_TOKEN не задана в файле .env!\n"
            "Пожалуйста, создайте файл .env на основе .env.example и укажите токен Telegram-бота."
        )
        sys.exit(1)

    bot = Bot(
        token=CONTROLLER_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация Middlewares
    dp.message.outer_middleware(SuperAdminAuthMiddleware())
    dp.callback_query.outer_middleware(SuperAdminAuthMiddleware())
    dp.message.middleware(AuditLoggingMiddleware())
    dp.callback_query.middleware(AuditLoggingMiddleware())

    # Подключение всех модульных хэндлеров
    setup_handlers(dp)

    # Регистрация событий старта и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Запуск polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query"]
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Работа завершена.")
