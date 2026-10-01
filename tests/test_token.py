import io
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from telegram_mcp import setup, token_store
from telegram_mcp.client import TelegramClient, TelegramError

SECRET = "123456:VERY-SECRET-TOKEN"


class FakeKeyring(types.ModuleType):
    class errors:  # noqa: N801
        class PasswordDeleteError(Exception):
            pass

    def __init__(self, stored=None):
        super().__init__("keyring")
        self.stored = stored

    def get_password(self, service, account):
        return self.stored

    def set_password(self, service, account, value):
        self.stored = value

    def delete_password(self, service, account):
        if self.stored is None:
            raise self.errors.PasswordDeleteError()
        self.stored = None


class TokenStoreTests(unittest.TestCase):
    def test_environment_wins_over_keyring(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "from-env"}), \
                patch.dict(sys.modules, {"keyring": FakeKeyring("from-store")}):
            self.assertEqual(token_store.get_token(), "from-env")

    def test_keyring_is_used_without_environment(self):
        env = {k: v for k, v in os.environ.items() if k != "TELEGRAM_BOT_TOKEN"}
        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"keyring": FakeKeyring("from-store")}):
            self.assertEqual(token_store.get_token(), "from-store")

    def test_missing_keyring_backend_gives_empty_token(self):
        broken = FakeKeyring()
        broken.get_password = lambda *a: (_ for _ in ()).throw(RuntimeError("no backend"))
        env = {k: v for k, v in os.environ.items() if k != "TELEGRAM_BOT_TOKEN"}
        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"keyring": broken}):
            self.assertEqual(token_store.get_token(), "")


class LazyClientTests(unittest.TestCase):
    def test_token_is_read_lazily_and_empty_is_not_cached(self):
        values = ["", SECRET]
        client = TelegramClient(lambda: values[0])
        with self.assertRaises(TelegramError) as caught:
            client.get_me()
        self.assertEqual(caught.exception.code, "NO_TOKEN")
        values[0] = values[1]  # токен сохранили, пока сервер работал
        with patch.object(client, "_post", return_value={"ok": True, "result": {"id": 1}}) as post:
            self.assertEqual(client.get_me(), {"id": 1})
        post.assert_called_once()
        self.assertEqual(client._redact(f"url /bot{SECRET}/x"), "url /bot<TOKEN>/x")


class SetupTests(unittest.TestCase):
    def run_setup(self, argv, typed=SECRET, me=None, fail=None):
        fake = FakeKeyring()
        out = io.StringIO()

        def get_me(self):
            if fail:
                raise TelegramError(fail, "API_ERROR")
            return me or {"username": "pub_bot"}

        with patch.dict(sys.modules, {"keyring": fake}), patch("getpass.getpass", return_value=typed), \
                patch.object(TelegramClient, "get_me", get_me), redirect_stdout(out):
            code = setup.main(argv)
        return code, out.getvalue(), fake

    def test_valid_token_is_saved_and_never_printed(self):
        code, output, fake = self.run_setup([])
        self.assertEqual(code, 0)
        self.assertEqual(fake.stored, SECRET)
        self.assertIn("@pub_bot", output)
        self.assertNotIn(SECRET, output)

    def test_rejected_token_is_not_saved(self):
        code, output, fake = self.run_setup([], fail="getMe: Unauthorized")
        self.assertEqual(code, 1)
        self.assertIsNone(fake.stored)
        self.assertNotIn(SECRET, output)

    def test_empty_input_saves_nothing(self):
        code, _, fake = self.run_setup([], typed="  ")
        self.assertEqual(code, 1)
        self.assertIsNone(fake.stored)

    def test_delete(self):
        fake = FakeKeyring(SECRET)
        out = io.StringIO()
        with patch.dict(sys.modules, {"keyring": fake}), redirect_stdout(out):
            self.assertEqual(setup.main(["--delete"]), 0)
        self.assertIsNone(fake.stored)


if __name__ == "__main__":
    unittest.main()
