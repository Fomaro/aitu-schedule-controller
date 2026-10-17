import html
from datetime import datetime, date, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command

from config import BOT_TZ
from keyboards.tests_kb import get_test_alerts_keyboard

router = Router(name="test_alerts")


@router.message(Command("test_alerts", "tests"))
@router.callback_query(F.data == "menu_test_alerts")
async def show_tests_menu(event: types.Message | types.CallbackQuery):
    """Меню быстрого тестирования рассылок и алертов."""
    text = (
        "🧪 <b>Тестирование оповещений и рассылок</b>\n"
        "──────────────────────────────\n"
        "Нажмите на интересующее оповещение ниже, чтобы мгновенно получить "
        "его точный тестовый вид в чат (без реальной отправки студентам):"
    )
    kb = get_test_alerts_keyboard()

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data == "test_alert_midnight")
async def preview_midnight_alert(call: types.CallbackQuery):
    """Превью полночной рассылки (00:00)."""
    await call.answer("Генерирую превью полночной рассылки...")
    now = datetime.now(BOT_TZ)
    tomorrow = now.date() + timedelta(days=1)

    preview_text = (
        f"🌙 <b>[ТЕСТ: РАССЫЛКА 00:00] Расписание на завтра</b>\n"
        f"📅 <b>{tomorrow.strftime('%d.%m.%Y')}</b> (Вторник · Числитель)\n"
        f"👥 Группа: <code>9ПО-43к</code> (4 курс)\n"
        "──────────────────────────────\n"
        "<blockquote>"
        "1️⃣ <b>1 пара (09:00 — 10:35)</b>\n"
        "💻 МДК 04.01 Разработка мобильных приложений\n"
        "▫️ Кабинет: <b>304</b> · Аманов А.К.\n\n"
        "2️⃣ <b>2 пара (10:45 — 12:20)</b>\n"
        "🛡 МДК 07.02 Безопасность баз данных\n"
        "▫️ Кабинет: <b>305</b> · Искаков Б.С.\n\n"
        "🍽 <b>ОБЕДЕННЫЙ ПЕРЕРЫВ (12:20 — 12:55, 35 мин)</b>\n\n"
        "3️⃣ <b>3 пара (12:55 — 14:30)</b>\n"
        "📊 Менеджмент в профессиональной деятельности\n"
        "▫️ Кабинет: <b>402</b> · Смагулова Г.Т."
        "</blockquote>\n\n"
        "<i>Хорошего вечера и продуктивной учёбы завтра! 🎓</i>"
    )
    await call.message.answer(preview_text)


@router.callback_query(F.data == "test_alert_morning")
async def preview_morning_alert(call: types.CallbackQuery):
    """Превью утреннего напоминания (08:00)."""
    await call.answer("Генерирую превью утреннего оповещения...")

    preview_text = (
        "🌅 <b>[ТЕСТ: СВОДКА 08:00] Доброе утро, студенты!</b>\n"
        "──────────────────────────────\n"
        "📅 Сегодня: <b>Вторник, 18 октября</b> · Числитель\n"
        "👥 Группа: <code>9ПО-43к</code>\n\n"
        "🔔 <b>Первая пара начинается в 09:00:</b>\n"
        "▫️ Предмет: <b>МДК 04.01 Мобильные приложения</b>\n"
        "▫️ Аудитория: <b>каб. 304</b>\n"
        "▫️ Преподаватель: <b>Аманов А.К.</b>\n\n"
        "⏳ До первого звонка осталось <b>60 минут</b>. Не опаздывайте!"
    )
    await call.message.answer(preview_text)


@router.callback_query(F.data == "test_alert_break")
async def preview_break_alert(call: types.CallbackQuery):
    """Превью оповещения о пятиминутке внутри пары."""
    await call.answer("Генерирую превью пятиминутки...")

    preview_text = (
        "☕️ <b>[ТЕСТ: ПЯТИМИНУТКА] Перерыв внутри пары!</b>\n"
        "──────────────────────────────\n"
        "⏰ Время: <b>09:45 — 09:50</b> (5 минут)\n"
        "Вторая половина пары начнётся в <b>09:50</b>."
    )
    await call.message.answer(preview_text)


@router.callback_query(F.data == "test_alert_ten_min")
async def preview_ten_min_alert(call: types.CallbackQuery):
    """Превью колокольчика за 10 минут до пары."""
    await call.answer("Генерирую превью 10-минутного колокольчика...")

    preview_text = (
        "🔔 <b>[ТЕСТ: КОЛОКОЛЬЧИК] Пара начнётся через 10 минут!</b>\n"
        "──────────────────────────────\n"
        "🔢 Пара: <b>2 пара (10:45)</b>\n"
        "📚 Предмет: <b>МДК 07.02 Безопасность БД</b>\n"
        "🚪 Аудитория: <b>каб. 305</b>\n"
        "👨‍🏫 Преподаватель: <b>Искаков Б.С.</b>\n\n"
        "🏃‍♂️ Пора выдвигаться к аудитории!"
    )
    await call.message.answer(preview_text)
