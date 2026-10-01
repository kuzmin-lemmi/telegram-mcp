"""Минимальный клиент Telegram Bot API.

Токен бота входит в адрес запроса, поэтому любой текст ошибки
очищается от него, прежде чем попасть наружу.
"""

import json
import os
import urllib.error
import urllib.request

API_URL = os.environ.get("TELEGRAM_API_URL", "https://api.telegram.org").rstrip("/")
TIMEOUT = int(os.environ.get("TELEGRAM_TIMEOUT", "30"))


class TelegramError(Exception):
    def __init__(self, message, code="TELEGRAM_ERROR"):
        super().__init__(message)
        self.code = code


class TelegramClient:
    def __init__(self, token, api_url=API_URL):
        self._token = token
        self._api_url = api_url

    def _redact(self, text):
        text = str(text)
        return text.replace(self._token, "<TOKEN>") if self._token else text

    def _post(self, method, payload):
        """Один запрос к Bot API. Возвращает распарсенный JSON целиком."""
        request = urllib.request.Request(
            f"{self._api_url}/bot{self._token}/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Telegram объясняет причину в теле ответа (например, «chat not found»).
            try:
                return json.loads(exc.read().decode("utf-8"))
            except (ValueError, OSError):
                raise TelegramError(f"Telegram вернул HTTP {exc.code}", "HTTP_ERROR") from None
        except urllib.error.URLError as exc:
            raise TelegramError(f"Не достучаться до Telegram: {self._redact(exc.reason)}", "NETWORK_ERROR") from None

    def call(self, method, **params):
        if not self._token:
            raise TelegramError("Не задан TELEGRAM_BOT_TOKEN", "NO_TOKEN")
        payload = {key: value for key, value in params.items() if value is not None}
        data = self._post(method, payload)
        if not data.get("ok"):
            description = self._redact(data.get("description", "неизвестная ошибка"))
            raise TelegramError(f"{method}: {description}", "API_ERROR")
        return data["result"]

    # -- методы, нужные серверу --------------------------------------------

    def get_me(self):
        return self.call("getMe")

    def get_chat(self, chat_id):
        return self.call("getChat", chat_id=chat_id)

    def get_chat_member(self, chat_id, user_id):
        return self.call("getChatMember", chat_id=chat_id, user_id=user_id)

    def get_updates(self):
        """Непрочитанные сообщения боту. Не подтверждает их (offset не передаётся)."""
        return self.call("getUpdates", limit=100, timeout=0, allowed_updates=["message"])

    def send_message(self, chat_id, text, parse_mode="HTML"):
        return self.call("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)
