import os
import sys
import html
import logging
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import TARGET_BOT_DIR

logger = logging.getLogger(__name__)
router = Router(name="documents")

# Обеспечиваем доступ к парсерам целевого бота
if str(TARGET_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(TARGET_BOT_DIR))


def get_documents_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура меню загрузки расписания."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить дашборд", callback_data="menu_dashboard")
    builder.button(text="◀️ Назад в дашборд", callback_data="back_to_dashboard")
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("upload", "parse"))
@router.callback_query(F.data == "menu_schedule_upload")
async def show_upload_info(event: types.Message | types.CallbackQuery):
    """Инструкция по загрузке файлов расписания и замен."""
    text = (
        "📄 <b>Загрузка и парсинг расписания / замен</b>\n"
        "──────────────────────────────\n"
        "Вы можете прислать боту-контроллеру документ прямо в этот чат:\n\n"
        "1️⃣ <b>Таблица расписания (<code>.xlsx</code> / <code>.xls</code>):</b>\n"
        "▫️ Полное семестровое расписание по группам.\n"
        "▫️ Автоматически создаёт группы и обновляет расписание пар в базе.\n\n"
        "2️⃣ <b>Приказ о заменах (<code>.docx</code>):</b>\n"
        "▫️ Документ с таблицей замен и отмен на конкретную дату.\n"
        "▫️ Автоматически распознаёт дату, группы, кабинеты и вносит замены в базу.\n\n"
        "📎 <i>Просто прикрепите и отправьте файл сюда без дополнительных команд!</i>"
    )
    kb = get_documents_menu_keyboard()

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.message(F.document)
async def handle_document_upload(message: types.Message, bot: Bot):
    """Обрабатывает загруженные файлы Word и Excel."""
    doc = message.document
    if not doc:
        return

    filename = (doc.file_name or "").lower()
    if not filename.endswith((".docx", ".xlsx", ".xls")):
        await message.answer(
            "ℹ️ <b>Неподдерживаемый формат файла.</b>\n"
            "Пожалуйста, отправьте документ замен (<code>.docx</code>) или таблицу расписания (<code>.xlsx</code>)."
        )
        return

    os.makedirs("downloads", exist_ok=True)
    temp_path = os.path.join("downloads", f"{message.from_user.id}_{doc.file_name}")

    status_msg = await message.answer(
        f"⏳ <i>Загружаю и анализирую документ <code>{html.escape(doc.file_name or '')}</code>...</i>"
    )

    try:
        await bot.download(doc, destination=temp_path)

        if filename.endswith(".docx"):
            # Парсинг замен Word
            try:
                from services.parser import parse_and_apply_docx_replacements
            except ImportError:
                # Попробуем альтернативный импорт из каталога бота
                sys.path.insert(0, str(TARGET_BOT_DIR))
                from services.parser.docx_parser import parse_and_apply_docx_replacements

            result = await parse_and_apply_docx_replacements(temp_path, created_by=message.from_user.id)
            groups_str = ", ".join(sorted(list(result.get("groups_affected", [])))) or "Все"

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Разослать студентам об изменениях", callback_data="menu_broadcast")],
                [InlineKeyboardButton(text="⚠️ Перейти в управление заменами", callback_data="menu_replacements")]
            ])

            await status_msg.edit_text(
                f"✅ <b>Документ замен успешно обработан и применён!</b>\n\n"
                f"📅 <b>Дата замен:</b> <code>{result.get('date_str', 'не указана')}</code>\n"
                f"👥 <b>Затронутые группы:</b> <code>{html.escape(groups_str)}</code>\n"
                f"📝 <b>Внесено записей:</b> <b>{result.get('applied_count', 0)}</b>\n\n"
                f"<i>Все изменения моментально сохранены в базу данных schedule_bot.db!</i>",
                reply_markup=kb
            )

        elif filename.endswith((".xlsx", ".xls")):
            # Парсинг расписания Excel
            try:
                from services.parser import parse_and_apply_excel_schedule
            except ImportError:
                sys.path.insert(0, str(TARGET_BOT_DIR))
                from services.parser.excel_parser import parse_and_apply_excel_schedule

            result = await parse_and_apply_excel_schedule(temp_path)
            groups_list = list(result.get("groups_found", []))
            groups_str = ", ".join(sorted(groups_list)[:10])
            if len(groups_list) > 10:
                groups_str += f" ... (и ещё {len(groups_list) - 10})"

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👑 Вернуться в дашборд", callback_data="menu_dashboard")]
            ])

            await status_msg.edit_text(
                f"✅ <b>Семестровое расписание успешно обновлено!</b>\n\n"
                f"👥 <b>Найдено академических групп:</b> <b>{len(groups_list)}</b>\n"
                f"▫️ <i>{html.escape(groups_str or '—')}</i>\n\n"
                f"📚 <b>Внесено занятий в базу:</b> <b>{result.get('applied_count', 0)}</b>\n\n"
                f"<i>Студенты и бот расписания уже видят обновлённые пары!</i>",
                reply_markup=kb
            )

    except Exception as e:
        logger.error(f"Ошибка парсинга документа {doc.file_name}: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ <b>Ошибка при обработке файла:</b>\n"
            f"<code>{html.escape(str(e))}</code>"
        )
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
