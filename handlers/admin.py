import aiosqlite
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter

from config import DB_PATH
from database.db import get_user, get_all_users, set_user_role
from handlers.keyboards import kb_back

router = Router()


# ── ВСПОМОГАТЕЛЬНЫЕ ───────────────────────────────────────────────────────────

class AdminFSM(StatesGroup):
    waiting_user_id = State()


async def is_superadmin(uid: int) -> bool:
    u = await get_user(uid)
    return bool(u and u["role"] == "superadmin")


async def is_admin_or_super(uid: int) -> bool:
    u = await get_user(uid)
    return bool(u and u["role"] in ("admin", "superadmin"))


def kb_admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Пользователи",     callback_data="users_list"),
            InlineKeyboardButton(text="🛡 Администраторы",   callback_data="admins_list"),
        ],
        [
            InlineKeyboardButton(text="➕ Назначить админа", callback_data="promote_admin"),
            InlineKeyboardButton(text="➖ Снять права",      callback_data="demote_admin"),
        ],
        [InlineKeyboardButton(text="📊 Статистика",          callback_data="stats")],
        [InlineKeyboardButton(text="◀️ Назад",               callback_data="main")],
    ])


# ── ПАНЕЛЬ СУПЕРАДМИНА ────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery):
    if not await is_superadmin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text(
        "⚙️ <b>Панель управления</b>\n\nВыбери действие:",
        reply_markup=kb_admin_panel(),
        parse_mode="HTML",
    )


# ── СТАТИСТИКА ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "stats")
async def cb_stats(call: CallbackQuery):
    if not await is_admin_or_super(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async def q(sql, *args):
            async with db.execute(sql, args) as cur:
                return (await cur.fetchone())[0]

        total_users    = await q("SELECT COUNT(*) FROM users")
        total_admins   = await q("SELECT COUNT(*) FROM users WHERE role IN ('admin','superadmin')")
        total_accounts = await q("SELECT COUNT(*) FROM accounts")
        active_acc     = await q("SELECT COUNT(*) FROM accounts WHERE status = 'active'")
        shop_acc       = await q("SELECT COUNT(*) FROM shop   WHERE status = 'available'")
        sold_acc       = await q("SELECT COUNT(*) FROM accounts WHERE status = 'sold'")
        paid_count     = await q("SELECT COUNT(*) FROM payments WHERE status = 'paid'")
        revenue        = await q("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='paid'")

    back_cb = "admin_panel" if await is_superadmin(call.from_user.id) else "main"
    await call.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{total_users}</b>\n"
        f"🛡 Администраторов: <b>{total_admins}</b>\n\n"
        f"📱 Всего аккаунтов: <b>{total_accounts}</b>\n"
        f"  🟢 Активных: <b>{active_acc}</b>\n"
        f"  🛒 В магазине: <b>{shop_acc}</b>\n"
        f"  🔴 Продано: <b>{sold_acc}</b>\n\n"
        f"💰 Успешных продаж: <b>{paid_count}</b>\n"
        f"💵 Общая выручка: <b>{revenue:.2f} USDT</b>",
        reply_markup=kb_back(back_cb),
        parse_mode="HTML",
    )


# ── СПИСОК ПОЛЬЗОВАТЕЛЕЙ ──────────────────────────────────────────────────────

@router.callback_query(F.data == "users_list")
async def cb_users_list(call: CallbackQuery):
    if not await is_admin_or_super(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    users = await get_all_users()
    icons = {"superadmin": "👑", "admin": "🛡", "user": "👤"}
    text  = f"👥 <b>Пользователи</b> ({len(users)})\n\n"
    for u in users[:25]:
        icon = icons.get(u["role"], "👤")
        name = f"@{u['username']}" if u["username"] else (u["full_name"] or "—")
        text += f"{icon} {name} · <code>{u['telegram_id']}</code>\n"
    if len(users) > 25:
        text += f"\n<i>...и ещё {len(users)-25} пользователей</i>"

    await call.message.edit_text(
        text,
        reply_markup=kb_back("admin_panel"),
        parse_mode="HTML",
    )


# ── СПИСОК АДМИНОВ ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admins_list")
async def cb_admins_list(call: CallbackQuery):
    if not await is_superadmin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    users  = await get_all_users()
    admins = [u for u in users if u["role"] in ("admin", "superadmin")]

    if not admins:
        await call.message.edit_text("Нет администраторов.", reply_markup=kb_back("admin_panel"))
        return

    text = f"🛡 <b>Администраторы</b> ({len(admins)})\n\n"
    for u in admins:
        icon = "👑" if u["role"] == "superadmin" else "🛡"
        name = f"@{u['username']}" if u["username"] else (u["full_name"] or "—")
        text += f"{icon} {name} · <code>{u['telegram_id']}</code>\n"

    await call.message.edit_text(text, reply_markup=kb_back("admin_panel"), parse_mode="HTML")


# ── НАЗНАЧИТЬ АДМИНА ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "promote_admin")
async def cb_promote(call: CallbackQuery, state: FSMContext):
    if not await is_superadmin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminFSM.waiting_user_id)
    await state.update_data(action="promote")
    await call.message.edit_text(
        "➕ Введи <b>Telegram ID</b> пользователя для назначения администратором:\n\n"
        "<i>Узнать ID можно через @userinfobot</i>",
        reply_markup=kb_back("admin_panel"),
        parse_mode="HTML",
    )


# ── СНЯТЬ АДМИНА ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "demote_admin")
async def cb_demote(call: CallbackQuery, state: FSMContext):
    if not await is_superadmin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminFSM.waiting_user_id)
    await state.update_data(action="demote")
    await call.message.edit_text(
        "➖ Введи <b>Telegram ID</b> администратора для снятия прав:",
        reply_markup=kb_back("admin_panel"),
        parse_mode="HTML",
    )


# ── FSM: обработка введённого ID ──────────────────────────────────────────────

@router.message(StateFilter(AdminFSM.waiting_user_id))
async def fsm_admin_action(message: Message, state: FSMContext):
    data   = await state.get_data()
    action = data.get("action", "")

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат. Введи числовой Telegram ID:")
        return

    user = await get_user(target_id)
    if not user:
        await message.answer(
            "❌ Пользователь не найден. Он должен сначала написать /start боту.",
            reply_markup=kb_back("admin_panel"),
        )
        await state.clear()
        return

    name = f"@{user['username']}" if user["username"] else (user["full_name"] or str(target_id))

    if action == "promote":
        if user["role"] in ("admin", "superadmin"):
            await message.answer(
                f"ℹ️ {name} уже является <b>{user['role']}</b>.",
                reply_markup=kb_back("admin_panel"),
                parse_mode="HTML",
            )
        else:
            await set_user_role(target_id, "admin")
            await message.answer(
                f"✅ {name} назначен <b>администратором</b>!",
                reply_markup=kb_back("admin_panel"),
                parse_mode="HTML",
            )

    elif action == "demote":
        if user["role"] == "superadmin":
            await message.answer(
                "❌ Нельзя снять главного администратора!",
                reply_markup=kb_back("admin_panel"),
            )
        elif user["role"] == "user":
            await message.answer(
                f"ℹ️ {name} уже обычный пользователь.",
                reply_markup=kb_back("admin_panel"),
            )
        else:
            await set_user_role(target_id, "user")
            await message.answer(
                f"✅ {name} разжалован до <b>пользователя</b>.",
                reply_markup=kb_back("admin_panel"),
                parse_mode="HTML",
            )

    await state.clear()
