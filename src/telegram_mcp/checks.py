"""Проверка прав бота в каналах. Чистая логика без сетевых вызовов."""

# Этих прав для работы не нужно; если они включены, сервер предупреждает.
EXTRA_RIGHTS = (
    "can_delete_messages",
    "can_change_info",
    "can_invite_users",
    "can_pin_messages",
    "can_promote_members",
    "can_restrict_members",
    "can_manage_video_chats",
    "can_post_stories",
    "can_edit_stories",
    "can_delete_stories",
)

RIGHTS_LABELS = {
    "can_delete_messages": "удаление сообщений",
    "can_change_info": "изменение информации о канале",
    "can_invite_users": "приглашение пользователей",
    "can_pin_messages": "закрепление сообщений",
    "can_promote_members": "назначение администраторов",
    "can_restrict_members": "блокировка участников",
    "can_manage_video_chats": "управление трансляциями",
    "can_post_stories": "публикация историй",
    "can_edit_stories": "правка историй",
    "can_delete_stories": "удаление историй",
}


def normalize_channel(value):
    """``https://t.me/name``, ``t.me/name`` и ``name`` превращаются в ``@name``; числовые ID остаются."""
    value = value.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.split("/")[0].split("?")[0]
    if not value:
        raise ValueError("пустое имя канала")
    if value.lstrip("-").isdigit():
        return value
    return value if value.startswith("@") else "@" + value


def parse_allowed_channels(raw):
    return [normalize_channel(part) for part in (raw or "").split(",") if part.strip()]


def assess_member(channel, chat, member):
    """Сводка о том, как бот состоит в канале, и предупреждения."""
    warnings = []
    status = member.get("status")
    report = {
        "channel": channel,
        "title": chat.get("title"),
        "type": chat.get("type"),
        "bot_status": status,
        "can_post": False,
        "can_edit": False,
        "extra_rights": [],
        "warnings": warnings,
    }
    if chat.get("type") != "channel":
        warnings.append(f"Это не канал, а «{chat.get('type')}». Сервер рассчитан на каналы.")
    if status == "creator":
        warnings.append("Бот — владелец канала. Так быть не должно.")
        report["can_post"] = report["can_edit"] = True
    elif status == "administrator":
        report["can_post"] = bool(member.get("can_post_messages"))
        report["can_edit"] = bool(member.get("can_edit_messages"))
        report["extra_rights"] = [right for right in EXTRA_RIGHTS if member.get(right)]
        if not report["can_post"]:
            warnings.append("У бота нет права «Публикация сообщений»: опубликовать пост не получится.")
        if report["extra_rights"]:
            names = ", ".join(RIGHTS_LABELS[right] for right in report["extra_rights"])
            warnings.append(f"Лишние права бота: {names}. Лучше их выключить.")
    else:
        warnings.append(f"Бот не администратор канала (статус: {status}). Добавьте его администратором.")
    report["ok"] = report["can_post"] and not warnings
    return report
