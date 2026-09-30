"""MCP-сервер Telegram: подготовка и публикация постов в канал.

Транспорт stdio (OpenCode, Claude Desktop, Claude Code). Токен бота
читается из окружения процесса и ИИ не передаётся.
"""

import json
import os

from mcp.server.mcpserver import MCPServer

from .checks import assess_member, parse_allowed_channels
from .client import TelegramClient, TelegramError

CLIENT = TelegramClient(os.environ.get("TELEGRAM_BOT_TOKEN", ""))

mcp = MCPServer(
    name="telegram",
    instructions=(
        "Сервер работает с Telegram-каналами автора. Публиковать можно только в каналы из списка "
        "TELEGRAM_ALLOWED_CHANNELS. Ничего не публикуй без явного подтверждения пользователя в чате. "
        "Сначала проверь связь инструментом telegram_check."
    ),
)


def _error(exc):
    return json.dumps({"status": "error", "code": exc.code, "message": str(exc)}, ensure_ascii=False, indent=2)


def allowed_channels():
    return parse_allowed_channels(os.environ.get("TELEGRAM_ALLOWED_CHANNELS", ""))


def check(client=None):
    """Проверка бота и прав в каждом разрешённом канале."""
    client = client or CLIENT
    channels = allowed_channels()
    if not channels:
        raise TelegramError(
            "Не задан список каналов TELEGRAM_ALLOWED_CHANNELS (например, @bot_dev_py_ai).", "NO_CHANNELS"
        )
    me = client.get_me()
    reports = []
    for channel in channels:
        try:
            chat = client.get_chat(channel)
            member = client.get_chat_member(channel, me["id"])
            reports.append(assess_member(channel, chat, member))
        except TelegramError as exc:
            reports.append({
                "channel": channel,
                "ok": False,
                "warnings": [f"Канал недоступен: {exc}"],
            })
    return {
        "status": "ok" if all(report["ok"] for report in reports) else "attention",
        "bot": {"username": me.get("username"), "name": me.get("first_name"), "id": me.get("id")},
        "channels": reports,
    }


@mcp.tool(
    description=(
        "Проверить связь с Telegram: какой это бот, есть ли он в разрешённых каналах и с какими правами. "
        "Предупреждает о недостающих и лишних правах. Ничего не отправляет и не меняет."
    )
)
def telegram_check() -> str:
    try:
        return json.dumps(check(), ensure_ascii=False, indent=2)
    except TelegramError as exc:
        return _error(exc)
    except Exception as exc:  # noqa: BLE001 — вместо стектрейса отдаём понятную причину
        return _error(TelegramError(f"{type(exc).__name__}: {exc}", "INTERNAL_ERROR"))


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
