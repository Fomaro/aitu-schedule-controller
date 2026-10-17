import logging
from pathlib import Path
import aiosqlite
from config import TARGET_DB_PATH

logger = logging.getLogger(__name__)


class DatabaseService:
    """
    Асинхронный сервис взаимодействия с SQLite базой данных целевого бота (schedule_bot.db).
    Позволяет инспектировать статистику, управлять ролями (Superadmin, Admin, Starosta),
    и подготавливать списки получателей для рассылок.
    """

    def __init__(self, db_path: Path = TARGET_DB_PATH):
        self.db_path = db_path

    async def _get_conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def is_db_available(self) -> bool:
        """Проверяет существование и доступность файла БД."""
        return self.db_path.exists()

    async def get_stats(self) -> dict:
        """Возвращает агрегированную статистику по базе данных."""
        stats = {
            "is_available": False,
            "total_users": 0,
            "total_groups": 0,
            "total_chats": 0,
            "total_replacements": 0,
            "sub_10min": 0,
            "sub_morning": 0,
            "sub_breaks": 0
        }
        if not await self.is_db_available():
            return stats

        try:
            async with await self._get_conn() as conn:
                stats["is_available"] = True
                
                # Пользователи
                async with conn.execute("SELECT count(*) FROM users") as cur:
                    row = await cur.fetchone()
                    stats["total_users"] = row[0] if row else 0

                # Группы
                async with conn.execute("SELECT count(*) FROM groups") as cur:
                    row = await cur.fetchone()
                    stats["total_groups"] = row[0] if row else 0

                # Привязанные беседы
                async with conn.execute("SELECT count(*) FROM chat_bindings") as cur:
                    row = await cur.fetchone()
                    stats["total_chats"] = row[0] if row else 0

                # Замены
                async with conn.execute("SELECT count(*) FROM replacements") as cur:
                    row = await cur.fetchone()
                    stats["total_replacements"] = row[0] if row else 0

                # Подписчики уведомлений
                async with conn.execute("SELECT count(*) FROM users WHERE remind_10min = 1") as cur:
                    row = await cur.fetchone()
                    stats["sub_10min"] = row[0] if row else 0

                async with conn.execute("SELECT count(*) FROM users WHERE morning_alert = 1") as cur:
                    row = await cur.fetchone()
                    stats["sub_morning"] = row[0] if row else 0

                async with conn.execute("SELECT count(*) FROM users WHERE five_min_breaks = 1") as cur:
                    row = await cur.fetchone()
                    stats["sub_breaks"] = row[0] if row else 0

        except Exception as e:
            logger.error(f"Ошибка получения статистики БД: {e}")

        return stats

    async def get_elevated_users(self) -> list[dict]:
        """Возвращает список всех пользователей с расширенными правами (админы, старосты)."""
        if not await self.is_db_available():
            return []

        try:
            async with await self._get_conn() as conn:
                query = """
                    SELECT user_id, username, full_name, group_name, role
                    FROM users
                    WHERE role IN ('superadmin', 'admin', 'starosta', 'zam_starosty')
                    ORDER BY 
                        CASE role
                            WHEN 'superadmin' THEN 1
                            WHEN 'admin' THEN 2
                            WHEN 'starosta' THEN 3
                            WHEN 'zam_starosty' THEN 4
                            ELSE 5
                        END,
                        group_name ASC
                """
                async with conn.execute(query) as cur:
                    rows = await cur.fetchall()
                    return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Ошибка получения списка ролей: {e}")
            return []

    async def find_user(self, query: str | int) -> dict | None:
        """Поиск пользователя по user_id или @username."""
        if not await self.is_db_available():
            return None

        clean_q = str(query).strip().lstrip("@")
        try:
            async with await self._get_conn() as conn:
                if clean_q.isdigit():
                    sql = "SELECT * FROM users WHERE user_id = ?"
                    param = int(clean_q)
                else:
                    sql = "SELECT * FROM users WHERE lower(username) = lower(?)"
                    param = clean_q

                async with conn.execute(sql, (param,)) as cur:
                    row = await cur.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка поиска пользователя: {e}")
            return None

    async def update_user_role(self, user_id: int, new_role: str, group_name: str | None = None) -> tuple[bool, str]:
        """Обновляет роль и опционально группу пользователя."""
        if not await self.is_db_available():
            return False, "Файл базы данных schedule_bot.db не найден."

        valid_roles = {"student", "zam_starosty", "starosta", "admin", "superadmin"}
        if new_role not in valid_roles:
            return False, f"Недопустимая роль. Доступны: {', '.join(valid_roles)}"

        try:
            async with await self._get_conn() as conn:
                # Проверяем наличие пользователя
                async with conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
                    user = await cur.fetchone()
                    if not user:
                        return False, f"Пользователь с ID {user_id} отсутствует в базе бота."

                if group_name:
                    await conn.execute(
                        "UPDATE users SET role = ?, group_name = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                        (new_role, group_name.strip(), user_id)
                    )
                else:
                    await conn.execute(
                        "UPDATE users SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                        (new_role, user_id)
                    )
                await conn.commit()
                return True, f"Роль успешно обновлена на: {new_role}"
        except Exception as e:
            logger.error(f"Ошибка обновления роли пользователя: {e}")
            return False, str(e)

    async def get_all_groups(self) -> list[str]:
        """Возвращает список всех зарегистрированных групп."""
        if not await self.is_db_available():
            return []

        try:
            async with await self._get_conn() as conn:
                async with conn.execute("SELECT name FROM groups ORDER BY name ASC") as cur:
                    rows = await cur.fetchall()
                    return [r["name"] for r in rows]
        except Exception:
            return []

    async def get_broadcast_recipients(self, target_type: str, group_name: str | None = None) -> list[int]:
        """
        Возвращает список уникальных chat_id / user_id для рассылки:
        target_type: 'all' (все пользователи и беседы), 'chats' (только беседы), 'group' (только студенты и беседы группы).
        """
        if not await self.is_db_available():
            return []

        recipients = []
        try:
            async with await self._get_conn() as conn:
                if target_type == "chats":
                    async with conn.execute("SELECT chat_id FROM chat_bindings") as cur:
                        rows = await cur.fetchall()
                        recipients.extend([r["chat_id"] for r in rows])

                elif target_type == "group" and group_name:
                    # Чаты группы
                    async with conn.execute("SELECT chat_id FROM chat_bindings WHERE group_name = ?", (group_name,)) as cur:
                        rows = await cur.fetchall()
                        recipients.extend([r["chat_id"] for r in rows])
                    # Студенты группы
                    async with conn.execute("SELECT user_id FROM users WHERE group_name = ?", (group_name,)) as cur:
                        rows = await cur.fetchall()
                        recipients.extend([r["user_id"] for r in rows])

                else:
                    # Все пользователи
                    async with conn.execute("SELECT user_id FROM users") as cur:
                        rows = await cur.fetchall()
                        recipients.extend([r["user_id"] for r in rows])
                    # Все беседы
                    async with conn.execute("SELECT chat_id FROM chat_bindings") as cur:
                        rows = await cur.fetchall()
                        recipients.extend([r["chat_id"] for r in rows])

        except Exception as e:
            logger.error(f"Ошибка сбора получателей рассылки: {e}")

        # Удаляем дубликаты
        return list(dict.fromkeys(recipients))


db_service = DatabaseService()
