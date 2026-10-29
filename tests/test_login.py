import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from telethon import errors

from telegram_mcp import account_store, login
from test_token import FakeKeyring

API_HASH = "0123456789abcdef0123456789abcdef"
SESSION = "1SECRET-SESSION"
OLD = '{"api_id": 1, "api_hash": "%s", "session": "OLD"}' % API_HASH


async def signed_in(api_id, api_hash):
    return "Антон (@anton)", SESSION


async def logged_out(account):
    return True


async def known(account):
    return "Антон (@anton)"


class LoginTests(unittest.TestCase):
    def run_login(self, argv=(), inputs=("12345",), api_hash=API_HASH, sign_in=signed_in, stored=None,
                  log_out=logged_out):
        fake = FakeKeyring(stored)
        out = io.StringIO()
        answers = iter((*inputs, api_hash))
        with patch.dict(sys.modules, {"keyring": fake}), \
                patch("builtins.input", lambda prompt="": next(answers)), \
                patch.object(login, "sign_in", sign_in), \
                patch.object(login, "log_out", log_out), \
                patch.object(login, "whoami", known), \
                redirect_stdout(out):
            code = login.main(list(argv))
        return code, out.getvalue(), fake

    def test_success_saves_and_prints_only_the_name(self):
        code, output, fake = self.run_login()
        self.assertEqual(code, 0)
        self.assertIn("@anton", output)
        self.assertNotIn(API_HASH, output)
        self.assertNotIn(SESSION, output)
        with patch.dict(sys.modules, {"keyring": fake}):
            self.assertEqual(account_store.get_account(), {"api_id": 12345, "api_hash": API_HASH, "session": SESSION})

    def test_bad_api_id_or_hash_stop_before_network(self):
        async def must_not_run(*args):
            raise AssertionError("network")

        code, _, fake = self.run_login(inputs=("abc",), sign_in=must_not_run)
        self.assertEqual(code, 1)
        self.assertIsNone(fake.stored)
        code, _, fake = self.run_login(api_hash="short", sign_in=must_not_run)
        self.assertEqual(code, 1)
        self.assertIsNone(fake.stored)

    def test_rejected_login_saves_nothing(self):
        async def rejected(api_id, api_hash):
            raise errors.ApiIdInvalidError(None)

        code, output, fake = self.run_login(sign_in=rejected)
        self.assertEqual(code, 1)
        self.assertIn("my.telegram.org", output)
        self.assertIsNone(fake.stored)

    def test_existing_login_is_kept_unless_confirmed(self):
        code, _, fake = self.run_login(inputs=("n",), stored=OLD)
        self.assertEqual(code, 0)
        self.assertEqual(fake.stored, OLD)

    def test_relogin_closes_the_old_session(self):
        closed = []

        async def log_out(account):
            closed.append(account["session"])
            return True

        code, _, fake = self.run_login(inputs=("y", "12345"), stored=OLD, log_out=log_out)
        self.assertEqual(code, 0)
        self.assertEqual(closed, ["OLD"])
        self.assertIn(SESSION, fake.stored)

    def test_phone_is_normalized(self):
        for raw in ("89878002113", "8 (987) 800-21-13", "9878002113", "+7 987 800 21 13", "79878002113"):
            self.assertEqual(login.normalize_phone(raw), "+79878002113", raw)
        self.assertEqual(login.normalize_phone("+44 20 7946 0958"), "+442079460958")

    def test_status_and_logout(self):
        code, output, _ = self.run_login(["--status"], stored=OLD)
        self.assertEqual(code, 0)
        self.assertIn("@anton", output)
        code, _, fake = self.run_login(["--logout"], stored=OLD)
        self.assertEqual(code, 0)
        self.assertIsNone(fake.stored)
        code, _, _ = self.run_login(["--status"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
