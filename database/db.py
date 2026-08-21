import aiosqlite
from config import DB_PATH

# ─── INIT ──────────────────────────────────────────────────────────────────────

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id  INTEGER UNIQUE NOT NULL,
            username     TEXT,
            full_name    TEXT,
            role         TEXT DEFAULT 'user',  -- 'superadmin' | 'admin' | 'user'
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id     INTEGER NOT NULL,
            phone        TEXT,
            session_file TEXT,
            status       TEXT DEFAULT 'active', -- 'active' | 'shop' | 'sold' | 'banned'
            added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(telegram_id)
        );

        CREATE TABLE IF NOT EXISTS shop (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id   INTEGER NOT NULL UNIQUE,
            price        REAL NOT NULL,
            currency     TEXT DEFAULT 'USDT',
            description  TEXT,
            status       TEXT DEFAULT 'available', -- 'available' | 'reserved' | 'sold'
            added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            account_id   INTEGER NOT NULL,
            amount       REAL NOT NULL,
            currency     TEXT DEFAULT 'USDT',
            invoice_id   TEXT,
            status       TEXT DEFAULT 'pending', -- 'pending' | 'paid' | 'failed'
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)    REFERENCES users(telegram_id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );
        """)
        await db.commit()


# ─── USERS ─────────────────────────────────────────────────────────────────────

async def get_user(telegram_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_user(telegram_id: int, username: str, full_name: str, role: str = "user"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO users (telegram_id, username, full_name, role)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, username, full_name, role),
        )
        await db.commit()


async def set_user_role(telegram_id: int, role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id)
        )
        await db.commit()


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ─── ACCOUNTS ──────────────────────────────────────────────────────────────────

async def add_account(owner_id: int, phone: str, session_file: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO accounts (owner_id, phone, session_file) VALUES (?, ?, ?)",
            (owner_id, phone, session_file),
        )
        await db.commit()
        return cur.lastrowid


async def get_account(account_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_accounts(owner_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM accounts WHERE owner_id = ? AND status != 'sold' ORDER BY added_at DESC",
            (owner_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_all_accounts() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT a.*, u.username FROM accounts a JOIN users u ON a.owner_id = u.telegram_id ORDER BY a.added_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def update_account_status(account_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE accounts SET status = ? WHERE id = ?", (status, account_id)
        )
        await db.commit()


async def delete_account(account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await db.commit()


# ─── SHOP ──────────────────────────────────────────────────────────────────────

async def add_to_shop(account_id: int, price: float, currency: str, description: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO shop (account_id, price, currency, description) VALUES (?, ?, ?, ?)",
            (account_id, price, currency, description),
        )
        await db.execute(
            "UPDATE accounts SET status = 'shop' WHERE id = ?", (account_id,)
        )
        await db.commit()


async def get_shop_items() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.*, a.phone FROM shop s
               JOIN accounts a ON s.account_id = a.id
               WHERE s.status = 'available'
               ORDER BY s.added_at DESC"""
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_shop_item(shop_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT s.*, a.phone, a.session_file FROM shop s JOIN accounts a ON s.account_id = a.id WHERE s.id = ?",
            (shop_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def mark_sold(shop_id: int, account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE shop SET status = 'sold' WHERE id = ?", (shop_id,))
        await db.execute(
            "UPDATE accounts SET status = 'sold' WHERE id = ?", (account_id,)
        )
        await db.commit()


# ─── PAYMENTS ──────────────────────────────────────────────────────────────────

async def create_payment(user_id: int, account_id: int, amount: float, currency: str, invoice_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO payments (user_id, account_id, amount, currency, invoice_id) VALUES (?, ?, ?, ?, ?)",
            (user_id, account_id, amount, currency, invoice_id),
        )
        await db.commit()
        return cur.lastrowid


async def get_payment_by_invoice(invoice_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payments WHERE invoice_id = ?", (invoice_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_payment_status(invoice_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status = ? WHERE invoice_id = ?", (status, invoice_id)
        )
        await db.commit()
