import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_ID         = int(os.getenv("ADMIN_ID", "0"))
API_ID           = int(os.getenv("API_ID", "0"))
API_HASH         = os.getenv("API_HASH")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")
MINIAPP_URL      = os.getenv("MINIAPP_URL", "")

DB_PATH          = "bot.db"
SESSIONS_DIR     = "sessions"

os.makedirs(SESSIONS_DIR, exist_ok=True)
