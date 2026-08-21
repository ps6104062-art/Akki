import os
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, Document
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter

from database.db import (
    get_user, add_account, get_user_accounts, get_account,
    update_account_status, delete_account, add_to_shop,
)
from services import telethon_service as tg
from handlers.keyboards import (
    kb_account_list, kb_account_menu, kb_sessions,
    kb_confirm, kb_back, kb_reactions,
)
from config import SESSIONS_DIR

router = Router()


# ── FSM States ─────────────────────────────────────────────────────────────────

class AuthPhone(StatesGroup):
    phone    = State()
    code     = State()
    password = State()

class BroadcastState(StatesGroup):
    targets = State()
    message = State()
    delay   = State()

class ReactState(StatesGroup):
    emoji   = State()
    target  = State()
    count   = State()
    delay   = State()

class ToShop(StatesGroup):
    price    = State()
    currency = State()
    desc     = State()

class SetPass(StatesGroup):
    waiting = State()


# ── Хелпер: проверка роли ──────────────────────────────────────────────────────

async def is_admin(user_id: int) -> bool:
    user = await get_user(user_id)
    return user and user["role"] in ("admin", "superadmin")


# ── МОИ АККАУНТЫ ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_accounts")
async def cb_my_accounts(call: CallbackQuery):
    await call.answer()
    if not await is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    accounts = await get_user_accounts(call.from_user.id)
    if not accounts:
        await call.message.edit_text(
            "📭 У тебя пока нет аккаунтов.\n\nДобавь через кнопку ➕",
            reply_markup=kb_back("main"),
        )
        return
    await call.message.edit_text(
        f"📱 <b>Твои аккаунты</b> ({len(accounts)} шт.)\n\nВыбери аккаунт:",
        reply_markup=kb_account_list(accounts),
        parse_mode="HTML",
    )


# ── ДОБАВИТЬ АККАУНТ ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "add_account")
async def cb_add_account(call: CallbackQuery):
    await call.answer()
    if not await is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    from handlers.keyboards import kb_add_account
    await call.message.edit_text(
        "➕ <b>Добавить аккаунт</b>\n\nВыбери способ:",
        reply_markup=kb_add_account(),
        parse_mode="HTML",
    )


# ── АВТОРИЗАЦИЯ ЧЕРЕЗ НОМЕР ────────────────────────────────────────────────────

@router.callback_query(F.data == "auth_phone")
async def cb_auth_phone(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AuthPhone.phone)
    await call.message.edit_text(
        "📞 Введи номер телефона в формате:\n<code>+79991234567</code>",
        parse_mode="HTML",
        reply_markup=kb_back("add_account"),
    )


