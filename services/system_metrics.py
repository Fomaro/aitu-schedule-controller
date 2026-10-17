import os
import sys
import platform
import time
from datetime import datetime
import psutil
from config import BOT_TZ


def get_system_metrics() -> dict:
    """
    Возвращает словарь с ключевыми метриками сервера (CPU, RAM, диск, ОС, аптайм).
    """
    # CPU
    cpu_usage = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count(logical=True)

    # RAM
    ram = psutil.virtual_memory()
    ram_total_gb = ram.total / (1024 ** 3)
    ram_used_gb = ram.used / (1024 ** 3)
    ram_percent = ram.percent

    # Disk
    disk = psutil.disk_usage("/") if os.name != "nt" else psutil.disk_usage("C:\\")
    disk_total_gb = disk.total / (1024 ** 3)
    disk_free_gb = disk.free / (1024 ** 3)
    disk_percent = disk.percent

    # System Uptime
    boot_time = psutil.boot_time()
    uptime_seconds = int(time.time() - boot_time)
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    uptime_str = f"{days}д {hours}ч {minutes}м" if days > 0 else f"{hours}ч {minutes}м"

    return {
        "os": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
        "cpu_usage": cpu_usage,
        "cpu_cores": cpu_cores,
        "ram_total_gb": round(ram_total_gb, 1),
        "ram_used_gb": round(ram_used_gb, 1),
        "ram_percent": ram_percent,
        "disk_total_gb": round(disk_total_gb, 1),
        "disk_free_gb": round(disk_free_gb, 1),
        "disk_percent": disk_percent,
        "system_uptime": uptime_str,
        "server_time": datetime.now(BOT_TZ).strftime("%d.%m.%Y %H:%M:%S")
    }
