"""MCP-сервер Telegram: подготовка и публикация постов в канал.

Транспорт stdio (OpenCode, Claude Desktop, Claude Code). Токен бота
читается из окружения процесса и ИИ не передаётся.
"""

import functools
import json
import os

from mcp.server.mcpserver import MCPServer

from . import workspace
from .checks import assess_member, normalize_channel, parse_allowed_channels
from .client import TelegramClient, TelegramError
from .validate import check_post

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


def resolve_channel(channel=None):
    """Канал из списка разрешённых. Если канал один, его можно не указывать."""
    allowed = allowed_channels()
    if not allowed:
        raise TelegramError("Не задан список каналов TELEGRAM_ALLOWED_CHANNELS.", "NO_CHANNELS")
    if not channel:
        if len(allowed) == 1:
            return allowed[0]
        raise TelegramError("Укажите канал: " + ", ".join(allowed), "CHANNEL_REQUIRED")
    try:
        normalized = normalize_channel(channel)
    except ValueError as exc:
        raise TelegramError(str(exc), "BAD_CHANNEL") from None
    if normalized not in allowed:
        raise TelegramError(f"Канал {normalized} не входит в список разрешённых.", "CHANNEL_NOT_ALLOWED")
    return normalized


def tool_result(func):
    """Результат инструмента — JSON; любая ошибка становится понятным ответом, а не стектрейсом."""
    @functools.wraps(func)
    def run(*args, **kwargs):
        try:
            return json.dumps(func(*args, **kwargs), ensure_ascii=False, indent=2)
        except TelegramError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error(TelegramError(f"{type(exc).__name__}: {exc}", "INTERNAL_ERROR"))
    return run


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
@tool_result
def telegram_check() -> dict:
    return check()


@mcp.tool(
    description=(
        "Создать папку канала (drafts/, published/, AGENTS.md, STYLE.md, content-plan.md). "
        "Существующие файлы не меняются. Вызывается один раз для канала."
    )
)
@tool_result
def telegram_init_channel(channel: str | None = None) -> dict:
    return workspace.init_channel(resolve_channel(channel))


@mcp.tool(
    description=(
        "Сохранить черновик поста в формате Telegram-HTML (<b>, <i>, <code>, <pre>, <a href>; не Markdown). "
        "name: латиница, цифры, «-», «_». Существующий черновик заменяется только при overwrite=true. "
        "В канал ничего не отправляется."
    )
)
@tool_result
def telegram_save_draft(name: str, text: str, channel: str | None = None, overwrite: bool = False) -> dict:
    channel = resolve_channel(channel)
    path = workspace.save_draft(channel, name, text, overwrite)
    return {"status": "saved", "path": path, **{k: v for k, v in check_post(text).items() if k != "ok"}}


@mcp.tool(description="Прочитать черновик поста. Ничего не меняет.")
@tool_result
def telegram_read_draft(name: str, channel: str | None = None) -> dict:
    channel = resolve_channel(channel)
    return {"name": name, "text": workspace.read_draft(channel, name)}


@mcp.tool(description="Список черновиков канала. Ничего не меняет.")
@tool_result
def telegram_list_drafts(channel: str | None = None) -> dict:
    channel = resolve_channel(channel)
    return {"channel": channel, "drafts": workspace.list_drafts(channel)}


@mcp.tool(
    description=(
        "Проверить черновик: теги Telegram-HTML, ссылки, длина (до 4096 символов, для подписи к картинке 1024), "
        "следы Markdown. Возвращает ошибки, предупреждения и хэш текста. Ничего не отправляет."
    )
)
@tool_result
def telegram_check_draft(name: str, channel: str | None = None, has_image: bool = False) -> dict:
    channel = resolve_channel(channel)
    return {"name": name, **check_post(workspace.read_draft(channel, name), has_image)}


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
