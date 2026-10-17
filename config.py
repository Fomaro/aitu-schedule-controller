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
resolved_target: Path | None = None

if raw_target_dir:
    p = Path(raw_target_dir).expanduser()
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    if p.exists():
        resolved_target = p

if resolved_target is None:
    # Поиск существующей директории бота (VPS или локально)
    candidates = [
        Path("/opt/aitu-schedule-bot"),
        BASE_DIR.parent / "aitu-schedule-bot",
        BASE_DIR.parent / "aitu-schudele",
        Path("/opt/aitu-schudele"),
    ]
    for cand in candidates:
        if cand.exists():
            resolved_target = cand.resolve()
            break

if resolved_target is None:
    # Fallback по умолчанию
    if sys.platform == "win32":
        resolved_target = (BASE_DIR.parent / "aitu-schudele").resolve()
    else:
        resolved_target = Path("/opt/aitu-schedule-bot")

TARGET_BOT_DIR = resolved_target

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
