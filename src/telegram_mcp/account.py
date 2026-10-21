"""Клиент Telegram от имени аккаунта автора (Telethon, MTProto).

Telethon асинхронный, а инструменты сервера синхронные, поэтому клиент
живёт в своём потоке со своим циклом событий. Наружу отдаются простые
словари, любая ошибка становится TelegramError без api_hash и сессии.
"""

import asyncio
import concurrent.futures
import threading

from . import __version__, account_store
from .client import TelegramError

TIMEOUT = 60
DEVICE = "telegram-mcp"

LOGIN_HINT = "Выполните в терминале: telegram-mcp-login"


def new_client(api_id, api_hash, session=""):
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    return TelegramClient(StringSession(session), int(api_id), api_hash, device_model=DEVICE, app_version=__version__)


def peer(channel):
    """``@name`` остаётся строкой, числовой ID (``-100…``) становится числом."""
    return int(channel) if channel.lstrip("-").isdigit() else channel


def translate(exc, secrets=()):
    """Ошибка Telethon или сети → понятная TelegramError."""
    from telethon import errors

    if isinstance(exc, TelegramError):
        return exc
    if isinstance(exc, errors.FloodWaitError):
        return TelegramError(f"Telegram просит подождать {exc.seconds} с, прежде чем повторить.", "FLOOD_WAIT")
    if isinstance(exc, (errors.AuthKeyError, errors.UnauthorizedError)):
        return TelegramError(f"Сеанс недействителен (возможно, завершён в «Устройствах»). {LOGIN_HINT}", "NOT_LOGGED_IN")
    if isinstance(exc, errors.RPCError):
        message = f"{type(exc).__name__}: {exc.message}"
        code = "API_ERROR"
    elif isinstance(exc, ValueError):
        # get_entity сообщает так о несуществующем имени канала
        message, code = str(exc), "NOT_FOUND"
    elif isinstance(exc, (ConnectionError, OSError, asyncio.TimeoutError, concurrent.futures.TimeoutError)):
        message, code = f"Не достучаться до Telegram: {type(exc).__name__} {exc}".strip(), "NETWORK_ERROR"
    else:
        message, code = f"{type(exc).__name__}: {exc}", "INTERNAL_ERROR"
    for secret in secrets:
        if secret:
            message = message.replace(secret, "<SECRET>")
    return TelegramError(message, code)


class AccountClient:
    def __init__(self, load=account_store.get_account, factory=new_client):
        self._load = load
        self._factory = factory
        self._client = None
        self._authorized = False
        self._secrets = ()
        self._loop = None
        self._loop_lock = threading.Lock()

    def _ensure_loop(self):
        with self._loop_lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, name="telethon", daemon=True).start()
                self._loop = loop
        return self._loop

    def _run(self, make_coro):
        future = asyncio.run_coroutine_threadsafe(make_coro(), self._ensure_loop())
        try:
            return future.result(TIMEOUT)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise translate(exc) from None
        except Exception as exc:  # noqa: BLE001
            raise translate(exc, self._secrets) from None

    async def _connected(self):
        if self._client is None:
            account = self._load()
            if not account:
                raise TelegramError(f"Вход в аккаунт не выполнен. {LOGIN_HINT}", "NOT_LOGGED_IN")
            self._secrets = (account["api_hash"], account["session"])
            self._client = self._factory(account["api_id"], account["api_hash"], account["session"])
            self._authorized = False
        if not self._client.is_connected():
            await self._client.connect()
        if not self._authorized:
            if not await self._client.is_user_authorized():
                self._client = None  # при следующем вызове вход перечитается из хранилища
                raise TelegramError(
                    f"Сеанс недействителен (возможно, завершён в «Устройствах»). {LOGIN_HINT}", "NOT_LOGGED_IN"
                )
            self._authorized = True
        return self._client

    # -- методы, нужные серверу --------------------------------------------

    def get_me(self):
        async def run():
            me = await (await self._connected()).get_me()
            return {"id": me.id, "username": me.username, "first_name": me.first_name}

        return self._run(run)

    def get_channel(self, channel):
        async def run():
            from telethon.tl.types import Channel

            entity = await (await self._connected()).get_entity(peer(channel))
            if isinstance(entity, Channel):
                kind = "channel" if entity.broadcast else "supergroup"
            else:
                kind = type(entity).__name__.lower()
            return {"id": entity.id, "title": getattr(entity, "title", None), "type": kind,
                    "username": getattr(entity, "username", None)}

        return self._run(run)

    def get_my_rights(self, channel):
        """Статус аккаунта в канале и права, нужные серверу."""
        async def run():
            from telethon import errors

            client = await self._connected()
            try:
                perms = await client.get_permissions(peer(channel), "me")
            except errors.UserNotParticipantError:
                return {"status": "left"}
            if perms.is_creator:
                return {"status": "creator", "can_post_messages": True, "can_edit_messages": True,
                        "can_pin_messages": True}
            if perms.is_admin:
                return {"status": "administrator", "can_post_messages": bool(perms.post_messages),
                        "can_edit_messages": bool(perms.edit_messages), "can_pin_messages": bool(perms.pin_messages)}
            return {"status": "left" if perms.has_left else "member"}

        return self._run(run)
