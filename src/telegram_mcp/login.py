"""Вход в аккаунт Telegram для сервера: ``telegram-mcp-login``.

api_id и api_hash берутся с my.telegram.org. Номер, код и облачный пароль
вводятся здесь, в терминале, и уходят только в Telegram. В хранилище ОС
сохраняются api_id, api_hash и строка сессии; на экран выводится только имя.
"""

import argparse
import asyncio
import getpass
import re
import sys

from . import account_store
from .account import new_client


CODE_ATTEMPTS = 3


def code_destination(code_type):
    """Куда Telegram отправил код — по типу из ответа auth.sendCode."""
    from telethon.tl.types import auth

    name = type(code_type).__name__
    if isinstance(code_type, auth.SentCodeTypeApp):
        return "в приложение Telegram: чат «Telegram» с синей галочкой на другом вашем устройстве (загляните и в Архив)"
    if isinstance(code_type, auth.SentCodeTypeEmailCode):
        return f"на почту для входа {code_type.email_pattern}"
    if isinstance(code_type, auth.SentCodeTypeMissedCall):
        return f"пропущенным звонком: код — последние {code_type.length} цифр номера, с которого позвонят"
    if isinstance(code_type, (auth.SentCodeTypeCall, auth.SentCodeTypeFlashCall)):
        return "звонком"
    if isinstance(code_type, auth.SentCodeTypeSetUpEmailRequired):
        return ("никуда: Telegram требует сначала привязать почту для входа. "
                "В приложении: Настройки → Конфиденциальность → Почта для входа")
    if "Sms" in name:
        return "по SMS"
    return f"способом {name}"


async def sign_in(api_id, api_hash):
    """Интерактивный вход. Возвращает (имя для показа, строка сессии)."""
    from telethon import errors

    client = new_client(api_id, api_hash)
    try:
        await client.connect()
        phone = normalize_phone(input("Номер телефона (например, 89991234567): "))
        sent = await client.send_code_request(phone)
        print(f"Код отправлен {code_destination(sent.type)}.")
        if sent.next_type:
            print("Если код не пришёл за пару минут, нажмите Enter без кода — Telegram отправит его другим способом.")
        attempts = 0
        while True:
            code = input("Код: ").strip()
            if not code:
                sent = await client.send_code_request(phone, force_sms=True)
                print(f"Код отправлен повторно {code_destination(sent.type)}.")
                continue
            try:
                await client.sign_in(phone, code)
                break
            except errors.SessionPasswordNeededError:
                await client.sign_in(password=getpass.getpass("Облачный пароль (символы не отображаются): "))
                break
            except errors.PhoneCodeInvalidError:
                attempts += 1
                if attempts >= CODE_ATTEMPTS:
                    raise
                print("Неверный код, попробуйте ещё раз.")
        me = await client.get_me()
        return display_name(me), client.session.save()
    finally:
        await client.disconnect()


async def whoami(account):
    client = new_client(account["api_id"], account["api_hash"], account["session"])
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return None
        return display_name(await client.get_me())
    finally:
        await client.disconnect()


async def log_out(account):
    """Завершает сеанс на стороне Telegram. False, если он уже недействителен."""
    client = new_client(account["api_id"], account["api_hash"], account["session"])
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return False
        return bool(await client.log_out())
    finally:
        if client.is_connected():
            await client.disconnect()


def normalize_phone(raw):
    """Российские ``8…`` и ``9…`` без кода страны превращаются в ``+7…``."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] == "8":
        return "+7" + digits[1:]
    if len(digits) == 10 and digits[0] == "9":
        return "+7" + digits
    return "+" + digits


def display_name(me):
    name = " ".join(part for part in (me.first_name, me.last_name) if part)
    return f"{name} (@{me.username})" if me.username else name


def describe(exc):
    """Текст ошибки входа без секретов."""
    from telethon import errors

    if isinstance(exc, errors.ApiIdInvalidError):
        return "Telegram не принял api_id или api_hash. Проверьте их на my.telegram.org."
    if isinstance(exc, errors.PhoneNumberInvalidError):
        return "Неверный номер телефона."
    if isinstance(exc, errors.PhoneCodeInvalidError):
        return "Код трижды введён неверно."
    if isinstance(exc, errors.PhoneCodeExpiredError):
        return "Код устарел. Запустите вход заново."
    if isinstance(exc, errors.PasswordHashInvalidError):
        return "Неверный облачный пароль."
    if isinstance(exc, errors.SendCodeUnavailableError):
        return "Telegram исчерпал способы отправки кода. Подождите несколько часов и попробуйте снова."
    if isinstance(exc, errors.FloodWaitError):
        return f"Слишком много попыток. Telegram просит подождать {exc.seconds} с."
    if isinstance(exc, errors.RPCError):
        return f"Telegram отказал: {type(exc).__name__}."
    return f"{type(exc).__name__}: {exc}"


def ask_credentials():
    api_id = input("api_id (число с my.telegram.org): ").strip()
    if not api_id.isdigit():
        print("api_id — это число. Ничего не сохранено.")
        return None
    api_hash = input("api_hash (32 символа с my.telegram.org): ").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", api_hash):
        print("api_hash — 32 символа из цифр и букв a–f. Ничего не сохранено.")
        return None
    return int(api_id), api_hash


def main(argv=None):
    parser = argparse.ArgumentParser(prog="telegram-mcp-login", description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true", help="проверить сохранённый вход и показать, чей он")
    group.add_argument("--logout", action="store_true", help="завершить сеанс в Telegram и удалить вход из хранилища")
    args = parser.parse_args(argv)

    old = account_store.get_account()

    if args.status:
        if not old:
            print("Вход не выполнен.")
            return 1
        try:
            name = asyncio.run(whoami(old))
        except Exception as exc:  # noqa: BLE001
            print(f"Не удалось проверить вход: {describe(exc)}")
            return 1
        print(f"Вход сохранён: {name}." if name else "Сеанс недействителен. Войдите заново: telegram-mcp-login")
        return 0 if name else 1

    if args.logout:
        if not old:
            print("Сохранённого входа нет.")
            return 0
        try:
            closed = asyncio.run(log_out(old))
        except Exception as exc:  # noqa: BLE001
            closed = False
            print(f"Сеанс в Telegram завершить не удалось ({describe(exc)}). Завершите его в «Настройки → Устройства».")
        account_store.delete_account()
        print(("Сеанс завершён, " if closed else "") + "вход удалён из хранилища.")
        return 0

    if old and input("Вход уже сохранён. Войти заново? [y/N]: ").strip().lower() not in ("y", "д"):
        print("Оставлен прежний вход.")
        return 0

    credentials = ask_credentials()
    if not credentials:
        return 1
    api_id, api_hash = credentials
    try:
        name, session = asyncio.run(sign_in(api_id, api_hash))
    except KeyboardInterrupt:
        print("\nВход отменён. Ничего не сохранено.")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Вход не удался: {describe(exc)}\nНичего не сохранено.")
        return 1
    account_store.store_account(api_id, api_hash, session)
    print(f"Готово. Вход выполнен: {name}. Данные сохранены в защищённом хранилище.")
    if old:
        try:
            asyncio.run(log_out(old))
            print("Прежний сеанс завершён.")
        except Exception:  # noqa: BLE001
            print("Прежний сеанс завершить не удалось: при желании завершите его в «Настройки → Устройства».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
