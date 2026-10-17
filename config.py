import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Токен контроллера
CONTROLLER_BOT_TOKEN = os.getenv("CONTROLLER_BOT_TOKEN", "").strip()

# Список супер-администраторов
DEFAULT_SUPERADMIN_IDS = {1019252177, 792569339}
SUPERADMIN_IDS: set[int] = set(DEFAULT_SUPERADMIN_IDS)

raw_superadmin_ids = os.getenv("SUPERADMIN_IDS", "").strip()
if raw_superadmin_ids:
    for part in raw_superadmin_ids.replace(";", ",").replace(" ", ",").split(","):
        p = part.strip()
        if p.isdigit():
            SUPERADMIN_IDS.add(int(p))

# Путь к каталогу целевого бота (aitu-schedule-bot)
raw_target_dir = os.getenv("TARGET_BOT_DIR", "").strip()
if not raw_target_dir:
    # По умолчанию ищем соседнюю папку с проектом расписания
    candidate_1 = BASE_DIR.parent / "aitu-schudele"
    candidate_2 = BASE_DIR.parent / "aitu-schedule-bot"
    candidate_3 = Path("/opt/aitu-schedule-bot")
    if candidate_1.exists():
        TARGET_BOT_DIR = candidate_1.resolve()
    elif candidate_2.exists():
        TARGET_BOT_DIR = candidate_2.resolve()
    elif candidate_3.exists():
        TARGET_BOT_DIR = candidate_3.resolve()
    else:
        TARGET_BOT_DIR = candidate_1.resolve()
else:
    TARGET_BOT_DIR = Path(raw_target_dir).expanduser().resolve()

# Пути к файлам целевого бота
TARGET_DB_PATH = TARGET_BOT_DIR / "schedule_bot.db"
TARGET_PID_PATH = TARGET_BOT_DIR / "bot.pid"
TARGET_STATUS_PATH = TARGET_BOT_DIR / ".bot_status.json"
TARGET_LOG_PATH = TARGET_BOT_DIR / "bot.log"

# Режим управления
RUN_MODE = os.getenv("RUN_MODE", "auto").strip().lower()
SYSTEMD_SERVICE_NAME = os.getenv("SYSTEMD_SERVICE_NAME", "aitu-bot").strip()
DOCKER_CONTAINER_NAME = os.getenv("DOCKER_CONTAINER_NAME", "aitu-schedule-bot").strip()
PROCESS_START_CMD = os.getenv("PROCESS_START_CMD", "").strip()

# Настройки Watchdog
WATCHDOG_ENABLED = os.getenv("WATCHDOG_ENABLED", "true").strip().lower() in ("true", "1", "yes")
try:
    WATCHDOG_CHECK_INTERVAL = int(os.getenv("WATCHDOG_CHECK_INTERVAL", "30"))
except ValueError:
    WATCHDOG_CHECK_INTERVAL = 30

AUTO_RESTART_ON_CRASH = os.getenv("AUTO_RESTART_ON_CRASH", "true").strip().lower() in ("true", "1", "yes")

# Опциональный токен целевого бота
TARGET_BOT_TOKEN = os.getenv("TARGET_BOT_TOKEN", "").strip()

# Временная зона
TIMEZONE_NAME = os.getenv("TIMEZONE", "Europe/Moscow").strip()
try:
    BOT_TZ = ZoneInfo(TIMEZONE_NAME)
except Exception:
    BOT_TZ = ZoneInfo("Europe/Moscow")
