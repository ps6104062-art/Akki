from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from database.db import get_user, create_user
from handlers.keyboards import kb_main_user, kb_main_admin, kb_main_superadmin
from config import ADMIN_ID

router = Router()


def get_main_kb(role: str):
    if role == "superadmin":
        return kb_main_superadmin()
    if role == "admin":
        return kb_main_admin()
    return kb_main_user()


def role_icon(role: str) -> str:
    return {"superadmin": "👑", "admin": "🛡", "user": "👤"}.get(role, "👤")


@router.message(CommandStart())
async def cmd_start(message: Message):
    uid  = message.from_user.id
    user = await get_user(uid)

    if not user:
        role = "superadmin" if uid == ADMIN_ID else "user"
        await create_user(
            uid,
            message.from_user.username or "",
            message.from_user.full_name or "",
            role,
        )
        user = await get_user(uid)

    icon = role_icon(user["role"])
    await message.answer(
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        f"{icon} Роль: <b>{user['role']}</b>\n\n"
        f"Выбери действие:",
        reply_markup=get_main_kb(user["role"]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        await call.answer("Сначала напиши /start")
        return
    icon = role_icon(user["role"])
    await call.message.edit_text(
        f"{icon} Роль: <b>{user['role']}</b>\n\nВыбери действие:",
        reply_markup=get_main_kb(user["role"]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery):
    from handlers.keyboards import kb_back
    user = await get_user(call.from_user.id)
    icon = role_icon(user["role"])
    await call.message.edit_text(
        f"👤 <b>Профиль</b>\n\n"
        f"ID: <code>{user['telegram_id']}</code>\n"
        f"Юзернейм: @{user['username'] or '—'}\n"
        f"Роль: {icon} {user['role']}\n"
        f"Зарегистрирован: {user['created_at'][:10]}",
        reply_markup=kb_back("main"),
        parse_mode="HTML",
    )
