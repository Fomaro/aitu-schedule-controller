import os
import html
import logging
from pathlib import Path
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import FSInputFile

from filters.superadmin import IsSuperAdminFilter
from config import (
    MOODLE_URL,
    MOODLE_USERNAME,
    MOODLE_AUTO_SYNC,
    MOODLE_START_HOUR,
    MOODLE_END_HOUR,
    BASE_DIR
)
from services.moodle_service import moodle_service
from keyboards.moodle_kb import get_moodle_keyboard

logger = logging.getLogger("controller.handlers.moodle")
router = Router(name="moodle_sync_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


async def _render_moodle_dashboard(event: types.Message | types.CallbackQuery, extra_text: str | None = None):
    """Отображает панель управления синхронизацией с Moodle."""
    state = moodle_service.load_state()

    auto_sync_status = f"Включена 🟢 (каждый час с {MOODLE_START_HOUR}:00 до {MOODLE_END_HOUR}:00 МСК)" if MOODLE_AUTO_SYNC else "Отключена ⚪️"
    last_check = state.get("last_check_at") or "ещё не выполнялась"
    last_status = state.get("last_status", "never")

    status_desc = {
        "applied_new": "Применён свежий приказ ✅",
        "already_processed": "Актуален (без изменений) ✅",
        "ok_no_files": "Файлы замен не найдены ℹ️",
        "error": f"Ошибка: {state.get('last_error', 'неизвестно')} ❌",
        "download_error": "Ошибка загрузки файла ❌",
        "never": "Ожидание первого запуска ⚪️"
    }.get(last_status, last_status)

    last_doc = state.get("last_applied_doc")
    last_doc_str = (
        f"<code>{last_doc['filename']}</code> на <b>{last_doc['date_str']}</b> "
        f"({last_doc.get('applied_count', 0)} пар)"
    ) if last_doc else "—"

    processed_count = len(state.get("processed_files", {}))

    lines = [
        "🌐 <b>СИНХРОНИЗАЦИЯ С ПОРТАЛОМ DO.EDUHOUSE.RU</b>",
        "──────────────────────────────",
        f"▫️ Портал: <code>{MOODLE_URL}</code>",
        f"▫️ Учётная запись: <code>{MOODLE_USERNAME}</code>",
        f"▫️ Автопроверка: <b>{auto_sync_status}</b>",
        f"▫️ Последняя проверка: <code>{last_check}</code>",
        f"▫️ Результат проверки: {status_desc}",
        f"▫️ Последний применённый приказ: {last_doc_str}",
        f"▫️ Всего обработано документов: <b>{processed_count}</b>",
        "──────────────────────────────",
        "💡 <i>Бот автоматически проверяет появление замен в 14:00 и каждый последующий час. "
        "Вы также можете запустить проверку вручную кнопкой ниже.</i>"
    ]

    if extra_text:
        lines.append("\n" + extra_text)

    text = "\n".join(lines)
    kb = get_moodle_keyboard(has_latest_file=bool(last_doc))

    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except Exception:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.message(Command("moodle", "moodle_sync", "sync"))
@router.callback_query(F.data == "menu_moodle_sync")
async def cb_menu_moodle_sync(event: types.Message | types.CallbackQuery):
    await _render_moodle_dashboard(event)


@router.callback_query(F.data == "moodle_check_now")
async def cb_moodle_check_now(call: types.CallbackQuery, bot: Bot):
    await call.answer("🔍 Подключаюсь к do.eduhouse.ru и проверяю файлы замен...", show_alert=False)
    report = await moodle_service.check_and_sync(bot=bot, force=True)

    if report.get("error"):
        extra = f"❌ <b>Ошибка при синхронизации:</b>\n<code>{html.escape(str(report['error']))}</code>"
    elif report.get("new_replacements_found"):
        extra = (
            "🎉 <b>Синхронизация завершена успешно!</b>\n\n"
            f"📄 Файл: <code>{report.get('filename')}</code>\n"
            f"📅 Дата: <code>{report.get('date_str')}</code>\n"
            f"👥 Затронутые группы: <code>{report.get('groups_str')}</code>\n"
            f"📝 Внесено записей в БД: <b>{report.get('applied_count')}</b>\n\n"
            "<i>Все замены активны и уже видны студентам в расписании!</i>"
        )
    else:
        extra = (
            "✅ <b>Проверка завершена!</b>\n\n"
            f"Новых приказов не появилось. Последний файл <code>{report.get('filename') or 'замен'}</code> "
            "уже синхронизирован с базой расписания."
        )

    await _render_moodle_dashboard(call, extra_text=extra)


@router.callback_query(F.data == "moodle_list_files")
async def cb_moodle_list_files(call: types.CallbackQuery):
    await call.answer("Сканирую файлы на сайте...")
    data = await moodle_service.fetch_available_documents()

    if not data.get("success"):
        extra = f"❌ <b>Ошибка получения списка:</b>\n<code>{html.escape(str(data.get('error')))}</code>"
        await _render_moodle_dashboard(call, extra_text=extra)
        return

    replacements = data.get("replacements", [])
    schedules = data.get("schedules", [])

    lines = ["📋 <b>ФАЙЛЫ НА ПОРТАЛЕ DO.EDUHOUSE.RU:</b>", "──────────────────────────────"]

    lines.append("📄 <b>Приказы о заменах (.docx):</b>")
    if replacements:
        for r in replacements[:6]:
            date_hint = f" (📅 {r['date_str']})" if r.get('date_str') else ""
            lines.append(f"▫️ <code>{html.escape(r['filename'])}</code>{date_hint}")
    else:
        lines.append("▫️ <i>Файлы замен не обнаружены.</i>")

    lines.append("\n📊 <b>Семестровые расписания (.xls / .xlsx):</b>")
    if schedules:
        for s in schedules[:5]:
            lines.append(f"▫️ {html.escape(s['title'])}")
    else:
        lines.append("▫️ <i>Файлы расписаний не найдены.</i>")

    extra = "\n".join(lines)
    await _render_moodle_dashboard(call, extra_text=extra)


@router.callback_query(F.data == "moodle_download_last")
async def cb_moodle_download_last(call: types.CallbackQuery):
    state = moodle_service.load_state()
    last_doc = state.get("last_applied_doc")

    if not last_doc or not last_doc.get("filename"):
        await call.answer("Файл ещё не был скачан.", show_alert=True)
        return

    fname = last_doc["filename"]
    local_path = BASE_DIR / "downloads" / f"moodle_{fname}"

    if not local_path.exists():
        await call.answer("Файл на сервере не найден. Выполняю повторную загрузку...", show_alert=False)
        data = await moodle_service.fetch_available_documents()
        for r in data.get("replacements", []):
            if r["filename"] == fname:
                await moodle_service.download_file(r["url"], local_path)
                break

    if not local_path.exists():
        await call.answer("Не удалось получить файл с сайта.", show_alert=True)
        return

    await call.answer("Отправляю документ...")
    doc = FSInputFile(str(local_path), filename=fname)
    caption = (
        f"📄 <b>Официальный приказ о заменах колледжа АИТУ</b>\n"
        f"📅 Дата: <code>{last_doc.get('date_str')}</code>\n"
        f"📝 Внесено замен: <b>{last_doc.get('applied_count')}</b>\n"
        f"🌐 Источник: <code>do.eduhouse.ru</code>"
    )
    await call.message.answer_document(doc, caption=caption)
