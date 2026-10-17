from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_test_alerts_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура тестирования рассылок и оповещений."""
    builder = InlineKeyboardBuilder()

    builder.button(text="🌙 Тест: 00:00 (Полночь)", callback_data="test_alert_midnight")
    builder.button(text="🌅 Тест: 08:00 (Утро)", callback_data="test_alert_morning")
    builder.button(text="☕️ Тест: Пятиминутка", callback_data="test_alert_break")
    builder.button(text="🔔 Тест: За 10 минут", callback_data="test_alert_ten_min")
    builder.button(text="◀️ Назад в дашборд", callback_data="back_to_dashboard")

    builder.adjust(2, 2, 1)
    return builder.as_markup()
