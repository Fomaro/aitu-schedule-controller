import os
import sys
import json
import signal
import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path
import psutil

from config import (
    TARGET_BOT_DIR,
    TARGET_PID_PATH,
    TARGET_STATUS_PATH,
    TARGET_LOG_PATH,
    RUN_MODE,
    SYSTEMD_SERVICE_NAME,
    DOCKER_CONTAINER_NAME,
    PROCESS_START_CMD,
    BOT_TZ
)

logger = logging.getLogger(__name__)


class BotSupervisor:
    """
    Управляет жизненным циклом и мониторингом процесса целевого бота (aitu-schedule-bot).
    Поддерживает режимы:
    - systemd (на Linux VPS)
    - docker (в контейнерах)
    - process (прямой запуск через subprocess/PID)
    """

    def __init__(self):
        self.effective_mode = self._detect_mode()
        logger.info(f"Инициализирован BotSupervisor в режиме: {self.effective_mode.upper()}")

    def _detect_mode(self) -> str:
        """Определяет эффективный режим управления."""
        if RUN_MODE in ("systemd", "docker", "process"):
            return RUN_MODE

        # Автоматическое определение
        if os.name != "nt":
            # Проверяем наличие systemctl
            try:
                res = subprocess.run(
                    ["systemctl", "status", SYSTEMD_SERVICE_NAME],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if res.returncode in (0, 3):  # 0=active, 3=inactive (но служба существует)
                    return "systemd"
            except Exception:
                pass

            # Проверяем наличие docker
            try:
                res = subprocess.run(
                    ["docker", "inspect", DOCKER_CONTAINER_NAME],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if res.returncode == 0:
                    return "docker"
            except Exception:
                pass

        return "process"

    async def get_status(self) -> dict:
        """
        Возвращает расширенную информацию о текущем состоянии целевого бота.
        """
        status_info = {
            "mode": self.effective_mode,
            "is_running": False,
            "status_text": "Остановлен 🔴",
            "pid": None,
            "uptime": "—",
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "heartbeat_status": "unknown",
            "last_heartbeat": "—",
            "target_dir": str(TARGET_BOT_DIR),
            "details": ""
        }

        # 1. Читаем heartbeat из файла статуса
        if TARGET_STATUS_PATH.exists():
            try:
                async with asyncio.Lock():
                    with open(TARGET_STATUS_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    status_info["heartbeat_status"] = data.get("status", "unknown")
                    started_at_str = data.get("started_at")
                    if started_at_str:
                        status_info["last_heartbeat"] = started_at_str[:19].replace("T", " ")
            except Exception as e:
                logger.debug(f"Не удалось прочитать .bot_status.json: {e}")

        # 2. Проверяем в зависимости от режима
        if self.effective_mode == "systemd":
            await self._check_systemd_status(status_info)
        elif self.effective_mode == "docker":
            await self._check_docker_status(status_info)
        else:
            await self._check_process_status(status_info)

        return status_info

    async def _check_systemd_status(self, status_info: dict):
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "is-active", SYSTEMD_SERVICE_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            state = stdout.decode().strip()
            if state == "active":
                status_info["is_running"] = True
                status_info["status_text"] = "В сети (systemd) 🟢"
            else:
                status_info["is_running"] = False
                status_info["status_text"] = f"Остановлен ({state}) 🔴"

            # Пытаемся получить MainPID
            pid_proc = await asyncio.create_subprocess_exec(
                "systemctl", "show", SYSTEMD_SERVICE_NAME, "--property=MainPID",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            pid_out, _ = await pid_proc.communicate()
            pid_str = pid_out.decode().strip().replace("MainPID=", "")
            if pid_str.isdigit() and int(pid_str) > 0:
                pid = int(pid_str)
                status_info["pid"] = pid
                self._enrich_process_metrics(pid, status_info)
        except Exception as e:
            status_info["details"] = str(e)

    async def _check_docker_status(self, status_info: dict):
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", "-f", "{{.State.Running}}", DOCKER_CONTAINER_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            is_run = stdout.decode().strip().lower() == "true"
            status_info["is_running"] = is_run
            status_info["status_text"] = "В сети (Docker) 🟢" if is_run else "Остановлен (Docker) 🔴"
        except Exception as e:
            status_info["details"] = str(e)

    async def _check_process_status(self, status_info: dict):
        pid = None
        if TARGET_PID_PATH.exists():
            try:
                raw_pid = TARGET_PID_PATH.read_text(encoding="utf-8").strip()
                if raw_pid.isdigit():
                    pid = int(raw_pid)
            except Exception:
                pass

        if pid and psutil.pid_exists(pid):
            try:
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    status_info["is_running"] = True
                    status_info["pid"] = pid
                    status_info["status_text"] = "В сети · Онлайн 🟢"
                    self._enrich_process_metrics(pid, status_info)
                    return
            except Exception:
                pass

        status_info["is_running"] = False
        status_info["status_text"] = "Остановлен 🔴"

    def _enrich_process_metrics(self, pid: int, status_info: dict):
        """Обогащает информацию метриками psutil (CPU, RAM, Uptime)."""
        try:
            p = psutil.Process(pid)
            with p.oneshot():
                status_info["cpu_percent"] = round(p.cpu_percent(interval=None), 1)
                mem = p.memory_info()
                status_info["memory_mb"] = round(mem.rss / (1024 * 1024), 1)
                
                # Uptime
                create_dt = datetime.fromtimestamp(p.create_time(), tz=BOT_TZ)
                delta = datetime.now(BOT_TZ) - create_dt
                total_seconds = int(delta.total_seconds())
                days, rem = divmod(total_seconds, 86400)
                hours, rem = divmod(rem, 3600)
                minutes, _ = divmod(rem, 60)
                parts = []
                if days > 0:
                    parts.append(f"{days}д")
                if hours > 0 or days > 0:
                    parts.append(f"{hours}ч")
                parts.append(f"{minutes}м")
                status_info["uptime"] = " ".join(parts) if parts else "< 1м"
        except Exception:
            pass

    async def start(self) -> tuple[bool, str]:
        """Запускает основной бот."""
        curr = await self.get_status()
        if curr["is_running"]:
            return False, "⚠️ Бот уже запущен и работает!"

        if self.effective_mode == "systemd":
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "start", SYSTEMD_SERVICE_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, "✅ Служба Systemd успешно запущена!"
            return False, f"❌ Ошибка Systemd: {stderr.decode()}"

        elif self.effective_mode == "docker":
            proc = await asyncio.create_subprocess_exec(
                "docker", "start", DOCKER_CONTAINER_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, "✅ Docker контейнер успешно запущен!"
            return False, f"❌ Ошибка Docker: {stderr.decode()}"

        else:
            # Subprocess
            cmd = self._resolve_start_command()
            try:
                log_file = open(TARGET_LOG_PATH, "a", encoding="utf-8")
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(TARGET_BOT_DIR),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    shell=True if os.name == "nt" else False
                )
                TARGET_PID_PATH.write_text(str(proc.pid), encoding="utf-8")
                return True, f"✅ Процесс бота запущен в фоне (PID: {proc.pid})!"
            except Exception as e:
                logger.error(f"Ошибка при запуске бота: {e}")
                return False, f"❌ Ошибка при запуске: {e}"

    async def stop(self) -> tuple[bool, str]:
        """Останавливает основной бот."""
        curr = await self.get_status()
        if not curr["is_running"]:
            return False, "ℹ️ Бот уже остановлен."

        if self.effective_mode == "systemd":
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "stop", SYSTEMD_SERVICE_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, "✅ Служба Systemd успешно остановлена."
            return False, f"❌ Ошибка: {stderr.decode()}"

        elif self.effective_mode == "docker":
            proc = await asyncio.create_subprocess_exec(
                "docker", "stop", DOCKER_CONTAINER_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, "✅ Docker контейнер успешно остановлен."
            return False, f"❌ Ошибка: {stderr.decode()}"

        else:
            pid = curr.get("pid")
            if not pid:
                return False, "❌ Не найден PID запущенного процесса."
            try:
                p = psutil.Process(pid)
                p.terminate()
                try:
                    p.wait(timeout=5)
                except psutil.TimeoutExpired:
                    p.kill()
                if TARGET_PID_PATH.exists():
                    try:
                        TARGET_PID_PATH.unlink()
                    except Exception:
                        pass
                return True, f"✅ Процесс (PID: {pid}) успешно остановлен."
            except Exception as e:
                return False, f"❌ Ошибка при остановке: {e}"

    async def restart(self) -> tuple[bool, str]:
        """Перезапускает целевой бот."""
        if self.effective_mode == "systemd":
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "restart", SYSTEMD_SERVICE_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, "⚡️ Служба Systemd успешно перезапущена!"
            return False, f"❌ Ошибка перезапуска: {stderr.decode()}"

        elif self.effective_mode == "docker":
            proc = await asyncio.create_subprocess_exec(
                "docker", "restart", DOCKER_CONTAINER_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, "⚡️ Docker контейнер успешно перезапущен!"
            return False, f"❌ Ошибка перезапуска: {stderr.decode()}"

        else:
            stop_ok, stop_msg = await self.stop()
            await asyncio.sleep(1.0)
            start_ok, start_msg = await self.start()
            if start_ok:
                return True, "⚡️ Процесс бота успешно перезапущен!"
            return False, f"⚠️ Не удалось перезапустить: {start_msg}"

    async def kill(self) -> tuple[bool, str]:
        """Принудительно убивает процесс целевого бота (SIGKILL)."""
        curr = await self.get_status()
        pid = curr.get("pid")
        if not pid or not psutil.pid_exists(pid):
            return False, "ℹ️ Процесс не найден или уже завершён."

        try:
            p = psutil.Process(pid)
            p.kill()
            if TARGET_PID_PATH.exists():
                try:
                    TARGET_PID_PATH.unlink()
                except Exception:
                    pass
            return True, f"💀 Процесс (PID: {pid}) принудительно завершён."
        except Exception as e:
            return False, f"❌ Ошибка при kill: {e}"

    def _resolve_start_command(self) -> list[str]:
        """Определяет исполняемую команду запуска для режима process."""
        if PROCESS_START_CMD:
            return PROCESS_START_CMD.split()

        # Проверяем venv целевого бота
        venv_py_win = TARGET_BOT_DIR / "venv" / "Scripts" / "python.exe"
        venv_py_linux = TARGET_BOT_DIR / "venv" / "bin" / "python"
        bot_file = TARGET_BOT_DIR / "bot.py"

        if venv_py_win.exists():
            return [str(venv_py_win), str(bot_file)]
        if venv_py_linux.exists():
            return [str(venv_py_linux), str(bot_file)]
        return [sys.executable, str(bot_file)]


supervisor = BotSupervisor()
