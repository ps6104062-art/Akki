import asyncio
import logging
import os
from aiohttp import web

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


async def run_miniapp() -> None:
    """Простой HTTP-сервер для Mini App."""
    miniapp_dir = os.path.join(os.path.dirname(__file__), "miniapp")

    async def index(request):
        return web.FileResponse(os.path.join(miniapp_dir, "index.html"))

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/{path:.*}", index)
    app.router.add_static("/", miniapp_dir, show_index=True)

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Mini App запущен на порту {port}")


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
    await run_miniapp()
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
