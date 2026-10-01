"""Сохранение токена бота в защищённое хранилище ОС: ``telegram-mcp-setup``.

Токен вводится скрытно, проверяется запросом getMe и сохраняется.
На экран и в журнал выводится только имя бота.
"""

import argparse
import getpass
import sys

from . import token_store
from .client import TelegramClient, TelegramError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="telegram-mcp-setup", description=__doc__.splitlines()[0])
    parser.add_argument("--delete", action="store_true", help="удалить сохранённый токен")
    parser.add_argument("--status", action="store_true", help="показать, сохранён ли токен (сам токен не показывается)")
    args = parser.parse_args(argv)

    if args.delete:
        print("Токен удалён." if token_store.delete_token() else "Сохранённого токена не было.")
        return 0
    if args.status:
        token = token_store.get_token()
        print("Токен найден." if token else "Токен не задан.")
        return 0 if token else 1

    print("Вставьте токен бота от @BotFather. При вводе символы не отображаются.")
    token = getpass.getpass("Токен: ").strip()
    if not token:
        print("Пустой ввод, ничего не сохранено.")
        return 1
    try:
        me = TelegramClient(token).get_me()
    except TelegramError as exc:
        print(f"Telegram не принял токен: {exc}\nНичего не сохранено.")
        return 1
    token_store.store_token(token)
    print(f"Готово. Токен бота @{me.get('username')} сохранён в защищённом хранилище.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