@router.message(StateFilter(AuthPhone.phone))
async def fsm_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    msg = await message.answer("⏳ Отправляю код...")
    try:
        session_name = await tg.start_auth(message.from_user.id, phone)
        await state.update_data(phone=phone, session_name=session_name)
        await state.set_state(AuthPhone.code)
        await msg.edit_text(
            f"📲 Код отправлен на <code>{phone}</code>\n\nВведи код из Telegram/SMS:",
            parse_mode="HTML",
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")
        await state.clear()


@router.message(StateFilter(AuthPhone.code))
async def fsm_code(message: Message, state: FSMContext):
    code = message.text.strip()
    msg = await message.answer("⏳ Проверяю код...")
    try:
        result = await tg.submit_code(message.from_user.id, code)
        if result == "ok":
            data = await state.get_data()
            session_file = data["session_name"] + ".session"
            acc_id = await add_account(message.from_user.id, data["phone"], session_file)
            await state.clear()
            await msg.edit_text(
                f"✅ Аккаунт <code>{data['phone']}</code> успешно добавлен!",
                parse_mode="HTML",
                reply_markup=kb_account_menu(acc_id),
            )
        elif result == "2fa":
            await state.set_state(AuthPhone.password)
            await msg.edit_text("🔐 Требуется пароль 2FA. Введи пароль:")
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


@router.message(StateFilter(AuthPhone.password))
async def fsm_password(message: Message, state: FSMContext):
    msg = await message.answer("⏳ Проверяю пароль...")
    try:
        session_file = await tg.submit_password(message.from_user.id, message.text.strip())
        data = await state.get_data()
        acc_id = await add_account(message.from_user.id, data["phone"], session_file)
        await state.clear()
        await msg.edit_text(
            f"✅ Аккаунт добавлен!",
            reply_markup=kb_account_menu(acc_id),
        )
    except Exception as e:
        await msg.edit_text(f"❌ Неверный пароль: {e}")


# ── ЗАГРУЗКА .SESSION ФАЙЛА ────────────────────────────────────────────────────

@router.callback_query(F.data == "auth_session")
async def cb_auth_session(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state("wait_session_file")
    await call.message.edit_text(
        "📂 Отправь <b>.session</b> файл:",
        parse_mode="HTML",
        reply_markup=kb_back("add_account"),
    )


@router.message(StateFilter("wait_session_file"), F.document)
async def fsm_session_file(message: Message, state: FSMContext, bot: Bot):
    doc: Document = message.document
    if not doc.file_name.endswith(".session"):
        await message.answer("❌ Нужен файл с расширением .session")
        return

    msg = await message.answer("⏳ Загружаю и проверяю сессию...")
    file_path = os.path.join(SESSIONS_DIR, doc.file_name)
    await bot.download(doc, destination=file_path)

    ok = await tg.load_session_file(file_path)
    if not ok:
        await msg.edit_text("❌ Сессия недействительна или устарела.")
        os.remove(file_path)
        return

    me = await tg.get_me(doc.file_name)
    acc_id = await add_account(
        message.from_user.id,
        me.get("phone", ""),
        doc.file_name,
    )
    await state.clear()
    await msg.edit_text(
        f"✅ Аккаунт <b>{me['first_name']}</b> (@{me['username']}) загружен!",
        parse_mode="HTML",
        reply_markup=kb_account_menu(acc_id),
    )


# ── МАССОВАЯ ЗАГРУЗКА ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "auth_bulk")
async def cb_auth_bulk(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state("wait_bulk_sessions")
    await call.message.edit_text(
        "📦 Отправляй .session файлы по одному.\n"
        "Когда закончишь — напиши /done",
        reply_markup=kb_back("add_account"),
    )
    await state.update_data(bulk_count=0)


@router.message(StateFilter("wait_bulk_sessions"), F.document)
async def fsm_bulk_file(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    if not doc.file_name.endswith(".session"):
        return
    data = await state.get_data()
    file_path = os.path.join(SESSIONS_DIR, doc.file_name)
    await bot.download(doc, destination=file_path)
    ok = await tg.load_session_file(file_path)
    if ok:
        me = await tg.get_me(doc.file_name)
        await add_account(message.from_user.id, me.get("phone", ""), doc.file_name)
        count = data.get("bulk_count", 0) + 1
        await state.update_data(bulk_count=count)
        await message.answer(f"✅ Загружено: {count} аккаунтов")
    else:
        await message.answer(f"❌ {doc.file_name} — невалидная сессия, пропущен.")


@router.message(StateFilter("wait_bulk_sessions"), F.text == "/done")
async def fsm_bulk_done(message: Message, state: FSMContext):
    data = await state.get_data()
    count = data.get("bulk_count", 0)
    await state.clear()
    await message.answer(
        f"✅ Массовая загрузка завершена!\nДобавлено аккаунтов: <b>{count}</b>",
        parse_mode="HTML",
        reply_markup=kb_back("my_accounts"),
    )


# ── МЕНЮ АККАУНТА ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("acc_"))
async def cb_account_menu(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[1])
    acc = await get_account(acc_id)
    if not acc:
        await call.answer("Аккаунт не найден", show_alert=True)
        return
    status_map = {"active": "🟢 Активен", "shop": "🛒 В магазине", "sold": "🔴 Продан", "banned": "⛔ Заблокирован"}
    await call.message.edit_text(
        f"📱 <b>Аккаунт</b>\n\n"
        f"Номер: <code>{acc['phone'] or '—'}</code>\n"
        f"Файл: <code>{acc['session_file']}</code>\n"
        f"Статус: {status_map.get(acc['status'], acc['status'])}\n"
        f"Добавлен: {acc['added_at'][:10]}\n\n"
        f"Выбери действие:",
        reply_markup=kb_account_menu(acc_id),
        parse_mode="HTML",
    )


# ── СЕССИИ ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sessions_"))
async def cb_sessions(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[1])
    acc = await get_account(acc_id)
    msg = await call.message.edit_text("⏳ Загружаю сессии...")
    try:
        sessions = await tg.get_sessions(acc["session_file"])
        text = "📋 <b>Активные сессии</b>\nНажми на сессию чтобы кикнуть:\n\n"
        for s in sessions:
            icon = "🟢" if s["current"] else "📱"
            text += f"{icon} <b>{s['device']}</b> · {s['platform']}\n"
            text += f"   IP: <code>{s['ip']}</code> · {s['country']}\n"
            text += f"   Активна: {s['active']}\n\n"
        await msg.edit_text(text, reply_markup=kb_sessions(sessions, acc_id), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}", reply_markup=kb_back(f"acc_{acc_id}"))


@router.callback_query(F.data.startswith("kick_"))
async def cb_kick_session(call: CallbackQuery):
    await call.answer()
    _, acc_id_str, session_hash_str = call.data.split("_", 2)
    acc_id = int(acc_id_str)
    acc = await get_account(acc_id)
    try:
        await tg.kick_session(acc["session_file"], int(session_hash_str))
        await call.answer("✅ Сессия завершена!", show_alert=True)
        sessions = await tg.get_sessions(acc["session_file"])
        await call.message.edit_reply_markup(reply_markup=kb_sessions(sessions, acc_id))
    except Exception as e:
        await call.answer(f"❌ {e}", show_alert=True)


@router.callback_query(F.data.startswith("kickall_confirm_"))
async def cb_kickall_confirm(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[2])
    acc = await get_account(acc_id)
    try:
        await tg.kick_all_sessions(acc["session_file"])
        await call.message.edit_text(
            "✅ Все сессии кроме текущей завершены!",
            reply_markup=kb_back(f"acc_{acc_id}"),
        )
    except Exception as e:
        await call.message.edit_text(f"❌ Ошибка: {e}", reply_markup=kb_back(f"acc_{acc_id}"))


@router.callback_query(F.data.startswith("kickall_"))
async def cb_kickall(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[1])
    await call.message.edit_text(
        "⚡ Кикнуть все сессии кроме текущей?",
        reply_markup=kb_confirm(f"kickall_confirm_{acc_id}", f"acc_{acc_id}"),
    )


# ── ОЧИСТКА ЧАТОВ ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("clearchats_confirm_"))
async def cb_clearchats_confirm(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[2])
    acc = await get_account(acc_id)
    msg = await call.message.edit_text("⏳ Очищаю чаты, это займёт время...")
    try:
        count = await tg.clear_all_chats(acc["session_file"])
        await msg.edit_text(f"✅ Очищено {count} диалогов!", reply_markup=kb_back(f"acc_{acc_id}"))
    except Exception as e:
        await msg.edit_text(f"❌ {e}", reply_markup=kb_back(f"acc_{acc_id}"))


@router.callback_query(F.data.startswith("clearchats_"))
async def cb_clearchats(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[1])
    await call.message.edit_text(
        "🗑 <b>Фулл очистка чатов</b>\n\n⚠️ Будет удалена ВСЯ история. Необратимо!",
        reply_markup=kb_confirm(f"clearchats_confirm_{acc_id}", f"acc_{acc_id}"),
        parse_mode="HTML",
    )


# ── ОЧИСТКА КОНТАКТОВ ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("clearcontacts_confirm_"))
async def cb_clearcontacts_confirm(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[2])
    acc = await get_account(acc_id)
    try:
        count = await tg.clear_contacts(acc["session_file"])
        await call.message.edit_text(f"✅ Удалено {count} контактов!", reply_markup=kb_back(f"acc_{acc_id}"))
    except Exception as e:
        await call.message.edit_text(f"❌ {e}", reply_markup=kb_back(f"acc_{acc_id}"))


@router.callback_query(F.data.startswith("clearcontacts_"))
async def cb_clearcontacts(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[1])
    await call.message.edit_text(
        "👥 Удалить все контакты?",
        reply_markup=kb_confirm(f"clearcontacts_confirm_{acc_id}", f"acc_{acc_id}"),
    )


# ── РАССЫЛКА ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("broadcast_"))
async def cb_broadcast_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    acc_id = int(call.data.split("_")[1])
    await state.set_state(BroadcastState.targets)
    await state.update_data(acc_id=acc_id)
    await call.message.edit_text(
        "📢 <b>Рассылка</b>\n\nВведи получателей через запятую:\n"
        "<code>@user1, @user2, +79991234567</code>",
        parse_mode="HTML",
        reply_markup=kb_back(f"acc_{acc_id}"),
    )


@router.message(StateFilter(BroadcastState.targets))
async def fsm_broadcast_targets(message: Message, state: FSMContext):
    targets = [t.strip() for t in message.text.split(",") if t.strip()]
    await state.update_data(targets=targets)
    await state.set_state(BroadcastState.message)
    await message.answer(f"✅ Получателей: {len(targets)}\n\nТеперь введи текст сообщения:")


@router.message(StateFilter(BroadcastState.message))
async def fsm_broadcast_message(message: Message, state: FSMContext):
    await state.update_data(message=message.text)
    await state.set_state(BroadcastState.delay)
    await message.answer("⏱ Задержка между сообщениями (секунды):\nНапример: <code>1.5</code>", parse_mode="HTML")


@router.message(StateFilter(BroadcastState.delay))
async def fsm_broadcast_delay(message: Message, state: FSMContext):
    try:
        delay = float(message.text.strip())
    except ValueError:
        delay = 1.5

    data = await state.get_data()
    await state.clear()

    acc = await get_account(data["acc_id"])
    msg = await message.answer(f"📢 Запускаю рассылку для {len(data['targets'])} адресатов...")

    async def progress(i, total, sent, failed):
        if i % 5 == 0 or i == total:
            await msg.edit_text(f"📢 Рассылка: {i}/{total}\n✅ Отправлено: {sent}  ❌ Ошибок: {failed}")

    result = await tg.broadcast(acc["session_file"], data["targets"], data["message"], delay, progress)
    await msg.edit_text(
        f"✅ Рассылка завершена!\n\nОтправлено: {result['sent']}\nОшибок: {result['failed']}",
        reply_markup=kb_back(f"acc_{data['acc_id']}"),
    )


# ── РЕАКЦИИ ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("reactions_"))
async def cb_reactions(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[1])
    await call.message.edit_text(
        "❤️ <b>Массовые реакции</b>\n\nВыбери реакцию:",
        reply_markup=kb_reactions(acc_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("react_pick_"))
async def cb_react_pick(call: CallbackQuery, state: FSMContext):
    await call.answer()
    parts = call.data.split("_", 3)
    acc_id = int(parts[2])
    emoji  = parts[3]
    await state.set_state(ReactState.target)
    await state.update_data(acc_id=acc_id, emoji=emoji)
    await call.message.edit_text(
        f"Выбрана реакция: {emoji}\n\nВведи @username или ID канала/чата:",
        reply_markup=kb_back(f"reactions_{acc_id}"),
    )


@router.message(StateFilter(ReactState.target))
async def fsm_react_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    await state.set_state(ReactState.count)
    await message.answer("Сколько постов реагировать? Введи число (например: <code>50</code>):", parse_mode="HTML")


@router.message(StateFilter(ReactState.count))
async def fsm_react_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
    except ValueError:
        count = 20
    await state.update_data(count=count)
    await state.set_state(ReactState.delay)
    await message.answer("Задержка (секунды, например <code>1.5</code>):", parse_mode="HTML")


@router.message(StateFilter(ReactState.delay))
async def fsm_react_delay(message: Message, state: FSMContext):
    try:
        delay = float(message.text.strip())
    except ValueError:
        delay = 1.5

    data = await state.get_data()
    await state.clear()

    acc = await get_account(data["acc_id"])
    msg = await message.answer(f"⚡ Запускаю реакции {data['emoji']} на {data['count']} постов...")

    async def progress(i, total, sent):
        if i % 10 == 0 or i == total:
            await msg.edit_text(f"⚡ Реакции: {i}/{total}  ✅ {sent}")

    result = await tg.send_reactions(
        acc["session_file"], data["target"], data["emoji"], data["count"], delay, progress
    )
    await msg.edit_text(
        f"✅ Готово!\nПоставлено реакций {data['emoji']}: {result['sent']}/{result['total']}",
        reply_markup=kb_back(f"acc_{data['acc_id']}"),
    )


#── В МАГАЗИН ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("toshop_"))
async def cb_toshop(call: CallbackQuery, state: FSMContext):
    await call.answer()
    acc_id = int(call.data.split("_")[1])
    await state.set_state(ToShop.price)
    await state.update_data(acc_id=acc_id)
    await call.message.edit_text(
        "🛒 <b>Добавить в магазин</b>\n\nВведи цену (например: <code>5.00</code>):",
        parse_mode="HTML",
        reply_markup=kb_back(f"acc_{acc_id}"),
    )


@router.message(StateFilter(ToShop.price))
async def fsm_shop_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи число, например: 5.00")
        return
    await state.update_data(price=price)
    await state.set_state(ToShop.currency)
    await message.answer("Валюта (USDT / TON / BTC):")


@router.message(StateFilter(ToShop.currency))
async def fsm_shop_currency(message: Message, state: FSMContext):
    await state.update_data(currency=message.text.strip().upper())
    await state.set_state(ToShop.desc)
    await message.answer("Описание аккаунта (или напиши <code>-</code> чтобы пропустить):", parse_mode="HTML")


@router.message(StateFilter(ToShop.desc))
async def fsm_shop_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await add_to_shop(data["acc_id"], data["price"], data["currency"], desc)
    await state.clear()
    await message.answer(
        f"✅ Аккаунт выставлен в магазин за {data['price']} {data['currency']}!",
        reply_markup=kb_back(f"acc_{data['acc_id']}"),
    )


#── УДАЛИТЬ АККАУНТ ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("delacc_confirm_"))
async def cb_delete_confirm(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[2])
    await delete_account(acc_id)
    await call.message.edit_text("✅ Аккаунт удалён.", reply_markup=kb_back("my_accounts"))


@router.callback_query(F.data.startswith("delacc_"))
async def cb_delete_account(call: CallbackQuery):
    await call.answer()
    acc_id = int(call.data.split("_")[1])
    await call.message.edit_text(
        "🗑 Удалить аккаунт из базы?",
        reply_markup=kb_confirm(f"delacc_confirm_{acc_id}", f"acc_{acc_id}"),
    )
