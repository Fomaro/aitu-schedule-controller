import html
from aiogram import Router, F, types
from aiogram.filters import Command
from filters.superadmin import IsSuperAdminFilter
from services.git_service import git_service
from services.supervisor import supervisor
from keyboards.git_kb import get_git_keyboard

router = Router(name="git_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


async def _render_git_menu(event: types.Message | types.CallbackQuery, extra_text: str | None = None):
    git_info = await git_service.get_info()
    behind = git_info.get("behind_count", 0)
    kb = get_git_keyboard(behind_count=behind)

    dirty_files = git_info.get("dirty_files", [])
    if dirty_files:
        files_str = "\n".join(f"  ▫️ <code>{html.escape(f)}</code>" for f in dirty_files[:5])
        if len(dirty_files) > 5:
            files_str += f"\n  ▫️ <i>...и ещё {len(dirty_files) - 5} файлов</i>"
        status_icon = f"⚠️ <b>Есть незакоммиченные файлы ({len(dirty_files)}):</b>\n{files_str}"
    else:
        status_icon = "Чисто (всё закоммичено) ✅"

    behind_desc = f"\n⚠️ <b>Внимание:</b> удалённый репозиторий опережает локальный на <b>{behind}</b> коммитов!" if behind > 0 else ""

    lines = [
        "📦 <b>УПРАВЛЕНИЕ РЕПОЗИТОРИЕМ И ОБНОВЛЕНИЯМИ</b>",
        "────────────────────────",
        f"▫️ Ветка: <code>{git_info['branch']}</code>",
        f"▫️ Последний коммит: <code>{git_info['commit']}</code> ({git_info['date']})",
        f"▫️ Автор коммита: <code>{git_info['author']}</code>",
        f"▫️ Сообщение: <i>{html.escape(git_info['message'])}</i>",
        f"▫️ Статус рабочей папки:\n{status_icon}{behind_desc}"
    ]

    if extra_text:
        lines.append("\n" + extra_text)

    text = "\n".join(lines)

    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except Exception:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data.in_(["menu_git", "git_check_status"]))
async def cb_menu_git(call: types.CallbackQuery):
    await _render_git_menu(call)


@router.callback_query(F.data == "git_pull_only")
async def cb_git_pull_only(call: types.CallbackQuery):
    await call.answer("Выполняю git pull origin main...")
    ok, output, reqs_changed = await git_service.pull()
    
    extra = (
        "✅ <b>Git pull выполнен успешно!</b>\n\n"
        f"<pre>{html.escape(output[:1200])}</pre>"
    ) if ok else (
        "❌ <b>Ошибка при выполнении git pull:</b>\n\n"
        f"<pre>{html.escape(output[:1200])}</pre>"
    )
    if reqs_changed:
        extra += "\n\n⚠️ <i>Обнаружены изменения в requirements.txt! Рекомендуется обновить зависимости окружения.</i>"

    await _render_git_menu(call, extra_text=extra)


@router.callback_query(F.data == "git_pull_restart")
async def cb_git_pull_restart(call: types.CallbackQuery):
    await call.answer("Выполняю Pull & Перезапуск...")
    ok, output, reqs_changed = await git_service.pull()

    if not ok:
        extra = f"❌ <b>Git pull завершился с ошибкой:</b>\n<pre>{html.escape(output[:1000])}</pre>\nПерезапуск отменён."
        await _render_git_menu(call, extra_text=extra)
        return

    # Перезапускаем целевой бот
    re_ok, re_msg = await supervisor.restart()
    extra = (
        "🚀 <b>Обновление и перезапуск завершены!</b>\n\n"
        f"▫️ Git Pull: <pre>{html.escape(output[:600])}</pre>\n"
        f"▫️ Перезапуск бота: <b>{re_msg}</b>"
    )
    if reqs_changed:
        extra += "\n\n⚠️ <i>Обновлены зависимости в requirements.txt!</i>"

    await _render_git_menu(call, extra_text=extra)


@router.callback_query(F.data == "git_recent_commits")
async def cb_git_recent_commits(call: types.CallbackQuery):
    commits = await git_service.get_recent_commits(limit=7)
    if commits:
        text = "📋 <b>ПОСЛЕДНИЕ КОММИТЫ В РЕПОЗИТОРИИ:</b>\n────────────────────────\n" + "\n".join(commits)
    else:
        text = "<i>Не удалось получить историю коммитов.</i>"

    await _render_git_menu(call, extra_text=text)


@router.callback_query(F.data == "git_reset_hard")
async def cb_git_reset_hard(call: types.CallbackQuery):
    await call.answer("Выполняю очистку рабочего дерева...")
    ok, output = await git_service.reset_hard()
    extra = (
        "✅ <b>Рабочее дерево успешно очищено (git reset --hard & clean)!</b>\n\n"
        f"<pre>{html.escape(output[:1000])}</pre>"
    ) if ok else (
        "❌ <b>Ошибка при очистке:</b>\n\n"
        f"<pre>{html.escape(output[:1000])}</pre>"
    )
    await _render_git_menu(call, extra_text=extra)


# Команды
@router.message(Command("pull"))
async def cmd_pull(message: types.Message):
    wait_msg = await message.answer("⏳ <i>Подтягиваю изменения из Git репозитория...</i>")
    ok, output, reqs_changed = await git_service.pull()
    if ok:
        res = f"✅ <b>Git pull выполнен!</b>\n\n<pre>{html.escape(output[:1200])}</pre>"
        if reqs_changed:
            res += "\n\n⚠️ <i>Внимание: изменился requirements.txt!</i>"
    else:
        res = f"❌ <b>Ошибка Git pull:</b>\n\n<pre>{html.escape(output[:1200])}</pre>"
    await wait_msg.edit_text(res)


@router.message(Command("commits"))
async def cmd_commits(message: types.Message):
    commits = await git_service.get_recent_commits(limit=7)
    text = "📋 <b>Последние коммиты:</b>\n\n" + "\n".join(commits) if commits else "История пуста."
    await message.answer(text)
