import html
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from filters.superadmin import IsSuperAdminFilter
from services.db_service import db_service
from keyboards.roles_kb import get_roles_keyboard
from config import SUPERADMIN_IDS

router = Router(name="roles_router")
router.message.filter(IsSuperAdminFilter())
router.callback_query.filter(IsSuperAdminFilter())


class RoleAssignState(StatesGroup):
    waiting_for_user_ident = State()
    waiting_for_group_name = State()


@router.callback_query(F.data == "menu_roles")
async def cb_menu_roles(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = get_roles_keyboard()
    text = (
        "👥 <b>УПРАВЛЕНИЕ РОЛЯМИ И ДОСТУПОМ В БОТЕ</b>\n"
        "────────────────────────\n"
        "Здесь вы можете централизованно управлять правами в целевом боте расписания:\n\n"
        "▫️ <b>Superadmin (👑):</b> Главный администратор всей инфраструктуры\n"
        "▫️ <b>Admin (🛡):</b> Администратор бота расписания (рассылки, замены)\n"
        "▫️ <b>Starosta (⭐️):</b> Староста группы (кабинет старосты, замены своей группы)\n"
        "▫️ <b>Zam. Starosty (⚡️):</b> Заместитель старосты\n"
        "▫️ <b>Student (👨‍🎓):</b> Обычный студент (базовый доступ к расписанию)\n\n"
        "👇 <i>Выберите действие ниже или используйте команду:</i>\n"
        "<code>/set_role &lt;@username или ID&gt; &lt;роль&gt; [группа]</code>"
    )
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "roles_list_elevated")
async def cb_roles_list_elevated(call: types.CallbackQuery):
    officers = await db_service.get_elevated_users()
    kb = get_roles_keyboard()

    if not officers:
        text = "👥 <b>Список пользователей с особыми ролями пуст.</b>"
    else:
        superadmins_str = ", ".join(str(uid) for uid in SUPERADMIN_IDS) if SUPERADMIN_IDS else "указаны в .env"
        lines = [
            "👥 <b>ПОЛЬЗОВАТЕЛИ С РАСШИРЕННЫМИ РОЛЯМИ:</b>",
            "────────────────────────",
            f"👑 <b>Superadmins ({len(SUPERADMIN_IDS)}):</b> <code>{superadmins_str}</code>\n"
        ]
        for u in officers:
            u_name = f"@{u['username']}" if u.get("username") else (u.get("full_name") or str(u["user_id"]))
            role_ru = {
                "superadmin": "👑 SUPERADMIN",
                "admin": "🛡 АДМИНИСТРАТОР",
                "starosta": "⭐️ СТАРОСТА",
                "zam_starosty": "⚡️ ЗАМ. СТАРОСТЫ"
            }.get(u["role"], u["role"].upper())
            grp = u.get("group_name") or "—"
            lines.append(f"• <b>{role_ru}</b> | {html.escape(u_name)} | Группа: <code>{grp}</code> (ID: <code>{u['user_id']}</code>)")

        lines.append(f"\nВсего привилегированных пользователей: <b>{len(officers)}</b>")
        text = "\n".join(lines)

    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.in_(["roles_assign_admin", "roles_assign_starosta", "roles_demote_user", "roles_search_user"]))
async def cb_roles_prompt_user(call: types.CallbackQuery, state: FSMContext):
    action = call.data
    await state.set_state(RoleAssignState.waiting_for_user_ident)
    await state.update_data(role_action=action)

    prompts = {
        "roles_assign_admin": "🛡 Введите <b>@username</b> или <b>Telegram ID</b> пользователя для назначения <b>Администратором</b> бота:",
        "roles_assign_starosta": "⭐️ Введите <b>@username</b> или <b>Telegram ID</b> пользователя для назначения <b>Старостой</b>:",
        "roles_demote_user": "👨‍🎓 Введите <b>@username</b> или <b>Telegram ID</b> пользователя для сброса роли в <b>Student</b>:",
        "roles_search_user": "🔍 Введите <b>@username</b> или <b>Telegram ID</b> пользователя для поиска по базе:"
    }

    cancel_kb = InlineKeyboardBuilder()
    cancel_kb.button(text="❌ Отмена", callback_data="menu_roles")

    text = (
        f"{prompts.get(action, 'Введите идентификатор пользователя:')}\n\n"
        "<i>Пользователь должен быть зарегистрирован в основном боте расписания (хотя бы раз нажать /start).</i>"
    )
    await call.message.edit_text(text, reply_markup=cancel_kb.as_markup())
    await call.answer()


