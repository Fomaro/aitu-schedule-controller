import os
import re
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("controller.excel_parser")

WEEKDAYS_MAP = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
}

GROUP_REGEX = re.compile(r'\b(\d{1,2}[А-Яа-яA-Za-z]{1,4}-\d{1,3}[а-яА-Яa-zA-Z]?)\b')
ROOM_REGEX = re.compile(r'(?:каб\.?|ауд\.?|№)?\s*(\b\d{2,4}[а-яА-Я]?\b|спортзал|актовый\s*зал|стадион|тир|дистант)', re.IGNORECASE)
TEACHER_REGEX = re.compile(r'\b([А-ЯЁ][а-яё]+)\s+([А-ЯЁ]\.\s*[А-ЯЁ]\.?)\b')


def canonical_group_name(group_name: str | None) -> str:
    """
    Приводит название группы к каноническому виду (например, 9ПО-43к).
    Автоматически преобразует визуально похожие латинские буквы в кириллицу.
    """
    if not group_name:
        return ""
    clean = group_name.strip()

    lat_to_cyr = {
        'A': 'А', 'a': 'а',
        'B': 'В', 'b': 'в',
        'C': 'С', 'c': 'с',
        'E': 'Е', 'e': 'е',
        'H': 'Н', 'h': 'н',
        'K': 'К', 'k': 'к',
        'M': 'М', 'm': 'м',
        'O': 'О', 'o': 'о',
        'P': 'Р', 'p': 'р',
        'T': 'Т', 't': 'т',
        'X': 'Х', 'x': 'х',
        'Y': 'У', 'y': 'у',
    }
    trans = "".join(lat_to_cyr.get(ch, ch) for ch in clean)
    m = re.match(r"^(\d{1,2})\s*([а-яА-Яa-zA-Z]+)\s*[-–—_]?\s*(\d{1,3})\s*([а-яА-Яa-zA-Z]?)$", trans)
    if m:
        c, dept, num, letter = m.groups()
        suffix = letter.lower() if letter else ""
        return f"{c}{dept.upper()}-{num}{suffix}"
    return trans


def normalize_group_name(name: str | None) -> str:
    """Алиас для обратной совместимости."""
    return canonical_group_name(name)


def get_group_variants(group_name: str | None) -> list[str]:
    """Возвращает все варианты написания группы для SQL-запросов."""
    if not group_name:
        return []
    variants = set()
    raw = group_name.strip()
    if not raw:
        return []

    variants.add(raw)
    variants.add(raw.upper())
    variants.add(raw.lower())

    canon = canonical_group_name(raw)
    if canon:
        variants.add(canon)
        variants.add(canon.upper())
        variants.add(canon.lower())

        if canon[-1].isalpha():
            base = canon[:-1]
            last = canon[-1]
            variants.add(f"{base}{last.lower()}")
            variants.add(f"{base}{last.upper()}")
            variants.add(f"{base.upper()}{last.lower()}")
            variants.add(f"{base.upper()}{last.upper()}")
            variants.add(f"{base.lower()}{last.lower()}")
            variants.add(f"{base.lower()}{last.upper()}")

        no_dash = canon.replace("-", "")
        variants.add(no_dash)
        variants.add(no_dash.upper())
        variants.add(no_dash.lower())

    return [v for v in variants if v]


def is_same_group(grp1: str | None, grp2: str | None) -> bool:
    """Сравнивает два названия учебных групп без учёта регистра и латиницы/кириллицы."""
    if not grp1 or not grp2:
        return False
    return canonical_group_name(grp1).lower() == canonical_group_name(grp2).lower()


def detect_course_from_group(grp_name: str | None) -> int:
    """Определяет номер курса (1..4) по названию группы."""
    if not grp_name:
        return 4
    m = re.search(r"-([1-4])", grp_name)
    if m:
        return int(m.group(1))
    m2 = re.search(r"[^0-9]([1-4])\d", grp_name)
    if m2:
        return int(m2.group(1))
    return 4


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def get_sheets_matrix(file_path: str | Path) -> list[tuple[str, list[list[str]]]]:
    """
    Универсальное извлечение матриц ячеек из файлов .xls (BIFF8) и .xlsx.
    Возвращает список кортежей (имя_листа, матрица_строк).
    """
    path_str = str(file_path)
    sheets_matrix = []

    # 1. Попытка чтения через xlrd для устаревшего бинарного формата .xls
    if path_str.lower().endswith(".xls"):
        try:
            import xlrd
            book = xlrd.open_workbook(path_str)
            for sheet in book.sheets():
                matrix = []
                for r in range(min(sheet.nrows, 350)):
                    row = [_clean_str(sheet.cell_value(r, c)) for c in range(min(sheet.ncols, 60))]
                    matrix.append(row)
                sheets_matrix.append((sheet.name, matrix))
            if sheets_matrix:
                return sheets_matrix
        except Exception as e:
            logger.warning(f"Ошибка чтения через xlrd ({path_str}): {e}")

    # 2. Попытка чтения через openpyxl для .xlsx
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path_str, data_only=True)
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            matrix = []
            max_row = min(sheet.max_row, 350)
            max_col = min(sheet.max_column, 60)
            for r in range(1, max_row + 1):
                row = [_clean_str(sheet.cell(row=r, column=c).value) for c in range(1, max_col + 1)]
                matrix.append(row)
            sheets_matrix.append((sheet_name, matrix))
        wb.close()
    except Exception as e:
        logger.error(f"Ошибка чтения через openpyxl ({path_str}): {e}")

    return sheets_matrix


