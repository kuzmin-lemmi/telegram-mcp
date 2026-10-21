"""Хранение входа в аккаунт Telegram: api_id, api_hash и строка сессии Telethon.

Всё лежит одной записью в хранилище ОС (Диспетчер учётных данных Windows,
Keychain в macOS, Secret Service в Linux). Туда запись попадает только через
``telegram-mcp-login``; файла сессии на диске нет, ИИ эти данные не видит.
"""

import json

SERVICE = "telegram-mcp"
ACCOUNT = "account"


def get_account():
    """``{"api_id": int, "api_hash": str, "session": str}`` или ``None``, если входа не было."""
    try:
        import keyring

        raw = keyring.get_password(SERVICE, ACCOUNT)
    except Exception:  # noqa: BLE001 — нет хранилища: сервер сообщит «вход не выполнен»
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return {"api_id": int(data["api_id"]), "api_hash": str(data["api_hash"]), "session": str(data["session"])}
    except (ValueError, KeyError, TypeError):
        return None


def store_account(api_id, api_hash, session):
    import keyring

    keyring.set_password(SERVICE, ACCOUNT, json.dumps({"api_id": int(api_id), "api_hash": api_hash, "session": session}))


def delete_account():
    import keyring

    try:
        keyring.delete_password(SERVICE, ACCOUNT)
        return True
    except keyring.errors.PasswordDeleteError:
        return False
