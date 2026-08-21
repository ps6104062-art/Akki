import aiohttp
from config import CRYPTO_BOT_TOKEN

BASE_URL = "https://pay.crypt.bot/api"

HEADERS = {
    "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
    "Content-Type": "application/json",
}


async def create_invoice(amount: float, currency: str, description: str, payload: str) -> dict:
    """Создать инвойс для оплаты."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/createInvoice",
            headers=HEADERS,
            json={
                "asset":       currency,
                "amount":      str(amount),
                "description": description,
                "payload":     payload,
                "paid_btn_name": "callback",
                "paid_btn_url":  "https://t.me/your_bot",
            },
        ) as resp:
            data = await resp.json()
            if data.get("ok"):
                inv = data["result"]
                return {
                    "invoice_id": str(inv["invoice_id"]),
                    "pay_url":    inv["pay_url"],
                    "amount":     amount,
                    "currency":   currency,
                }
            raise Exception(f"CryptoBot error: {data}")


async def check_invoice(invoice_id: str) -> str:
    """Проверить статус инвойса. Вернуть 'paid' | 'active' | 'expired'."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/getInvoices",
            headers=HEADERS,
            params={"invoice_ids": invoice_id},
        ) as resp:
            data = await resp.json()
            if data.get("ok"):
                items = data["result"].get("items", [])
                if items:
                    return items[0]["status"]
            return "unknown"
