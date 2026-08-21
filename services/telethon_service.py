import os
import asyncio
from telethon import TelegramClient
from telethon.tl.functions.account import (
    GetAuthorizationsRequest,
    ResetAuthorizationRequest,
    ResetAuthorizationsRequest,
)
from telethon.tl.functions.contacts import DeleteContactsRequest, GetContactsRequest
from telethon.tl.functions.messages import DeleteHistoryRequest
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from config import API_ID, API_HASH, SESSIONS_DIR

# Хранилище активных клиентов { session_file: TelegramClient }
_clients: dict[str, TelegramClient] = {}


def _session_path(session_file: str) -> str:
    return os.path.join(SESSIONS_DIR, session_file.replace(".session", ""))


async def get_client(session_file: str) -> TelegramClient:
    """Получить или создать клиент для сессии."""
    if session_file not in _clients:
        client = TelegramClient(_session_path(session_file), API_ID, API_HASH)
        await client.connect()
        _clients[session_file] = client
    return _clients[session_file]


async def disconnect_client(session_file: str):
    if session_file in _clients:
        await _clients[session_file].disconnect()
        del _clients[session_file]


# ─── АВТОРИЗАЦИЯ ───────────────────────────────────────────────────────────────

# Временное хранилище для процесса входа { telegram_user_id: {...} }
_auth_sessions: dict[int, dict] = {}


async def start_auth(user_id: int, phone: str) -> str:
    """Начать авторизацию — отправить код на номер."""
    session_name = f"acc_{phone.replace('+', '').replace(' ', '')}"
    client = TelegramClient(_session_path(session_name), API_ID, API_HASH)
    await client.connect()

    result = await client.send_code_request(phone)
    _auth_sessions[user_id] = {
        "client": client,
        "phone": phone,
        "phone_code_hash": result.phone_code_hash,
        "session_name": session_name,
    }
    return session_name


async def submit_code(user_id: int, code: str) -> str:
    """Подтвердить код. Вернуть 'ok' или '2fa'."""
    data = _auth_sessions.get(user_id)
    if not data:
        raise ValueError("Сессия авторизации не найдена. Начните заново.")

    client: TelegramClient = data["client"]
    try:
        await client.sign_in(
            phone=data["phone"],
            code=code,
            phone_code_hash=data["phone_code_hash"],
        )
        # Успешно — сохраняем клиент
        session_file = data["session_name"] + ".session"
        _clients[session_file] = client
        return "ok"
    except SessionPasswordNeededError:
        return "2fa"
    except PhoneCodeInvalidError:
        raise ValueError("Неверный код. Попробуйте ещё раз.")


async def submit_password(user_id: int, password: str) -> str:
    """Ввести пароль 2FA."""
    data = _auth_sessions.get(user_id)
    if not data:
        raise ValueError("Сессия авторизации не найдена.")

    client: TelegramClient = data["client"]
    await client.sign_in(password=password)
    session_file = data["session_name"] + ".session"
    _clients[session_file] = client
    del _auth_sessions[user_id]
    return data["session_name"] + ".session"


async def load_session_file(session_path: str) -> bool:
    """Загрузить готовый .session файл и проверить что он рабочий."""
    try:
        client = TelegramClient(session_path.replace(".session", ""), API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return False
        fname = os.path.basename(session_path)
        _clients[fname] = client
        return True
    except Exception:
        return False


# ─── СЕССИИ ────────────────────────────────────────────────────────────────────

async def get_sessions(session_file: str) -> list[dict]:
    client = await get_client(session_file)
    auths = await client(GetAuthorizationsRequest())
    result = []
    for a in auths.authorizations:
        result.append({
            "hash":        a.hash,
            "device":      a.device_model,
            "platform":    a.platform,
            "app":         a.app_name,
            "ip":          a.ip,
            "country":     a.country,
            "active":      a.date_active.strftime("%d.%m.%Y %H:%M"),
            "current":     a.current,
        })
    return result


async def kick_session(session_file: str, session_hash: int):
    client = await get_client(session_file)
    await client(ResetAuthorizationRequest(hash=session_hash))


async def kick_all_sessions(session_file: str):
    client = await get_client(session_file)
    await client(ResetAuthorizationsRequest())


# ─── ОЧИСТКА ───────────────────────────────────────────────────────────────────

async def clear_all_chats(session_file: str) -> int:
    client = await get_client(session_file)
    dialogs = await client.get_dialogs(limit=None)
    count = 0
    for d in dialogs:
        try:
            await client(DeleteHistoryRequest(
                peer=d.input_entity, max_id=0, revoke=True
            ))
            count += 1
            await asyncio.sleep(0.4)
        except Exception:
            pass
    return count


async def clear_contacts(session_file: str) -> int:
    client = await get_client(session_file)
    contacts = await client(GetContactsRequest(hash=0))
    ids = [u.id for u in contacts.users]
    if ids:
        await client(DeleteContactsRequest(id=ids))
    return len(ids)


# ─── РАССЫЛКА ──────────────────────────────────────────────────────────────────

async def broadcast(
    session_file: str,
    targets: list[str],
    message: str,
    delay: float = 1.5,
    progress_cb=None,
) -> dict:
    client = await get_client(session_file)
    sent = 0
    failed = 0
    for i, target in enumerate(targets):
        try:
            await client.send_message(target, message)
            sent += 1
        except Exception as e:
            failed += 1
        if progress_cb:
            await progress_cb(i + 1, len(targets), sent, failed)
        await asyncio.sleep(delay)
    return {"sent": sent, "failed": failed}


# ─── РЕАКЦИИ ───────────────────────────────────────────────────────────────────

async def send_reactions(
    session_file: str,
    target: str,
    emoji: str,
    count: int,
    delay: float,
    progress_cb=None,
) -> dict:
    client = await get_client(session_file)
    entity = await client.get_entity(target)
    messages = await client.get_messages(entity, limit=count)
    sent = 0
    for i, msg in enumerate(messages):
        try:
            await client(SendReactionRequest(
                peer=entity,
                msg_id=msg.id,
                reaction=[ReactionEmoji(emoticon=emoji)],
            ))
            sent += 1
        except Exception:
            pass
        if progress_cb:
            await progress_cb(i + 1, len(messages), sent)
        await asyncio.sleep(delay)
    return {"sent": sent, "total": len(messages)}


# ─── ИНФО ──────────────────────────────────────────────────────────────────────

async def get_me(session_file: str) -> dict:
    client = await get_client(session_file)
    me = await client.get_me()
    return {
        "id":         me.id,
        "first_name": me.first_name or "",
        "last_name":  me.last_name or "",
        "username":   me.username or "",
        "phone":      me.phone or "",
    }
