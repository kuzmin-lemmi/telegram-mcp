"""Хранение токена бота.

Порядок поиска: переменная TELEGRAM_BOT_TOKEN, затем хранилище ОС
(Диспетчер учётных данных Windows, Keychain в macOS, Secret Service в Linux).
В хранилище токен попадает через ``telegram-mcp-setup`` и ИИ не виден.
"""

import os

SERVICE = "telegram-mcp"
ACCOUNT = "bot-token"


def get_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token
    try:
        import keyring

        return (keyring.get_password(SERVICE, ACCOUNT) or "").strip()
    except Exception:  # noqa: BLE001 — нет хранилища: сервер сообщит «токен не задан»
        return ""


def store_token(token):
    import keyring

    keyring.set_password(SERVICE, ACCOUNT, token)


def delete_token():
    import keyring

    try:
        keyring.delete_password(SERVICE, ACCOUNT)
        return True
    except keyring.errors.PasswordDeleteError:
        return False
