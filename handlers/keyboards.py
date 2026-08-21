from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from config import MINIAPP_URL


def kb_main_user() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Магазин аккаунтов", callback_data="shop")],
        [InlineKeyboardButton(text="💎 Открыть Mini App",  web_app=WebAppInfo(url=MINIAPP_URL))],
        [InlineKeyboardButton(text="👤 Мой профиль",       callback_data="profile")],
    ])


def kb_main_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 Мои аккаунты",   callback_data="my_accounts"),
            InlineKeyboardButton(text="➕ Добавить",        callback_data="add_account"),
        ],
        [
            InlineKeyboardButton(text="🛒 Магазин",        callback_data="shop"),
            InlineKeyboardButton(text="📊 Статистика",     callback_data="stats"),
        ],
        [InlineKeyboardButton(text="💎 Mini App",          web_app=WebAppInfo(url=MINIAPP_URL))],
        [InlineKeyboardButton(text="⚙️ Управление",        callback_data="admin_panel")],
    ])


def kb_main_superadmin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 Аккаунты",       callback_data="my_accounts"),
            InlineKeyboardButton(text="➕ Добавить",        callback_data="add_account"),
        ],
        [
            InlineKeyboardButton(text="🛒 Магазин",        callback_data="shop"),
            InlineKeyboardButton(text="📊 Статистика",     callback_data="stats"),
        ],
        [
            InlineKeyboardButton(text="👥 Пользователи",   callback_data="users_list"),
            InlineKeyboardButton(text="🛡 Админы",         callback_data="admins_list"),
        ],
        [InlineKeyboardButton(text="💎 Mini App",          web_app=WebAppInfo(url=MINIAPP_URL))],
    ])


def kb_add_account() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Номер + Код + 2FA", callback_data="auth_phone")],
        [InlineKeyboardButton(text="📂 Загрузить .session", callback_data="auth_session")],
        [InlineKeyboardButton(text="📦 Массовая загрузка",  callback_data="auth_bulk")],
        [InlineKeyboardButton(text="◀️ Назад",              callback_data="main")],
    ])


def kb_account_list(accounts: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for acc in accounts:
        phone = acc.get("phone") or "Без номера"
        status_icon = {"active": "🟢", "shop": "🛒", "sold": "🔴", "banned": "⛔"}.get(acc["status"], "⚪")
        rows.append([InlineKeyboardButton(
            text=f"{status_icon} {phone}",
            callback_data=f"acc_{acc['id']}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_account_menu(account_id: int) -> InlineKeyboardMarkup:
    aid = account_id
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Сессии",         callback_data=f"sessions_{aid}"),
            InlineKeyboardButton(text="⚡ Кик всех",       callback_data=f"kickall_{aid}"),
        ],
        [
            InlineKeyboardButton(text="🔐 Пароль 2FA",     callback_data=f"setpass_{aid}"),
            InlineKeyboardButton(text="📦 Получить аккаунт",   callback_data=f"getcode_{aid}"),
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка",       callback_data=f"broadcast_{aid}"),
            InlineKeyboardButton(text="❤️ Реакции",        callback_data=f"reactions_{aid}"),
        ],
        [
            InlineKeyboardButton(text="🗑 Очистить чаты",  callback_data=f"clearchats_{aid}"),
            InlineKeyboardButton(text="👥 Контакты",       callback_data=f"clearcontacts_{aid}"),
        ],
        [
            InlineKeyboardButton(text="🔄 Пересоздать",    callback_data=f"recreate_{aid}"),
            InlineKeyboardButton(text="🛒 В магазин",      callback_data=f"toshop_{aid}"),
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить аккаунт",callback_data=f"delacc_{aid}"),
        ],
        [InlineKeyboardButton(text="◀️ Назад",             callback_data="my_accounts")],
    ])


def kb_sessions(sessions: list[dict], account_id: int) -> InlineKeyboardMarkup:
    rows = []
    for s in sessions:
        icon = "🟢" if s["current"] else "📱"
        label = f"{icon} {s['device']} · {s['country']}"
        if not s["current"]:
            rows.append([InlineKeyboardButton(
                text=label,
                callback_data=f"kick_{account_id}_{s['hash']}",
            )])
        else:
            rows.append([InlineKeyboardButton(text=label + " (текущая)", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"acc_{account_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_confirm(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, подтвердить", callback_data=yes_cb),
            InlineKeyboardButton(text="❌ Отмена",          callback_data=no_cb),
        ]
    ])


def kb_shop(items: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        phone = item.get("phone") or "Аккаунт"
        rows.append([InlineKeyboardButton(
            text=f"📱 {phone} — {item['price']} {item['currency']}",
            callback_data=f"buy_{item['id']}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_buy(shop_id: int, pay_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"checkpay_{shop_id}")],
        [InlineKeyboardButton(text="◀️ Назад",            callback_data="shop")],
    ])


def kb_back(cb: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=cb)]
    ])


def kb_reactions(account_id: int) -> InlineKeyboardMarkup:
    emojis = ["👍", "👎", "❤️", "🔥", "🎉", "😮", "😢", "💯", "⚡", "🏆"]
    rows = []
    row = []
    for i, e in enumerate(emojis):
        row.append(InlineKeyboardButton(
            text=e, callback_data=f"react_pick_{account_id}_{e}"
        ))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"acc_{account_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
