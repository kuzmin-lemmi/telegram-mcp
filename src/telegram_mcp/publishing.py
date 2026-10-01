"""Публикация и правка постов в канале.

Условия, без которых в канал ничего не уходит:
1. канал из списка разрешённых;
2. черновик проходит проверку;
3. автор уже видел этот текст (telegram_preview) и с тех пор он не менялся;
4. вызывающий передал хэш именно этого текста (confirm_sha256);
5. бот в канале администратор с правом публикации;
6. для этого черновика ещё нет записи о публикации.

Удаления сообщений нет ни в каком виде.
"""

from datetime import datetime, timezone

from . import workspace
from .checks import assess_member
from .client import TelegramError
from .validate import check_post, normalize_text


def _gate(client, channel, name, confirm_sha256):
    """Общие проверки перед отправкой. Возвращает (текст для отправки, хэш)."""
    text = workspace.read_draft(channel, name)
    result = check_post(text)
    if not result["ok"]:
        raise TelegramError("Черновик не прошёл проверку: " + " ".join(result["errors"]), "DRAFT_INVALID")
    sha = result["sha256"]
    seen = workspace.get_preview(channel, name)
    if not seen:
        raise TelegramError("Автор ещё не видел этот пост. Сначала вызовите telegram_preview.", "NOT_PREVIEWED")
    if seen["sha256"] != sha:
        raise TelegramError(
            "Текст изменился после показа автору. Покажите новую версию через telegram_preview.", "CHANGED_AFTER_PREVIEW"
        )
    if (confirm_sha256 or "").strip().lower() != sha:
        raise TelegramError(
            "confirm_sha256 не совпадает с хэшем текста. Передайте sha256 из ответа telegram_preview.", "BAD_CONFIRMATION"
        )
    me = client.get_me()
    report = assess_member(channel, client.get_chat(channel), client.get_chat_member(channel, me["id"]))
    if not report["can_post"] or report["bot_status"] not in ("administrator", "creator"):
        raise TelegramError("; ".join(report["warnings"]) or "Нет права публикации.", "NO_POST_RIGHT")
    return normalize_text(text), sha


def _link(channel, message_id):
    return f"https://t.me/{channel.lstrip('@')}/{message_id}" if channel.startswith("@") else None


def publish(client, channel, name, confirm_sha256):
    text, sha = _gate(client, channel, name, confirm_sha256)
    now = datetime.now(timezone.utc).isoformat()
    # Запись занимается до отправки: повторный вызов не создаст дубль, а сбой не потеряет следов.
    workspace.reserve_published(channel, name, {"status": "sending", "channel": channel, "sha256": sha, "started_at": now})
    try:
        sent = client.send_message(channel, text)
    except Exception:
        workspace.release_published(channel, name)
        raise
    record = {
        "status": "published", "channel": channel, "message_id": sent["message_id"], "sha256": sha,
        "published_at": now, "link": _link(channel, sent["message_id"]), "text": text, "edits": [],
    }
    try:
        workspace.write_published(channel, name, record)
    except OSError as exc:
        raise TelegramError(
            f"Пост ВЫШЕЛ (сообщение {sent['message_id']}), но запись о нём не сохранилась: {exc}", "RECORD_FAILED"
        ) from None
    return {"status": "published", "draft": name, "channel": channel, "message_id": sent["message_id"],
            "link": record["link"]}


def edit_published(client, channel, name, confirm_sha256):
    record = workspace.read_published(channel, name)
    if not record or record.get("status") != "published":
        raise TelegramError(f"«{name}» не опубликован этим сервером: править нечего.", "NOT_PUBLISHED")
    text, sha = _gate(client, channel, name, confirm_sha256)
    if sha == record["sha256"]:
        raise TelegramError("Текст не отличается от опубликованного.", "NOT_MODIFIED")
    client.edit_message_text(channel, record["message_id"], text)
    record["edits"].append({"at": datetime.now(timezone.utc).isoformat(), "previous_sha256": record["sha256"],
                            "previous_text": record["text"]})
    record["sha256"], record["text"] = sha, text
    try:
        workspace.write_published(channel, name, record)
    except OSError as exc:
        raise TelegramError(f"Пост ИСПРАВЛЕН, но запись не обновилась: {exc}", "RECORD_FAILED") from None
    return {"status": "edited", "draft": name, "channel": channel, "message_id": record["message_id"],
            "link": record.get("link"), "edit_count": len(record["edits"])}
