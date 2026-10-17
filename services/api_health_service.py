import time
import logging
import aiohttp
from datetime import datetime
from config import BOT_TZ

logger = logging.getLogger("controller.api_health")

DEFAULT_PUBLIC_URL = "https://72-4-67-12.sslip.io"
CANDIDATE_LOCAL_PORTS = (8089, 8080, 8000, 8081)


class ApiHealthService:
    """
    Сервис мониторинга и валидации REST API и Telegram Mini App.
    Проверяет локальный HTTP-сервер бота, публичный HTTPS-шлюз и целостность ключевых эндпоинтов.
    """

    def __init__(self, public_base_url: str = DEFAULT_PUBLIC_URL):
        self.public_base_url = public_base_url.rstrip("/")

    async def get_quick_status(self) -> dict:
        """
        Быстрая проверка жизнедеятельности API (для сводки в Dashboard).
        Выполняется с минимальным таймаутом (800 мс).
        """
        for port in CANDIDATE_LOCAL_PORTS:
            url = f"http://127.0.0.1:{port}/api/health"
            t0 = time.perf_counter()
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=0.8)) as session:
                    async with session.get(url) as resp:
                        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                        if resp.status == 200:
                            data = await resp.json()
                            version = data.get("version", "v3.x")
                            return {
                                "is_online": True,
                                "icon": "🟢",
                                "text": f"200 OK ({version})",
                                "port": port,
                                "latency_ms": latency_ms,
                                "version": version
                            }
                        else:
                            return {
                                "is_online": False,
                                "icon": "⚠️",
                                "text": f"HTTP {resp.status}",
                                "port": port,
                                "latency_ms": latency_ms,
                                "version": "unknown"
                            }
            except Exception:
                continue

        return {
            "is_online": False,
            "icon": "🔴",
            "text": "Offline (порт недоступен)",
            "port": None,
            "latency_ms": 0,
            "version": "—"
        }

    async def check_full_health(self) -> dict:
        """
        Полная диагностика всех API-эндпоинтов, Caddy SSL-шлюза и SPA Mini App.
        """
        results = {
            "timestamp": datetime.now(BOT_TZ).strftime("%d.%m.%Y · %H:%M:%S"),
            "is_healthy": True,
            "active_port": None,
            "local_check": None,
            "public_check": None,
            "endpoints": [],
            "total_passed": 0,
            "total_tested": 0
        }

        timeout = aiohttp.ClientTimeout(total=2.5)

        # 1. Поиск активного локального порта
        active_local_port = None
        for port in CANDIDATE_LOCAL_PORTS:
            t0 = time.perf_counter()
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(f"http://127.0.0.1:{port}/api/health") as resp:
                        lat = round((time.perf_counter() - t0) * 1000, 1)
                        if resp.status == 200:
                            data = await resp.json()
                            active_local_port = port
                            results["active_port"] = port
                            results["local_check"] = {
                                "status": 200,
                                "port": port,
                                "latency_ms": lat,
                                "version": data.get("version", "v3.x"),
                                "service": data.get("service", "AITU Schedule API")
                            }
                            break
            except Exception:
                continue

        if not results["local_check"]:
            results["local_check"] = {
                "status": 0,
                "port": None,
                "latency_ms": 0,
                "error": "Ни один локальный порт не ответил (8089, 8080, 8000, 8081)"
            }
            results["is_healthy"] = False

        # 2. Проверка публичного шлюза Caddy (HTTPS)
        base_api_url = f"http://127.0.0.1:{active_local_port}" if active_local_port else self.public_base_url

        t0 = time.perf_counter()
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.public_base_url}/api/health") as resp:
                    lat = round((time.perf_counter() - t0) * 1000, 1)
                    if resp.status == 200:
                        data = await resp.json()
                        results["public_check"] = {
                            "status": 200,
                            "latency_ms": lat,
                            "version": data.get("version", "v3.x"),
                            "ssl_ok": True
                        }
                    else:
                        results["public_check"] = {
                            "status": resp.status,
                            "latency_ms": lat,
                            "error": f"HTTP {resp.status}"
                        }
                        results["is_healthy"] = False
        except Exception as e:
            results["public_check"] = {
                "status": 0,
                "latency_ms": 0,
                "error": str(e)
            }
            results["is_healthy"] = False

        # 3. Комплексная проверка эндпоинтов (через локальный сокет для скорости и надежности)
        test_cases = [
            {
                "path": "/api/health",
                "label": "Healthcheck",
                "validate": lambda d: d.get("status") == "ok",
                "extract": lambda d: f"{d.get('version', 'v3.x')} · {d.get('status', 'ok')}"
            },
            {
                "path": "/api/groups",
                "label": "Реестр групп",
                "validate": lambda d: "groups" in d and len(d["groups"]) > 0,
                "extract": lambda d: f"{d.get('total', len(d.get('groups', [])))} групп колледжа"
            },
            {
                "path": "/api/schedule?group=9ПО-43к",
                "label": "Расписание занятий",
                "validate": lambda d: "days" in d and len(d["days"]) > 0,
                "extract": lambda d: f"Группа {d.get('group', '9ПО-43к')} ({d.get('course', 4)} курс)"
            },
            {
                "path": "/api/replacements",
                "label": "Синхронизация замен",
                "validate": lambda d: "replacements" in d and isinstance(d["replacements"], list),
                "extract": lambda d: f"{d.get('total', len(d.get('replacements', [])))} активных замен"
            },
            {
                "path": "/api/tournaments",
                "label": "Киберспорт и турниры",
                "validate": lambda d: "tournaments" in d and isinstance(d["tournaments"], list),
                "extract": lambda d: f"{len(d.get('tournaments', []))} турниров в БД"
            },
            {
                "path": "/",
                "url": f"{self.public_base_url}/",
                "label": "Mini App Web Bundle",
                "validate": lambda text: "root" in text,
                "extract": lambda text: "Vite SPA сборка активна",
                "is_html": True
            }
        ]

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for tc in test_cases:
                results["total_tested"] += 1
                target_url = tc.get("url") or f"{base_api_url}{tc['path']}"
                t_start = time.perf_counter()
                try:
                    async with session.get(target_url) as resp:
                        lat_ms = round((time.perf_counter() - t_start) * 1000, 1)
                        if resp.status == 200:
                            if tc.get("is_html"):
                                body = await resp.text()
                                is_ok = tc["validate"](body)
                                details = tc["extract"](body) if is_ok else "HTML некорректен"
                            else:
                                body = await resp.json()
                                is_ok = tc["validate"](body)
                                details = tc["extract"](body) if is_ok else "Невалидная структура JSON"

                            if is_ok:
                                results["total_passed"] += 1
                                results["endpoints"].append({
                                    "path": tc["path"],
                                    "label": tc["label"],
                                    "status": 200,
                                    "latency_ms": lat_ms,
                                    "is_ok": True,
                                    "details": details
                                })
                            else:
                                results["is_healthy"] = False
                                results["endpoints"].append({
                                    "path": tc["path"],
                                    "label": tc["label"],
                                    "status": 200,
                                    "latency_ms": lat_ms,
                                    "is_ok": False,
                                    "details": f"Ошибка валидации: {details}"
                                })
                        else:
                            results["is_healthy"] = False
                            results["endpoints"].append({
                                "path": tc["path"],
                                "label": tc["label"],
                                "status": resp.status,
                                "latency_ms": lat_ms,
                                "is_ok": False,
                                "details": f"HTTP {resp.status}"
                            })
                except Exception as e:
                    results["is_healthy"] = False
                    results["endpoints"].append({
                        "path": tc["path"],
                        "label": tc["label"],
                        "status": 0,
                        "latency_ms": 0,
                        "is_ok": False,
                        "details": f"Сетевая ошибка: {str(e)[:35]}"
                    })

        return results

    def format_report_text(self, res: dict) -> str:
        """
        Форматирует детальный диагностический отчёт в формате Telegram HTML.
        """
        passed = res["total_passed"]
        total = res["total_tested"]
        is_healthy = res["is_healthy"] and passed == total

        overall_badge = "🟢 ВСЕ СИСТЕМЫ ИСПРАВНЫ" if is_healthy else "⚠️ ВЫЯВЛЕНЫ ОТКЛОНЕНИЯ"

        # Локальный сокет
        loc = res["local_check"]
        if loc and loc.get("status") == 200:
            local_line = f"🟢 <b>127.0.0.1:{loc['port']}</b> (200 OK · {loc['latency_ms']} мс · {loc['version']})"
        else:
            local_line = f"🔴 <b>Локальный сокет:</b> {loc.get('error', 'Недоступен')}"

        # Публичный шлюз
        pub = res["public_check"]
        if pub and pub.get("status") == 200:
            public_line = f"🟢 <b>{self.public_base_url}</b> (200 OK · SSL OK · {pub['latency_ms']} мс)"
        else:
            public_line = f"⚠️ <b>Публичный HTTPS:</b> {pub.get('error', 'Ошибка шлюза')}"

        # Список эндпоинтов
        ep_lines = []
        for ep in res["endpoints"]:
            icon = "✅" if ep["is_ok"] else "❌"
            ep_lines.append(
                f"{icon} <code>{ep['path']}</code> — <b>{ep['details']}</b> ({ep['latency_ms']} мс)"
            )

        report = (
            f"🩺 <b>РЕВИЗИЯ И HEALTH-CHECK REST API</b>\n"
            f"────────────────────────\n"
            f"▫️ Статус: <b>{overall_badge}</b>\n"
            f"▫️ Проверено: <b>{passed} из {total}</b> тестов успешно\n"
            f"▫️ Время проверки: <code>{res['timestamp']}</code>\n\n"
            f"🌐 <b>Сетевые шлюзы:</b>\n"
            f"▫️ Локально: {local_line}\n"
            f"▫️ Публично: {public_line}\n\n"
            f"📡 <b>Ключевые эндпоинты API & Mini App:</b>\n" +
            "\n".join(ep_lines) +
            "\n\n────────────────────────\n"
            "💡 <i>Все маршруты REST API поддерживаются веб-сервером на порту 8089 и проксируются Caddy с автоматическим HTTPS.</i>"
        )
        return report


api_health_service = ApiHealthService()
