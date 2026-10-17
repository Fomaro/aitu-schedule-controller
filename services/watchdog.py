import asyncio
import logging
import html
from datetime import datetime
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions
from config import (
    SUPERADMIN_IDS,
    WATCHDOG_ENABLED,
    WATCHDOG_CHECK_INTERVAL,
    AUTO_RESTART_ON_CRASH,
    BOT_TZ
)
from services.supervisor import supervisor
from services.system_metrics import get_system_metrics
from services.log_reader import log_reader

logger = logging.getLogger("controller.watchdog")


class BotWatchdog:
    """
    Фоновый сторожевой сервис (Watchdog / Supervisor loop).
    Непрерывно отслеживает жизнедеятельность целевого бота,
    оповещает супер-администраторов при сбоях и при необходимости выполняет авто-восстановление.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._is_running = False
        self._last_state: bool | None = None  # True = running, False = stopped, None = init

    async def start(self, bot: Bot):
        """Запускает фоновый цикл мониторинга."""
        if not WATCHDOG_ENABLED:
            logger.info("Watchdog отключён в конфигурации (WATCHDOG_ENABLED=False).")
            return

        if self._is_running:
            return

        self._is_running = True
        self._task = asyncio.create_task(self._monitor_loop(bot))
        logger.info(f"Watchdog мониторинг активирован (интервал: {WATCHDOG_CHECK_INTERVAL} сек).")

    async def stop(self):
        """Останавливает мониторинг."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog мониторинг остановлен.")

    async def _notify_admins(self, bot: Bot, text: str, reply_markup: InlineKeyboardMarkup | None = None):
        """Отправляет уведомление всем супер-администраторам без звука."""
        for admin_id in SUPERADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    reply_markup=reply_markup,
                    disable_notification=True,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

    async def _monitor_loop(self, bot: Bot):
        # Даём боту 5 секунд на старт перед первым циклом проверки
        await asyncio.sleep(5.0)

        while self._is_running:
            try:
                status = await supervisor.get_status()
                is_currently_running = status["is_running"]

                # Проверяем переход состояния
                if self._last_state is not None:
                    # Случай 1: Бот упал (был запущен, стал выключен)
                    if self._last_state is True and not is_currently_running:
                        logger.critical("🚨 ОБНАРУЖЕНО ПАДЕНИЕ ЦЕЛЕВОГО БОТА!")

                        metrics = get_system_metrics()
                        now_time = datetime.now(BOT_TZ).strftime("%d.%m.%Y · %H:%M:%S")

                        err_snippet = ""
                        try:
                            recent_errs = await log_reader.get_logs(limit=4, level_filter="error")
                            if recent_errs and "Нет записей в логах" not in recent_errs and "Журнал логов пуст" not in recent_errs:
                                err_snippet = f"\n\n<b>🔍 Журнал ошибок:</b>\n<pre>{html.escape(recent_errs[:700])}</pre>"
                        except Exception:
                            pass

                        alert_text = (
                            "🚨 <b>[КРИТИЧЕСКИЙ СБОЙ СЕРВИСА]</b>\n"
                            "──────────────────────────────\n"
                            "⚠️ <b>Основной бот aitu-schedule-bot перестал отвечать!</b>\n\n"
                            "<blockquote>"
                            f"⚙️ <b>Режим службы:</b> <code>{status['mode'].upper()}</code>\n"
                            f"⏱ <b>Время сбоя:</b> <code>{now_time}</code>\n"
                            f"🖥 <b>Сервер:</b> CPU <code>{metrics['cpu_usage']}%</code> | RAM <code>{metrics['ram_used_gb']}/{metrics['ram_total_gb']} ГБ</code> ({metrics['ram_percent']}%)\n"
                            f"💾 <b>Диск:</b> свободно <code>{metrics['disk_free_gb']} ГБ</code>\n"
                            f"⏱ <b>Аптайм VPS:</b> <code>{metrics['system_uptime']}</code>"
                            "</blockquote>"
                            f"{err_snippet}"
                        )

                        crash_kb = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(text="📊 Дашборд", callback_data="dashboard"),
                                InlineKeyboardButton(text="📋 Журнал логов", callback_data="menu_logs")
                            ]
                        ])

                        if AUTO_RESTART_ON_CRASH:
                            alert_text += "\n\n⏳ <i>Сторожевой сервис (Watchdog) выполняет авто-восстановление...</i>"
                            await self._notify_admins(bot, alert_text, reply_markup=crash_kb)

                            await asyncio.sleep(2.0)
                            ok, msg = await supervisor.restart()
                            await asyncio.sleep(1.5)
                            new_status = await supervisor.get_status()
                            heal_time = datetime.now(BOT_TZ).strftime("%d.%m.%Y · %H:%M:%S")

                            if ok and new_status["is_running"]:
                                heal_text = (
                                    "🟢 <b>[АВТО-ВОССТАНОВЛЕНИЕ УСПЕШНО]</b>\n"
                                    "──────────────────────────────\n"
                                    "⚡️ <b>Основной бот автоматически перезапущен и находится онлайн!</b>\n\n"
                                    "<blockquote>"
                                    f"🆔 <b>Новый PID:</b> <code>{new_status['pid'] or 'active'}</code>\n"
                                    f"📦 <b>Память:</b> <code>{new_status['memory_mb']} МБ</code> | CPU: <code>{new_status['cpu_percent']}%</code>\n"
                                    f"⚙️ <b>Состояние:</b> {new_status['status_text']}\n"
                                    f"⏱ <b>Время восстановления:</b> <code>{heal_time}</code>"
                                    "</blockquote>\n\n"
                                    "<i>Все сервисы расписания, уведомления и Mini App функционируют в штатном режиме.</i>"
                                )
                                heal_kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [
                                        InlineKeyboardButton(text="📊 Дашборд", callback_data="dashboard"),
                                        InlineKeyboardButton(text="⚡️ Жизненный цикл", callback_data="menu_process")
                                    ]
                                ])
                                await self._notify_admins(bot, heal_text, reply_markup=heal_kb)
                            else:
                                fail_text = (
                                    "❌ <b>[ОШИБКА АВТО-ВОССТАНОВЛЕНИЯ]</b>\n"
                                    "──────────────────────────────\n"
                                    "🚨 <b>Не удалось автоматически перезапустить основного бота!</b>\n\n"
                                    "<blockquote>"
                                    f"⚠️ <b>Причина:</b> <code>{html.escape(msg[:300])}</code>\n"
                                    f"⏱ <b>Время попытки:</b> <code>{heal_time}</code>\n"
                                    f"⚙️ <b>Режим:</b> <code>{status['mode'].upper()}</code>"
                                    "</blockquote>\n\n"
                                    "❗️ <b>Требуется ручное вмешательство в консоли управления!</b>"
                                )
                                fail_kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [
                                        InlineKeyboardButton(text="🔄 Повторить запуск", callback_data="proc_restart"),
                                        InlineKeyboardButton(text="📋 Журнал логов", callback_data="menu_logs")
                                    ]
                                ])
                                await self._notify_admins(bot, fail_text, reply_markup=fail_kb)
                        else:
                            await self._notify_admins(bot, alert_text, reply_markup=crash_kb)

                    # Случай 2: Бот вернулся в строй
                    elif self._last_state is False and is_currently_running:
                        logger.info("🟢 Основной бот восстановил работу.")
                        rec_metrics = get_system_metrics()
                        rec_time = datetime.now(BOT_TZ).strftime("%d.%m.%Y · %H:%M:%S")
                        recovery_text = (
                            "🟢 <b>[СЛУЖБА ВОССТАНОВИЛА РАБОТУ]</b>\n"
                            "──────────────────────────────\n"
                            "⚡️ <b>Основной бот aitu-schedule-bot снова онлайн и обрабатывает запросы!</b>\n\n"
                            "<blockquote>"
                            f"🆔 <b>PID процесса:</b> <code>{status['pid'] or 'active'}</code>\n"
                            f"📦 <b>Память процесса:</b> <code>{status['memory_mb']} МБ</code> | CPU: <code>{status['cpu_percent']}%</code>\n"
                            f"⚙️ <b>Режим службы:</b> <code>{status['mode'].upper()}</code>\n"
                            f"⏱ <b>Время фиксации:</b> <code>{rec_time}</code>\n"
                            f"🖥 <b>Сервер:</b> RAM <code>{rec_metrics['ram_used_gb']}/{rec_metrics['ram_total_gb']} ГБ</code>"
                            "</blockquote>"
                        )
                        rec_kb = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(text="📊 Дашборд", callback_data="dashboard"),
                                InlineKeyboardButton(text="🔄 Проверить статус", callback_data="proc_status_refresh")
                            ]
                        ])
                        await self._notify_admins(bot, recovery_text, reply_markup=rec_kb)

                self._last_state = is_currently_running

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле Watchdog: {e}")

            await asyncio.sleep(WATCHDOG_CHECK_INTERVAL)


watchdog = BotWatchdog()
