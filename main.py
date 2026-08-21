import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database.db import init_db

# ── Роутеры ───────────────────────────────────────────────────────────────────
from handlers.common          import router as common_router
from handlers.accounts        import router as accounts_router
from handlers.account_extras  import router as extras_router
from handlers.shop            import router as shop_router
from handlers.admin           import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    # Инициализация БД
    await init_db()
    logger.info("Database initialised.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # Порядок важен: common первым (start/main), затем остальные
    dp.include_router(common_router)
    dp.include_router(accounts_router)
    dp.include_router(extras_router)   # setpass / getcode / recreate
    dp.include_router(shop_router)
    dp.include_router(admin_router)

    logger.info("Bot is starting...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