def parse_schedule_excel(file_path: str | Path) -> dict[str, Any]:
    """
    Интеллектуальный парсер расписания колледжа (.xls / .xlsx).
    Распознает:
    - Все группы в заголовках колонок
    - Дни недели (Пн..Сб)
    - Номера пар (1..6)
    - Чередование по числителю / знаменателю (по строкам или слэшу /)
    - Аудитории и преподавателей
    """
    results = {
        "groups_found": set(),
        "lessons": [],
        "lessons_parsed": 0,
        "sheets_count": 0
    }

    sheets = get_sheets_matrix(file_path)
    results["sheets_count"] = len(sheets)

    for sheet_name, matrix in sheets:
        if not matrix:
            continue
        max_row = len(matrix)

        # 1. Поиск колонок с названиями групп (первые 10 строк таблицы)
        group_cols: dict[int, str] = {}
        for r in range(min(max_row, 10)):
            row = matrix[r]
            for c in range(len(row)):
                val = row[c]
                matches = GROUP_REGEX.findall(val)
                for m in matches:
                    grp_name = normalize_group_name(m)
                    group_cols[c] = grp_name
                    results["groups_found"].add(grp_name)

        if not group_cols:
            continue

        current_weekday = None
        current_pair_num = None

        # 2. Построчный разбор занятий
        for r in range(max_row):
            row = matrix[r]
            if not row:
                continue

            row_prefix_text = " ".join(row[:min(len(row), 6)]).lower()

            # Определение дня недели
            for day_name, day_idx in WEEKDAYS_MAP.items():
                if day_name in row_prefix_text:
                    current_weekday = day_idx
                    break

            # Определение номера пары (1..6)
            for c in range(min(len(row), 5)):
                cell_val = row[c]
                if cell_val.isdigit() and 1 <= int(cell_val) <= 6:
                    current_pair_num = int(cell_val)
                    break

            if current_weekday is None or current_pair_num is None:
                continue

            # Определение четности недели на уровне строки
            row_parity = "both"
            for c in range(min(len(row), 5)):
                val_lower = row[c].lower().strip()
                if any(k in val_lower for k in ["числ", "1 нед", "i нед"]) or val_lower == "ч":
                    row_parity = "chislitel"
                    break
                elif any(k in val_lower for k in ["знам", "2 нед", "ii нед"]) or val_lower == "з":
                    row_parity = "znamenatel"
                    break

            # Считывание предметов по найденным колонкам групп
            for col_idx, grp_name in group_cols.items():
                if col_idx >= len(row):
                    continue
                cell_content = row[col_idx]
                if not cell_content or len(cell_content) < 3:
                    continue

                # Извлечение аудитории
                room = "—"
                r_m = ROOM_REGEX.search(cell_content)
                if r_m:
                    room = r_m.group(1).strip()

                # Извлечение преподавателя
                teacher = "—"
                t_m = TEACHER_REGEX.search(cell_content)
                if t_m:
                    teacher = f"{t_m.group(1)} {t_m.group(2)}".strip()

                # Очистка названия предмета
                subj_clean = cell_content
                if t_m:
                    subj_clean = subj_clean.replace(t_m.group(0), "")
                if r_m and r_m.group(0).lower() != "дистант":
                    subj_clean = subj_clean.replace(r_m.group(0), "")
                subj_clean = re.sub(r'[\(\)\[\]]', ' ', subj_clean)
                subj_clean = re.sub(r'\s+', ' ', subj_clean).strip()
                if not subj_clean or len(subj_clean) < 2:
                    subj_clean = cell_content

                # Если четность определена строкой
                if row_parity != "both":
                    results["lessons"].append({
                        "group_name": grp_name,
                        "weekday": current_weekday,
                        "pair_num": current_pair_num,
                        "parity": row_parity,
                        "subject": subj_clean,
                        "room": room,
                        "teacher": teacher
                    })
                    results["lessons_parsed"] += 1
                # Если ячейка разделена слэшем или переносом строки на числитель / знаменатель
                elif "/" in cell_content and len(cell_content.split("/")) == 2:
                    parts = cell_content.split("/")
                    for p_code, part in [("chislitel", parts[0].strip()), ("znamenatel", parts[1].strip())]:
                        if part and len(part) > 1 and part not in ("-", "—"):
                            results["lessons"].append({
                                "group_name": grp_name,
                                "weekday": current_weekday,
                                "pair_num": current_pair_num,
                                "parity": p_code,
                                "subject": part,
                                "room": room,
                                "teacher": teacher
                            })
                            results["lessons_parsed"] += 1
                else:
                    results["lessons"].append({
                        "group_name": grp_name,
                        "weekday": current_weekday,
                        "pair_num": current_pair_num,
                        "parity": "both",
                        "subject": subj_clean,
                        "room": room,
                        "teacher": teacher
                    })
                    results["lessons_parsed"] += 1

    return results
