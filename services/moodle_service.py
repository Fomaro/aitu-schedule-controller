import os
import re
import sys
import json
import asyncio
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any
import aiohttp
from bs4 import BeautifulSoup
import docx

from config import (
    MOODLE_URL,
    MOODLE_USERNAME,
    MOODLE_PASSWORD,
    MOODLE_AUTO_SYNC,
    MOODLE_START_HOUR,
    MOODLE_END_HOUR,
    MOODLE_STATE_FILE,
    BOT_TZ,
    SUPERADMIN_IDS,
    BASE_DIR
)
from services.db_service import db_service

logger = logging.getLogger("controller.moodle")

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
}


class MoodleSyncService:
    """
    Интеллектуальный сервис автоматической синхронизации с порталом do.eduhouse.ru.
    Авторизуется на сайте, сканирует публикации, скачивает официальные приказы о заменах (.docx)
    и расписания (.xls/.xlsx), парсит их и вносит в общую базу данных.
    """

    def __init__(self):
        self.base_url = MOODLE_URL.rstrip("/")
        self.username = MOODLE_USERNAME
        self.password = MOODLE_PASSWORD
        self._scheduler_task: asyncio.Task | None = None
        self._is_running = False

    def load_state(self) -> dict[str, Any]:
        """Загружает состояние предыдущих проверок."""
        if MOODLE_STATE_FILE.exists():
            try:
                with open(MOODLE_STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Ошибка чтения {MOODLE_STATE_FILE}: {e}")
        return {
            "last_check_at": None,
            "last_status": "never",
            "last_error": None,
            "processed_files": {},  # filename/url: applied_date
            "last_applied_doc": None
        }

    def save_state(self, state: dict[str, Any]) -> None:
        """Сохраняет состояние проверок."""
        try:
            with open(MOODLE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Ошибка записи {MOODLE_STATE_FILE}: {e}")

    async def fetch_available_documents(self) -> dict[str, Any]:
        """
        Авторизуется на do.eduhouse.ru и собирает все ссылки на файлы замен и расписаний.
        """
        result = {
            "success": False,
            "error": None,
            "replacements": [],
            "schedules": [],
            "user_full_name": None
        }

        if not self.username or not self.password:
            result["error"] = "Логин или пароль Moodle не настроены (MOODLE_USERNAME / MOODLE_PASSWORD)."
            return result

        login_url = f"{self.base_url}/login/index.php"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        cookie_jar = aiohttp.CookieJar(unsafe=True)
        timeout = aiohttp.ClientTimeout(total=25)

        try:
            async with aiohttp.ClientSession(cookie_jar=cookie_jar, headers=headers, timeout=timeout) as session:
                # 1. Получаем страницу входа и парсим logintoken
                async with session.get(login_url) as resp:
                    if resp.status != 200:
                        result["error"] = f"Страница логина недоступна: HTTP {resp.status}"
                        return result
                    login_html = await resp.text()

                soup_login = BeautifulSoup(login_html, "html.parser")
                token_input = soup_login.find("input", {"name": "logintoken"})
                logintoken = token_input.get("value", "") if token_input else ""

                # 2. Выполняем POST логина
                post_data = {
                    "username": self.username,
                    "password": self.password,
                    "logintoken": logintoken
                }
                async with session.post(login_url, data=post_data, allow_redirects=True) as post_resp:
                    post_html = await post_resp.text()

                if "login/index.php" in str(post_resp.url) or "неверный логин" in post_html.lower():
                    result["error"] = "Ошибка авторизации: неверный логин или пароль do.eduhouse.ru"
                    return result

                # Извлекаем имя пользователя
                user_match = re.search(r'class="usertext">([^<]+)<', post_html)
                if user_match:
                    result["user_full_name"] = user_match.group(1).strip()

                # 3. Сканируем главную страницу на наличие прикрепленных файлов
                # В Moodle файлы замен и расписаний обычно находятся в блоках объявлений
                main_soup = BeautifulSoup(post_html, "html.parser")
                links = main_soup.find_all("a", href=True)

                seen_urls = set()
                for a in links:
                    href = a["href"]
                    if href in seen_urls:
                        continue

                    raw_text = a.get_text(separator=" ", strip=True)
                    clean_text = re.sub(r'\s+', ' ', raw_text)

                    # Файлы замен (.docx)
                    if ".docx" in href.lower() or "замен" in clean_text.lower():
                        if "pluginfile.php" in href or ".docx" in href:
                            seen_urls.add(href)
                            # Пытаемся извлечь дату из имени файла или текста
                            date_str = self._extract_date_str(clean_text, href)
                            result["replacements"].append({
                                "title": clean_text or Path(href.split("?")[0]).name,
                                "url": href,
                                "date_str": date_str,
                                "filename": Path(href.split("?")[0]).name
                            })

                    # Файлы расписания (.xls / .xlsx)
                    elif (".xls" in href.lower() or ".xlsx" in href.lower()) and ("расп" in clean_text.lower() or "курс" in clean_text.lower()):
                        seen_urls.add(href)
                        result["schedules"].append({
                            "title": clean_text or Path(href.split("?")[0]).name,
                            "url": href,
                            "filename": Path(href.split("?")[0]).name
                        })

                # Сортируем замены: файлы с датами помещаем наверх
                result["replacements"].sort(key=lambda x: x.get("date_str") or "", reverse=True)
                result["success"] = True

        except Exception as e:
            logger.error(f"Ошибка при подключении к Moodle: {e}")
            result["error"] = str(e)

        return result

    def _extract_date_str(self, text: str, url: str) -> str | None:
        """Извлекает дату из строки вида '19.10.docx' или 'на 19 октября'."""
        combined = f"{text} {url}"
        # Формат: 19.10.2026 или 19.10
        m1 = re.search(r'\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b', combined)
        if m1:
            d = int(m1.group(1))
            m = int(m1.group(2))
            y = int(m1.group(3)) if m1.group(3) else datetime.now(BOT_TZ).year
            if y < 100:
                y += 2000
            try:
                return f"{y:04d}-{m:02d}-{d:02d}"
            except Exception:
                pass

        # Формат: 19 октября
        m2 = re.search(r'(\d{1,2})\s+([а-яё]+)', combined.lower())
        if m2:
            d = int(m2.group(1))
            m_name = m2.group(2)
            if m_name in MONTHS_RU:
                y = datetime.now(BOT_TZ).year
                return f"{y:04d}-{MONTHS_RU[m_name]:02d}-{d:02d}"

        return None

    async def download_file(self, url: str, target_path: Path) -> bool:
        """Авторизуется и скачивает файл по ссылке."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        login_url = f"{self.base_url}/login/index.php"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        cookie_jar = aiohttp.CookieJar(unsafe=True)

        try:
            async with aiohttp.ClientSession(cookie_jar=cookie_jar, headers=headers) as session:
                # Вход
                async with session.get(login_url) as resp:
                    soup_login = BeautifulSoup(await resp.text(), "html.parser")
                    token_input = soup_login.find("input", {"name": "logintoken"})
                    logintoken = token_input.get("value", "") if token_input else ""

                post_data = {
                    "username": self.username,
                    "password": self.password,
                    "logintoken": logintoken
                }
                await session.post(login_url, data=post_data, allow_redirects=True)

                # Скачивание файла
                async with session.get(url, allow_redirects=True) as file_resp:
                    if file_resp.status == 200:
                        content = await file_resp.read()
                        with open(target_path, "wb") as f:
                            f.write(content)
                        return True
                    else:
                        logger.error(f"Не удалось скачать {url}: HTTP {file_resp.status}")
                        return False
        except Exception as e:
            logger.error(f"Ошибка загрузки файла {url}: {e}")
            return False

    def parse_replacement_docx(self, docx_path: Path) -> dict[str, Any]:
        """
        Высокоточный парсер официальной таблицы замен колледжа АИТУ.
        Структура таблицы:
        Группа | Пара | Снято: Дисциплина | Снято: Преподаватель | Снято: Ауд | Назначено: Дисциплина | Назначено: Преподаватель | Назначено: Ауд
        """
        doc = docx.Document(str(docx_path))
        result = {
            "date": None,
            "date_str": None,
            "parity": "Знаменатель",
            "items": [],
            "groups_affected": set(),
            "total_count": 0
        }

        # 1. Поиск даты в документе
        all_text = " ".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])
        # Также проверяем текст первой таблицы
        if doc.tables:
            for row in doc.tables[0].rows[:3]:
                all_text += " " + " ".join(c.text.strip() for c in row.cells)

        # Определение четности
        if "числитель" in all_text.lower():
            result["parity"] = "Числитель"
        elif "знаменатель" in all_text.lower():
            result["parity"] = "Знаменатель"

        # Дата: "19. 10.2026" или "19.10.2026" или "19 октября"
        d_match = re.search(r'(\d{1,2})[\s.]+(\d{1,2})[\s.]+(\d{2,4})', all_text)
        if d_match:
            d = int(d_match.group(1))
            m = int(d_match.group(2))
            y = int(d_match.group(3))
            if y < 100:
                y += 2000
            try:
                result["date"] = date(y, m, d)
                result["date_str"] = f"{y:04d}-{m:02d}-{d:02d}"
            except Exception:
                pass

        if not result["date"]:
            result["date"] = datetime.now(BOT_TZ).date()
            result["date_str"] = result["date"].strftime("%Y-%m-%d")

        # 2. Парсинг строк таблицы замен
        group_pattern = re.compile(r'\b(\d{1,2}[А-Яа-яA-Za-z]{1,4}-\d{1,3}[а-яА-Яa-zA-Z]?)\b')

        for table in doc.tables:
            rows = table.rows
            if len(rows) < 3:
                continue

            current_groups = []
            for row_idx in range(len(rows)):
                cells = [c.text.strip() for c in rows[row_idx].cells]
                if len(cells) < 4:
                    continue

                # Проверяем, не является ли строка частью шапки таблицы
                cell0_low = cells[0].lower()
                cell1_low = cells[1].lower() if len(cells) > 1 else ""
                if any(h in cell0_low or h in cell1_low for h in ["группа", "пара", "урок", "дисциплина"]):
                    current_groups = []
                    continue

                # Ищем номер(а) группы в первой ячейке (поддерживает список через запятую: "9КС-41, 9КС-42к")
                found_grps = [g.upper() for g in group_pattern.findall(cells[0])]
                if found_grps:
                    current_groups = found_grps
                
                # Если в ячейке пусто из-за объединенных строк Word, используем группы из предыдущей строки
                if not current_groups:
                    continue

                # Номер(а) пары (поддерживает "1,2" или "2,3" или "1-2")
                pair_raw = cells[1] if len(cells) > 1 else "1"
                pair_nums = [int(p.strip()) for p in re.findall(r'\b[1-6]\b', pair_raw)]
                if not pair_nums:
                    pair_nums = [1]

                # Извлечение данных: если 8 колонок (стандартный официальный приказ АИТУ)
                # Col 0: Группа, Col 1: Пара
                # Col 2: Снято Предмет, Col 3: Снято Препод, Col 4: Снято Ауд
                # Col 5: Назначено Предмет, Col 6: Назначено Препод, Col 7: Назначено Ауд
                if len(cells) >= 8:
                    canceled_subject = cells[2]
                    assigned_subject = cells[5]
                    assigned_teacher = cells[6]
                    assigned_room = cells[7]
                elif len(cells) >= 6:
                    canceled_subject = ""
                    assigned_subject = cells[2]
                    assigned_teacher = cells[3] if len(cells) > 3 else "—"
                    assigned_room = cells[4] if len(cells) > 4 else "—"
                else:
                    continue

                # Определяем тип: замена или отмена
                if assigned_subject in ("-", "—", "", "нет", "нет пары") and canceled_subject not in ("-", "—", ""):
                    action_type = "cancel"
                    subject_to_show = f"Отменено: {canceled_subject}"
                    teacher_to_show = "—"
                    room_to_show = "—"
                else:
                    action_type = "replace"
                    subject_to_show = assigned_subject if assigned_subject not in ("-", "—") else (canceled_subject or "Замена")
                    teacher_to_show = assigned_teacher if assigned_teacher not in ("-", "—") else "—"
                    room_to_show = assigned_room if assigned_room not in ("-", "—") else "—"

                for grp in current_groups:
                    for p_num in pair_nums:
                        item = {
                            "group_name": grp,
                            "pair_num": p_num,
                            "action_type": action_type,
                            "subject": subject_to_show,
                            "teacher": teacher_to_show,
                            "room": room_to_show,
                            "raw_text": " | ".join(cells)
                        }
                        result["items"].append(item)
                        result["groups_affected"].add(grp)
                        result["total_count"] += 1

        return result

    async def check_and_sync(self, bot: Any = None, force: bool = False) -> dict[str, Any]:
        """
        Основной метод проверки: авторизуется, находит свежие замены,
        скачивает и применяет в БД, оповещая супер-администраторов.
        """
        now = datetime.now(BOT_TZ)
        state = self.load_state()
        state["last_check_at"] = now.strftime("%d.%m.%Y %H:%M:%S")

        report = {
            "success": False,
            "new_replacements_found": False,
            "applied_count": 0,
            "date_str": None,
            "groups_str": "",
            "filename": None,
            "error": None
        }

        # 1. Сканируем сайт
        doc_data = await self.fetch_available_documents()
        if not doc_data.get("success"):
            state["last_status"] = "error"
            state["last_error"] = doc_data.get("error")
            self.save_state(state)
            report["error"] = doc_data.get("error")
            return report

        replacements = doc_data.get("replacements", [])
        if not replacements:
            state["last_status"] = "ok_no_files"
            self.save_state(state)
            report["success"] = True
            return report

        # 2. Берем самый свежий документ замен
        latest = replacements[0]
        url = latest["url"]
        fname = latest["filename"]
        target_date_str = latest.get("date_str") or now.strftime("%Y-%m-%d")

        # Проверяем, обрабатывали ли мы уже этот файл
        processed = state.get("processed_files", {})
        if not force and fname in processed:
            state["last_status"] = "already_processed"
            self.save_state(state)
            report["success"] = True
            report["filename"] = fname
            report["date_str"] = target_date_str
            return report

        # 3. Скачиваем файл во временную директорию
        downloads_dir = BASE_DIR / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        local_docx = downloads_dir / f"moodle_{fname}"

        download_ok = await self.download_file(url, local_docx)
        if not download_ok:
            state["last_status"] = "download_error"
            self.save_state(state)
            report["error"] = f"Не удалось скачать файл {fname} с Moodle"
            return report

        # 4. Парсим документ
        parsed = self.parse_replacement_docx(local_docx)
        applied_count = 0
        actual_date_str = parsed.get("date_str") or target_date_str

        # 5. Записываем замены в общую базу данных через db_service
        for item in parsed.get("items", []):
            ok, _ = await db_service.add_replacement(
                date_str=actual_date_str,
                pair_num=item["pair_num"],
                action_type=item["action_type"],
                group_name=item["group_name"],
                subject=item["subject"],
                room=item["room"],
                teacher=item["teacher"],
                raw_text=item.get("raw_text", "")
            )
            if ok:
                applied_count += 1

        # Фиксируем статус
        processed[fname] = actual_date_str
        state["processed_files"] = processed
        state["last_applied_doc"] = {
            "filename": fname,
            "date_str": actual_date_str,
            "applied_count": applied_count,
            "groups_count": len(parsed.get("groups_affected", []))
        }
        state["last_status"] = "applied_new"
        state["last_error"] = None
        self.save_state(state)

        report["success"] = True
        report["new_replacements_found"] = True
        report["applied_count"] = applied_count
        report["date_str"] = actual_date_str
        report["filename"] = fname
        groups_list = sorted(list(parsed.get("groups_affected", [])))
        report["groups_str"] = ", ".join(groups_list) if groups_list else "—"

        # 6. Если найден новый приказ — отправляем оповещение супер-администраторам
        if bot and applied_count > 0:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Разослать студентам об изменениях", callback_data="menu_broadcast")],
                [InlineKeyboardButton(text="⚠️ Открыть управление заменами", callback_data="menu_replacements")]
            ])

            alert_text = (
                "🔔 <b>НОВЫЙ ПРИКАЗ О ЗАМЕНАХ НА САЙТЕ DO.EDUHOUSE.RU!</b>\n"
                "──────────────────────────────\n"
                f"📄 <b>Файл:</b> <code>{fname}</code>\n"
                f"📅 <b>Дата замен:</b> <code>{actual_date_str}</code> ({parsed.get('parity', '')})\n"
                f"👥 <b>Затронутые группы ({len(groups_list)}):</b>\n"
                f"<code>{report['groups_str']}</code>\n\n"
                f"📝 <b>Внесено пар в расписание:</b> <b>{applied_count}</b>\n"
                f"⏰ <b>Время обнаружения:</b> {now.strftime('%H:%M:%S')}\n\n"
                "<i>Замены автоматически применены в базу данных бота и уже активны!</i>"
            )

            for admin_id in SUPERADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=alert_text,
                        reply_markup=kb
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")

        return report

    async def sync_all_schedules(self, bot: Any = None) -> dict[str, Any]:
        """
        Скачивает все семестровые расписания курсов (1-4 курс) с do.eduhouse.ru,
        парсит все группы, числители/знаменатели и пары, и сохраняет в общую базу schedule_bot.db.
        """
        from services.excel_parser import parse_schedule_excel, detect_course_from_group

        result = {
            "success": False,
            "error": None,
            "files_success": 0,
            "files_total": 0,
            "groups_count": 0,
            "groups_list": [],
            "lessons_count": 0
        }

        # 1. Получаем список ссылок на файлы
        doc_data = await self.fetch_available_documents()
        if not doc_data.get("success"):
            result["error"] = doc_data.get("error", "Не удалось подключиться к сайту.")
            return result

        schedules = doc_data.get("schedules", [])
        if not schedules:
            result["error"] = "Файлы расписаний (.xls / .xlsx) не найдены на сайте."
            return result

        result["files_total"] = len(schedules)
        downloads_dir = BASE_DIR / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        total_groups = set()
        total_lessons = 0
        files_success = 0

        # 2. Скачиваем и парсим каждый файл расписания
        for s in schedules:
            url = s["url"]
            fname = s["filename"]
            local_path = downloads_dir / f"moodle_{fname}"

            ok = await self.download_file(url, local_path)
            if not ok:
                logger.error(f"Не удалось скачать расписание {fname}")
                continue

            try:
                parsed = await asyncio.to_thread(parse_schedule_excel, local_path)
            except Exception as e:
                logger.error(f"Ошибка парсинга {fname}: {e}")
                continue

            # Сохраняем группы в БД
            for grp in parsed.get("groups_found", []):
                course = detect_course_from_group(grp)
                await db_service.ensure_group(grp, course=course)
                total_groups.add(grp)

            # Сохраняем все уроки в БД
            for lesson in parsed.get("lessons", []):
                await db_service.add_or_update_lesson(
                    group_name=lesson["group_name"],
                    weekday=lesson["weekday"],
                    pair_num=lesson["pair_num"],
                    subject=lesson["subject"],
                    parity=lesson["parity"],
                    room=lesson.get("room", "—"),
                    teacher=lesson.get("teacher", "—")
                )
                total_lessons += 1

            files_success += 1

        result["success"] = (files_success > 0)
        result["files_success"] = files_success
        result["groups_count"] = len(total_groups)
        result["groups_list"] = sorted(list(total_groups))
        result["lessons_count"] = total_lessons
        return result

    async def start_scheduler(self, bot: Any):
        """
        Запускает почасовую фоновую проверку сайта:
        Начинает проверки в 14:00 и выполняет каждый час до 21:00 по времени бота.
        """
        if not MOODLE_AUTO_SYNC:
            logger.info("Авто-синхронизация с do.eduhouse.ru отключена в настройках.")
            return

        if self._is_running:
            return

        self._is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop(bot))
        logger.info(
            f"Авто-синхронизация с do.eduhouse.ru активирована: "
            f"проверка каждый час с {MOODLE_START_HOUR}:00 до {MOODLE_END_HOUR}:00."
        )

    async def stop_scheduler(self):
        """Останавливает планировщик."""
        self._is_running = False
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Авто-синхронизация с do.eduhouse.ru остановлена.")

    async def _scheduler_loop(self, bot: Any):
        """Фоновый цикл почасовой проверки."""
        while self._is_running:
            try:
                now = datetime.now(BOT_TZ)
                current_hour = now.hour

                # Проверяем, входит ли текущий час в интервал проверки (с 14:00 до 21:00)
                if MOODLE_START_HOUR <= current_hour <= MOODLE_END_HOUR:
                    logger.info(f"⏰ Запуск плановой проверки замен на do.eduhouse.ru (час: {current_hour}:00)...")
                    try:
                        res = await self.check_and_sync(bot=bot, force=False)
                        if res.get("new_replacements_found"):
                            logger.info(f"✅ Применены новые замены из файла {res.get('filename')}: {res.get('applied_count')} записей")
                        else:
                            logger.info("ℹ️ Проверка завершена: новых документов замен не опубликовано.")
                    except Exception as e:
                        logger.error(f"Ошибка плановой проверки Moodle: {e}")

                # Вычисляем время до следующего круглого часа
                now = datetime.now(BOT_TZ)
                seconds_until_next_hour = (60 - now.minute) * 60 - now.second + 5
                # Минимум 60 секунд
                sleep_time = max(60, min(seconds_until_next_hour, 3600))
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Неожиданное исключение в Moodle loop: {e}")
                await asyncio.sleep(300)


moodle_service = MoodleSyncService()
