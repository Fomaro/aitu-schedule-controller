import asyncio
import logging
from aiogram import Bot
from config import (
    SUPERADMIN_IDS,
    WATCHDOG_ENABLED,
    WATCHDOG_CHECK_INTERVAL,
    AUTO_RESTART_ON_CRASH
)
from services.supervisor import supervisor

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

    async def _notify_admins(self, bot: Bot, text: str):
        """Отправляет уведомление всем супер-администраторам."""
        for admin_id in SUPERADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    disable_web_page_preview=True
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
                        alert_text = (
                            "🚨 <b>[КРИТИЧЕСКИЙ СБОЙ]</b>\n\n"
                            "⚠️ <b>Основной бот aitu-schedule-bot упал или остановлен!</b>\n\n"
                            f"▫️ Режим: <code>{status['mode']}</code>\n"
                            f"▫️ Время падения: <code>{status.get('last_heartbeat', 'сейчас')}</code>\n"
                        )

                        if AUTO_RESTART_ON_CRASH:
                            alert_text += "\n⏳ <i>Сторожевой сервис пытается выполнить авто-восстановление...</i>"
                            await self._notify_admins(bot, alert_text)

                            await asyncio.sleep(2.0)
                            ok, msg = await supervisor.restart()
                            if ok:
                                heal_text = (
                                    "✅ <b>[АВТО-ВОССТАНОВЛЕНИЕ УСПЕШНО]</b>\n\n"
                                    "⚡️ Основной бот был автоматически перезапущен сторожевым сервисом (Watchdog)!"
                                )
                                await self._notify_admins(bot, heal_text)
                            else:
                                fail_text = (
                                    "❌ <b>[ОШИБКА АВТО-ВОССТАНОВЛЕНИЯ]</b>\n\n"
                                    f"Не удалось перезапустить бота автоматически: {msg}\n"
                                    "Требуется ручное вмешательство в панели управления!"
                                )
                                await self._notify_admins(bot, fail_text)
                        else:
                            await self._notify_admins(bot, alert_text)

                    # Случай 2: Бот вернулся в строй
                    elif self._last_state is False and is_currently_running:
                        logger.info("🟢 Основной бот восстановил работу.")
                        recovery_text = (
                            "🟢 <b>[СЛУЖБА ВОССТАНОВЛЕНА]</b>\n\n"
                            "Основной бот aitu-schedule-bot снова онлайн и обрабатывает запросы!"
                        )
                        await self._notify_admins(bot, recovery_text)

                self._last_state = is_currently_running

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле Watchdog: {e}")

            await asyncio.sleep(WATCHDOG_CHECK_INTERVAL)


watchdog = BotWatchdog()
