import os
import asyncio
import logging
from config import (
    TARGET_LOG_PATH,
    SYSTEMD_SERVICE_NAME,
    DOCKER_CONTAINER_NAME
)
from services.supervisor import supervisor

logger = logging.getLogger(__name__)


class LogReaderService:
    """
    Сервис чтения и фильтрации журналов логов целевого бота.
    """

    async def get_logs(self, limit: int = 40, level_filter: str = "all") -> str:
        """
        Возвращает последние строки логов с опциональной фильтрацией по уровню.
        level_filter: 'all', 'error', 'warning'
        """
        raw_lines = await self._fetch_raw_log_lines(limit * 2)

        if not raw_lines:
            return "<i>Журнал логов пуст или файл логов ещё не создан.</i>"

        # Фильтрация
        filtered = []
        for line in raw_lines:
            l_lower = line.lower()
            if level_filter == "error":
                if any(k in l_lower for k in ("error", "critical", "exception", "traceback", "failed")):
                    filtered.append(line)
            elif level_filter == "warning":
                if any(k in l_lower for k in ("warning", "warn", "retryafter")):
                    filtered.append(line)
            else:
                filtered.append(line)

        # Берём последние limit строк
        selected = filtered[-limit:]
        if not selected:
            return f"<i>Нет записей в логах с фильтром [{level_filter.upper()}].</i>"

        return "\n".join(selected)

    async def _fetch_raw_log_lines(self, count: int) -> list[str]:
        mode = supervisor.effective_mode

        if mode == "systemd":
            try:
                proc = await asyncio.create_subprocess_exec(
                    "journalctl", "-u", SYSTEMD_SERVICE_NAME, f"-n{count}", "--no-pager",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                text = stdout.decode(errors="replace").strip()
                return text.split("\n") if text else []
            except Exception as e:
                logger.debug(f"Ошибка чтения journalctl: {e}")

        elif mode == "docker":
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "logs", f"--tail={count}", DOCKER_CONTAINER_NAME,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                text = (stdout.decode(errors="replace") + "\n" + stderr.decode(errors="replace")).strip()
                return text.split("\n") if text else []
            except Exception as e:
                logger.debug(f"Ошибка чтения docker logs: {e}")

        # Чтение из файла bot.log
        if TARGET_LOG_PATH.exists():
            try:
                with open(TARGET_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    return [line.rstrip("\r\n") for line in lines[-count:]]
            except Exception as e:
                logger.debug(f"Ошибка чтения файла логов: {e}")

        return []


log_reader = LogReaderService()
