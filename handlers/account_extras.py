"""
Дополнительные обработчики для аккаунтов:
  setpass_   — установить / удалить пароль 2FA
  getcode_   — запросить код авторизации
  recreate_  — пересоздать сессию (реконнект)

Эти хэндлеры не вошли в accounts.py,
поэтому вынесены в отдельный файл.
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter

from database.db import get_account
from services import telethon_service as tg
from handlers.keyboards import kb_back

router = Router()


# ── FSM STATE ────────────────────────────────────────────────────────────────

class SetPassState(StatesGroup):
    waiting = State()


# ── УСТАНОВИТЬ ПАРОЛЬ 2FA ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("setpass_"))
async def cb_setpass_start(call: CallbackQuery, state: FSMContext):
    acc_id = int(call.data.split("_")[1])
    await state.set_state(SetPassState.waiting)
    await state.update_data(acc_id=acc_id)
    await call.message.edit_text(
        "🔐 <b>Пароль 2FA</b>\n\n"
        "Введи <b>новый пароль</b> для двухфакторной аутентификации.\n"
        "Чтобы <b>удалить</b> текущий пароль — отправь <code>-</code>",
        parse_mode="HTML",
        reply_markup=kb_back(f"acc_{acc_id}"),
    )


@router.message(StateFilter(SetPassState.waiting))
async def fsm_setpass(message: Message, state: FSMContext):
    data   = await state.get_data()
    acc_id = data["acc_id"]
    acc    = await get_account(acc_id)
    new_pw = message.text.strip()

    try:
        client = await tg.get_client(acc["session_file"])

        if new_pw == "-":
            # Telethon: remove password — нужен текущий пароль,
            # поэтому делаем edit_2fa без new_password
            await client.edit_2fa(new_password=None)
            await state.clear()
            await message.answer(
                "✅ Пароль 2FA удалён.",
                reply_markup=kb_back(f"acc_{acc_id}"),
            )
        else:
            await client.edit_2fa(new_password=new_pw)
            await state.clear()
            await message.answer(
                f"✅ Пароль 2FA установлен:\n<code>{new_pw}</code>\n\n"
                f"⚠️ Сохрани его в надёжном месте!",
                parse_mode="HTML",
                reply_markup=kb_back(f"acc_{acc_id}"),
            )
    except Exception as e:
        await state.clear()
        await message.answer(
            f"❌ Ошибка: {e}",
            reply_markup=kb_back(f"acc_{acc_id}"),
        )


# ── ПОЛУЧИТЬ КОД АВТОРИЗАЦИИ ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("getcode_"))
async def cb_getcode(call: CallbackQuery):
    acc_id = int(call.data.split("_")[1])
    acc    = await get_account(acc_id)
    await call.answer("⏳ Запрашиваю код...")

    try:
        client = await tg.get_client(acc["session_file"])
        me     = await client.get_me()
        if not me or not me.phone:
            raise ValueError("Не удалось получить номер аккаунта.")

        await client.send_code_request(me.phone)

        await call.message.edit_text(
            f"📲 Код авторизации отправлен на номер\n"
            f"<code>+{me.phone}</code>\n\n"
            f"Проверь Telegram (системное сообщение) или SMS.",
            parse_mode="HTML",
            reply_markup=kb_back(f"acc_{acc_id}"),
        )
    except Exception as e:
        await call.message.edit_text(
            f"❌ Ошибка: {e}",
            reply_markup=kb_back(f"acc_{acc_id}"),
        )


# ── ПЕРЕСОЗДАТЬ СЕССИЮ (реконнект) ────────────────────────────────────────────

@router.callback_query(F.data.startswith("recreate_"))
async def cb_recreate(call: CallbackQuery):
    acc_id = int(call.data.split("_")[1])
    acc    = await get_account(acc_id)
    msg    = await call.message.edit_text("⏳ Пересоздаю сессию...")

    try:
        # Отключить текущий клиент если он есть
        await tg.disconnect_client(acc["session_file"])

        # Заново подключить
        client = await tg.get_client(acc["session_file"])

        if await client.is_user_authorized():
            me = await client.get_me()
            name = f"{me.first_name or ''} @{me.username}" if me.username else (me.first_name or "—")
            await msg.edit_text(
                f"✅ Сессия успешно пересоздана!\n\n"
                f"👤 Аккаунт: <b>{name}</b>",
                parse_mode="HTML",
                reply_markup=kb_back(f"acc_{acc_id}"),
            )
        else:
            await msg.edit_text(
                "⚠️ Сессия пересоздана, но авторизация потеряна.\n"
                "Возможно сессия устарела.",
                reply_markup=kb_back(f"acc_{acc_id}"),
            )
    except Exception as e:
        await msg.edit_text(
            f"❌ Ошибка: {e}",
            reply_markup=kb_back(f"acc_{acc_id}"),
        )
