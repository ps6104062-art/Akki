import aiosqlite
from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from config import DB_PATH, SESSIONS_DIR
from database.db import (
    get_shop_items, get_shop_item,
    create_payment, update_payment_status, mark_sold,
)
from services.cryptopay import create_invoice, check_invoice
from handlers.keyboards import kb_shop, kb_buy, kb_back

router = Router()


# ── СПИСОК МАГАЗИНА ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "shop")
async def cb_shop(call: CallbackQuery):
    items = await get_shop_items()
    if not items:
        await call.message.edit_text(
            "🛒 <b>Магазин аккаунтов</b>\n\n"
            "📭 Сейчас нет доступных аккаунтов.\n"
            "Загляни позже!",
            reply_markup=kb_back("main"),
            parse_mode="HTML",
        )
        return
    await call.message.edit_text(
        f"🛒 <b>Магазин аккаунтов</b>\n\n"
        f"✅ Доступно: <b>{len(items)}</b> аккаунтов\n"
        f"Оплата через @CryptoBot\n\n"
        f"Выбери аккаунт:",
        reply_markup=kb_shop(items),
        parse_mode="HTML",
    )


# ── ПОКУПКА — СОЗДАНИЕ ИНВОЙСА ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("buy_"))
async def cb_buy(call: CallbackQuery):
    shop_id = int(call.data.split("_")[1])
    item = await get_shop_item(shop_id)

    if not item or item.get("status") != "available":
        await call.answer("❌ Аккаунт уже продан или недоступен", show_alert=True)
        return

    description = item.get("description") or f"Telegram аккаунт {item.get('phone', '')}"

    try:
        invoice = await create_invoice(
            amount=item["price"],
            currency=item["currency"],
            description=description,
            payload=f"shop_{shop_id}_{call.from_user.id}",
        )
        await create_payment(
            user_id=call.from_user.id,
            account_id=item["account_id"],
            amount=item["price"],
            currency=item["currency"],
            invoice_id=invoice["invoice_id"],
        )
        await call.message.edit_text(
            f"💳 <b>Оплата аккаунта</b>\n\n"
            f"📱 Номер: <code>{item.get('phone') or '—'}</code>\n"
            f"💰 Цена: <b>{item['price']} {item['currency']}</b>\n"
            f"📝 {description}\n\n"
            f"👇 Нажми <b>Оплатить</b> и переведи средства.\n"
            f"Затем нажми <b>Проверить оплату</b>:",
            reply_markup=kb_buy(shop_id, invoice["pay_url"]),
            parse_mode="HTML",
        )
    except Exception as e:
        await call.message.edit_text(
            f"❌ Ошибка создания счёта:\n<code>{e}</code>",
            reply_markup=kb_back("shop"),
            parse_mode="HTML",
        )


# ── ПРОВЕРКА ОПЛАТЫ ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("checkpay_"))
async def cb_check_payment(call: CallbackQuery):
    shop_id = int(call.data.split("_")[1])

    item = await get_shop_item(shop_id)
    if not item:
        await call.answer("Товар не найден", show_alert=True)
        return

    # Найти последний pending-платёж этого пользователя за этот аккаунт
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM payments
               WHERE user_id = ? AND account_id = ? AND status = 'pending'
               ORDER BY created_at DESC LIMIT 1""",
            (call.from_user.id, item["account_id"]),
        ) as cur:
            row = await cur.fetchone()
            payment = dict(row) if row else None

    if not payment:
        await call.answer("Платёж не найден. Нажми «Купить» снова.", show_alert=True)
        return

    await call.answer("⏳ Проверяю оплату...")

    status = await check_invoice(payment["invoice_id"])

    if status == "paid":
        await update_payment_status(payment["invoice_id"], "paid")
        await mark_sold(shop_id, item["account_id"])

        import os
        session_path = os.path.join(SESSIONS_DIR, item["session_file"])

        try:
            doc = FSInputFile(session_path, filename=item["session_file"])
            await call.message.answer_document(
                document=doc,
                caption=(
                    f"✅ <b>Оплата подтверждена!</b>\n\n"
                    f"📱 Аккаунт: <code>{item.get('phone') or '—'}</code>\n"
                    f"💰 Оплачено: <b>{payment['amount']} {payment['currency']}</b>\n\n"
                    f"Твой .session файл:"
                ),
                parse_mode="HTML",
            )
            await call.message.edit_text(
                "✅ Покупка завершена! .session файл отправлен выше.",
                reply_markup=kb_back("shop"),
            )
        except Exception as e:
            await call.message.edit_text(
                f"✅ Оплата получена!\n\n"
                f"⚠️ Не удалось отправить файл автоматически: <code>{e}</code>\n"
                f"Обратись к администратору — сообщи ID аккаунта: <code>{item['account_id']}</code>",
                reply_markup=kb_back("shop"),
                parse_mode="HTML",
            )

    elif status in ("active", "pending"):
        await call.answer("⏳ Оплата ещё не получена. Оплати и повтори проверку.", show_alert=True)

    elif status == "expired":
        await update_payment_status(payment["invoice_id"], "failed")
        await call.message.edit_text(
            "❌ Счёт истёк. Нажми «Купить» снова чтобы создать новый.",
            reply_markup=kb_back("shop"),
        )
    else:
        await call.answer(f"Статус: {status}", show_alert=True)
