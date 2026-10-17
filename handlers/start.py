from aiogram import Router, types
from aiogram.filters import CommandStart, Command
from filters.superadmin import IsSuperAdminFilter
from handlers.dashboard import render_dashboard_text
from keyboards.dashboard import get_dashboard_keyboard

router = Router(name="start_router")
router.message.filter(IsSuperAdminFilter())


@router.message(CommandStart())
@router.message(Command("help", "menu"))
async def cmd_start(message: types.Message):
    """Приветствие супер-администратора и вывод главного пульта."""
    intro = (
        f"👋 Здравствуйте, <b>{message.from_user.first_name}</b>!\n\n"
        "Добро пожаловать в <b>AITU Schedule Supervisor</b> — независимый бот-контроллер "
        "и выделенную консоль супер-администратора бота расписания колледжа AITU.\n\n"
        "<blockquote>"
        "👑 <b>Панель управления супер-администратора</b>\n"
        "🔒 Доступ строго ограничен. Все действия фиксируются в аудит-журнале."
        "</blockquote>\n\n"
        "🛠 <b>Быстрые команды:</b>\n"
        "▫️ <code>/dashboard</code> — главный экран мониторинга и метрик\n"
        "▫️ <code>/restart</code> — перезапуск процесса расписания\n"
        "▫️ <code>/pull</code> — подтянуть обновления Git (origin/main)\n"
        "▫️ <code>/logs</code> — просмотр последних логов и ошибок\n"
        "▫️ <code>/roles</code> — список администраторов и старост\n"
        "▫️ <code>/set_role &lt;user&gt; &lt;role&gt; [группа]</code> — назначение роли\n"
        "▫️ <code>/broadcast</code> — экстренная рассылка студентам\n\n"
        "👇 <i>Используйте интерактивную панель управления ниже:</i>\n"
    )

    dash_text, is_running = await render_dashboard_text()
    kb = get_dashboard_keyboard(is_running=is_running)

    await message.answer(intro + dash_text, reply_markup=kb)
