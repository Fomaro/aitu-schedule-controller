import os
import asyncio
import logging
import subprocess
from pathlib import Path
from config import TARGET_BOT_DIR

logger = logging.getLogger(__name__)


class GitService:
    """
    Сервис управления Git репозиторием целевого бота (информация, коммиты, git pull).
    """

    def __init__(self, repo_dir: Path = TARGET_BOT_DIR):
        self.repo_dir = repo_dir

    async def _run_git_cmd(self, *args: str) -> tuple[int, str, str]:
        """Асинхронно выполняет команду git в директории репозитория."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", *args,
                cwd=str(self.repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout.decode(errors="replace").strip(), stderr.decode(errors="replace").strip()
        except Exception as e:
            logger.error(f"Ошибка выполнения git {args}: {e}")
            return 1, "", str(e)

    async def get_info(self) -> dict:
        """Получает расширенную информацию о Git репозитории."""
        info = {
            "is_git": False,
            "branch": "unknown",
            "commit": "—",
            "commit_full": "",
            "author": "—",
            "date": "—",
            "message": "—",
            "is_dirty": False,
            "behind_count": 0
        }

        # Проверяем, является ли папка git-репозиторием
        rc, _, _ = await self._run_git_cmd("rev-parse", "--is-inside-work-tree")
        if rc != 0:
            return info
        info["is_git"] = True

        # Текущая ветка
        rc, branch, _ = await self._run_git_cmd("rev-parse", "--abbrev-ref", "HEAD")
        if rc == 0:
            info["branch"] = branch

        # Последний коммит
        rc, commit_hash, _ = await self._run_git_cmd("rev-parse", "--short", "HEAD")
        rc_full, commit_full, _ = await self._run_git_cmd("rev-parse", "HEAD")
        rc2, msg, _ = await self._run_git_cmd("log", "-1", "--pretty=%s")
        rc3, author, _ = await self._run_git_cmd("log", "-1", "--pretty=%an")
        rc4, date_str, _ = await self._run_git_cmd("log", "-1", "--pretty=%cd", "--date=format:%d.%m.%Y %H:%M")

        if rc == 0:
            info["commit"] = commit_hash
            info["commit_full"] = commit_full
            info["message"] = msg
            info["author"] = author
            info["date"] = date_str

        # Проверка наличия незакоммиченных изменений (с фильтрацией runtime-данных)
        rc_status, status_out, _ = await self._run_git_cmd("status", "--porcelain")
        dirty_items = []
        if rc_status == 0 and status_out.strip():
            runtime_names = {
                "subscribers.json", "zameny.json", "user_settings.json",
                ".bot_status.json", "bot.pid", "bot.log", "schedule_bot.db",
                "schedule_bot.db-wal", "schedule_bot.db-shm", "schedule_bot.db-journal"
            }
            for line in status_out.splitlines():
                line_s = line.strip()
                if not line_s:
                    continue
                parts = line_s.split(maxsplit=1)
                fname = parts[1].strip() if len(parts) > 1 else line_s
                base_fname = Path(fname).name
                if (
                    base_fname in runtime_names
                    or fname.startswith("downloads/")
                    or fname.startswith("__pycache__")
                    or fname.endswith(".pyc")
                ):
                    continue
                dirty_items.append(fname)

        info["is_dirty"] = bool(dirty_items)
        info["dirty_files"] = dirty_items

        # Проверка отставания от origin (без долгой блокировки)
        try:
            branch = info.get("branch", "main")
            rc_fetch, _, _ = await asyncio.wait_for(self._run_git_cmd("fetch", "origin", branch), timeout=7.0)
            rc_behind, behind_out, _ = await self._run_git_cmd("rev-list", f"HEAD..origin/{branch}", "--count")
            if rc_behind == 0 and behind_out.strip().isdigit():
                info["behind_count"] = int(behind_out.strip())
        except Exception:
            pass

        return info

    async def pull(self) -> tuple[bool, str, bool]:
        """
        Выполняет git pull origin <current_branch>.
        Возвращает: (успех, вывод_команды, изменился_ли_requirements)
        """
        info = await self.get_info()
        branch = info.get("branch") or "main"

        # Сохраняем хеш до обновления для проверки изменений
        old_head = info.get("commit_full", "")

        rc, stdout, stderr = await self._run_git_cmd("pull", "origin", branch)
        output = (stdout + "\n" + stderr).strip()
        success = rc == 0

        reqs_changed = False
        if success and old_head:
            # Проверяем, изменился ли requirements.txt
            rc_diff, diff_out, _ = await self._run_git_cmd("diff", "--name-only", old_head, "HEAD")
            if rc_diff == 0 and "requirements.txt" in diff_out:
                reqs_changed = True

        return success, output, reqs_changed

    async def reset_hard(self) -> tuple[bool, str]:
        """Сбрасывает локальные изменения (git reset --hard HEAD && git clean -fd)."""
        rc1, out1, err1 = await self._run_git_cmd("reset", "--hard", "HEAD")
        rc2, out2, err2 = await self._run_git_cmd("clean", "-fd")
        ok = (rc1 == 0 and rc2 == 0)
        output = (out1 + "\n" + out2 + "\n" + err1 + "\n" + err2).strip()
        return ok, output

    async def get_recent_commits(self, limit: int = 5) -> list[str]:
        """Возвращает список последних N коммитов."""
        rc, out, _ = await self._run_git_cmd("log", f"-{limit}", "--pretty=format:▫️ <code>%h</code> (%cd) %s <i>[%an]</i>", "--date=format:%d.%m %H:%M")
        if rc == 0 and out.strip():
            return out.strip().split("\n")
        return []


git_service = GitService()