@router.message(RoleAssignState.waiting_for_user_ident)
async def handle_user_ident_input(message: types.Message, state: FSMContext):
    text_val = (message.text or "").strip()
    user_data = await state.get_data()
    action = user_data.get("role_action", "")

    found_user = await db_service.find_user(text_val)
    if not found_user:
        await message.answer(
            f"❌ Пользователь <code>{html.escape(text_val)}</code> не найден в базе schedule_bot.db.\n\n"
            "Пользователь должен сначала отправить команду <code>/start</code> в основном боте расписания."
        )
        await state.clear()
        return

    uid = found_user["user_id"]
    u_name = f"@{found_user['username']}" if found_user.get("username") else (found_user.get("full_name") or str(uid))
    current_role = found_user.get("role", "student")
    current_group = found_user.get("group_name") or "—"

    if action == "roles_search_user":
        await state.clear()
        res_text = (
            f"👤 <b>КАРТОЧКА ПОЛЬЗОВАТЕЛЯ:</b>\n"
            f"────────────────────────\n"
            f"▫️ Имя / Ник: {html.escape(u_name)}\n"
            f"▫️ Telegram ID: <code>{uid}</code>\n"
            f"▫️ Текущая роль: <b>{current_role}</b>\n"
            f"▫️ Академическая группа: <code>{current_group}</code>\n"
            f"▫️ Уведомления за 10 мин: {'Да' if found_user.get('remind_10min') else 'Нет'}\n"
            f"▫️ Утренняя сводка: {'Да' if found_user.get('morning_alert') else 'Нет'}"
        )
        await message.answer(res_text, reply_markup=get_roles_keyboard())
        return

    if action == "roles_assign_admin":
        await state.clear()
        ok, msg = await db_service.update_user_role(uid, "admin")
        if ok:
            await message.answer(f"✅ Пользователь <b>{u_name}</b> (ID: <code>{uid}</code>) успешно назначен <b>Администратором</b> бота!")
        else:
            await message.answer(f"❌ Ошибка: {msg}")
        return

    if action == "roles_demote_user":
        await state.clear()
        ok, msg = await db_service.update_user_role(uid, "student")
        if ok:
            await message.answer(f"✅ Роль пользователя <b>{u_name}</b> успешно сброшена в <b>Student</b>.")
        else:
            await message.answer(f"❌ Ошибка: {msg}")
        return

    if action == "roles_assign_starosta":
        await state.update_data(target_uid=uid, target_uname=u_name)
        await state.set_state(RoleAssignState.waiting_for_group_name)
        cancel_kb = InlineKeyboardBuilder()
        cancel_kb.button(text="❌ Отмена", callback_data="menu_roles")
        await message.answer(
            f"👤 Выбран пользователь: <b>{u_name}</b> (ID: <code>{uid}</code>)\n\n"
            f"📝 <b>Введите название академической группы</b>, старостой которой он назначается (например: <code>9ПО-43к</code>):",
            reply_markup=cancel_kb.as_markup()
        )


@router.message(RoleAssignState.waiting_for_group_name)
async def handle_group_name_input(message: types.Message, state: FSMContext):
    grp_name = (message.text or "").strip()
    data = await state.get_data()
    uid = data.get("target_uid")
    u_name = data.get("target_uname", "Пользователь")
    await state.clear()

    ok, msg = await db_service.update_user_role(uid, "starosta", group_name=grp_name)
    if ok:
        await message.answer(
            f"✅ Пользователь <b>{u_name}</b> успешно назначен <b>Старостой</b> группы <code>{grp_name}</code>!"
        )
    else:
        await message.answer(f"❌ Ошибка при назначении: {msg}")


# Команды
@router.message(Command("roles"))
async def cmd_roles(message: types.Message):
    officers = await db_service.get_elevated_users()
    if not officers:
        await message.answer("👥 Пользователей с особыми ролями в базе не найдено.")
        return
    lines = ["👥 <b>Администраторы и старосты:</b>\n────────────────────────"]
    for u in officers:
        u_name = f"@{u['username']}" if u.get("username") else (u.get("full_name") or str(u["user_id"]))
        lines.append(f"• <b>{u['role'].upper()}</b> | {html.escape(u_name)} | Группа: <code>{u.get('group_name') or '—'}</code> (ID: <code>{u['user_id']}</code>)")
    await message.answer("\n".join(lines))


@router.message(Command("set_role"))
async def cmd_set_role(message: types.Message):
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "ℹ️ <b>Формат команды:</b>\n"
            "<code>/set_role &lt;@username или ID&gt; &lt;роль&gt; [группа]</code>\n\n"
            "Роли: <code>superadmin</code>, <code>admin</code>, <code>starosta</code>, <code>zam_starosty</code>, <code>student</code>\n"
            "<i>Пример: <code>/set_role @ivanov starosta 9ПО-43к</code></i>"
        )
        return

    user_ident = parts[1].strip()
    role_str = parts[2].strip().lower()
    group_str = parts[3].strip() if len(parts) > 3 else None

    user = await db_service.find_user(user_ident)
    if not user:
        await message.answer(f"❌ Пользователь «{user_ident}» не найден в базе schedule_bot.db.")
        return

    ok, msg = await db_service.update_user_role(user["user_id"], role_str, group_name=group_str)
    if ok:
        u_name = f"@{user['username']}" if user.get("username") else str(user["user_id"])
        grp_info = f" (группа {group_str})" if group_str else ""
        await message.answer(f"✅ Пользователю <b>{u_name}</b> успешно назначена роль <b>{role_str}</b>{grp_info}!")
    else:
        await message.answer(f"❌ Ошибка: {msg}")
