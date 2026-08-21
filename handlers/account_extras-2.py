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
    await call.answer("⏳ Подготавливаю файлы...")
    acc_id = int(call.data.split("_")[1])
    acc    = await get_account(acc_id)

    try:
        import os
        from config import SESSIONS_DIR

        session_filename = acc["session_file"]
        session_path = os.path.join(SESSIONS_DIR, session_filename)

        # Отправляем .session файл
        if os.path.exists(session_path):
            await call.message.answer_document(
                FSInputFile(session_path, filename=session_filename),
                caption=f"📦 <b>Session файл</b>\nАккаунт: <code>{acc['phone'] or session_filename}</code>",
                parse_mode="HTML",
            )
        else:
            await call.message.answer("❌ Session файл не найден на сервере.")

        # Проверяем наличие tdata
        tdata_path = os.path.join(SESSIONS_DIR, session_filename.replace(".session", "_tdata"))
        if os.path.exists(tdata_path):
            import shutil
            zip_path = tdata_path + ".zip"
            shutil.make_archive(tdata_path, "zip", tdata_path)
            await call.message.answer_document(
                FSInputFile(zip_path, filename=os.path.basename(zip_path)),
                caption="📁 <b>Tdata архив</b>",
                parse_mode="HTML",
            )
            os.remove(zip_path)
        else:
            await call.message.answer(
                "ℹ️ Tdata для этого аккаунта отсутствует.",
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
