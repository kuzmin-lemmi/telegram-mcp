import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from telethon import errors

from telegram_mcp import account_store
from telegram_mcp.account import AccountClient, peer, translate
from telegram_mcp.client import TelegramError
from test_token import FakeKeyring

STORED = {"api_id": 12345, "api_hash": "0123456789abcdef0123456789abcdef", "session": "1SECRET-SESSION"}


class FakeTelethon:
    def __init__(self, authorized=True, perms=None, fail=None):
        self.authorized = authorized
        self.perms = perms
        self.fail = fail
        self.connected = False
        self.calls = []

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connected = True

    async def is_user_authorized(self):
        self.calls.append("is_user_authorized")
        return self.authorized

    async def get_me(self):
        if self.fail:
            raise self.fail
        return SimpleNamespace(id=42, username="anton", first_name="Антон")

    async def get_entity(self, value):
        from telethon.tl.types import Channel

        self.calls.append(("get_entity", value))
        entity = Channel.__new__(Channel)
        entity.id, entity.title, entity.broadcast, entity.username = 100, "Bot Dev", True, "bot_dev_py_ai"
        return entity

    async def get_permissions(self, value, user):
        if isinstance(self.perms, Exception):
            raise self.perms
        return self.perms


def perms(creator=False, admin=False, left=False, post=False, edit=False, pin=False):
    return SimpleNamespace(is_creator=creator, is_admin=admin or creator, has_left=left,
                           post_messages=post, edit_messages=edit, pin_messages=pin)


def make(fake, stored=STORED):
    created = []

    def factory(api_id, api_hash, session):
        created.append((api_id, api_hash, session))
        return fake

    return AccountClient(load=lambda: stored, factory=factory), created


class AccountStoreTests(unittest.TestCase):
    def test_round_trip(self):
        with patch.dict(sys.modules, {"keyring": FakeKeyring()}):
            account_store.store_account("12345", STORED["api_hash"], STORED["session"])
            self.assertEqual(account_store.get_account(), STORED)
            self.assertTrue(account_store.delete_account())
            self.assertIsNone(account_store.get_account())
            self.assertFalse(account_store.delete_account())

    def test_broken_record_or_backend_means_no_login(self):
        with patch.dict(sys.modules, {"keyring": FakeKeyring("not json")}):
            self.assertIsNone(account_store.get_account())
        broken = FakeKeyring()
        broken.get_password = lambda *a: (_ for _ in ()).throw(RuntimeError("no backend"))
        with patch.dict(sys.modules, {"keyring": broken}):
            self.assertIsNone(account_store.get_account())


class AccountClientTests(unittest.TestCase):
    def test_no_login(self):
        client = AccountClient(load=lambda: None)
        with self.assertRaises(TelegramError) as caught:
            client.get_me()
        self.assertEqual(caught.exception.code, "NOT_LOGGED_IN")

    def test_revoked_session_is_reported_and_reloaded_next_time(self):
        client, created = make(FakeTelethon(authorized=False))
        for _ in range(2):
            with self.assertRaises(TelegramError) as caught:
                client.get_me()
            self.assertEqual(caught.exception.code, "NOT_LOGGED_IN")
        self.assertEqual(len(created), 2)

    def test_me_and_channel(self):
        fake = FakeTelethon(perms=perms(creator=True))
        client, created = make(fake)
        self.assertEqual(client.get_me()["username"], "anton")
        channel = client.get_channel("@bot_dev_py_ai")
        self.assertEqual(channel["type"], "channel")
        self.assertEqual(channel["title"], "Bot Dev")
        self.assertEqual(len(created), 1)
        self.assertEqual(fake.calls.count("is_user_authorized"), 1)

    def test_numeric_channel_id_becomes_int(self):
        self.assertEqual(peer("-1001234567890"), -1001234567890)
        self.assertEqual(peer("@bot_dev_py_ai"), "@bot_dev_py_ai")

    def test_rights(self):
        cases = [
            (perms(creator=True), {"status": "creator", "can_pin_messages": True}),
            (perms(admin=True, post=True, edit=True), {"status": "administrator", "can_pin_messages": False}),
            (perms(left=True), {"status": "left"}),
            (perms(), {"status": "member"}),
            (errors.UserNotParticipantError(None), {"status": "left"}),
        ]
        for value, expected in cases:
            client, _ = make(FakeTelethon(perms=value))
            rights = client.get_my_rights("@c")
            for key, wanted in expected.items():
                self.assertEqual(rights.get(key, False), wanted, (value, key))

    def test_errors_are_translated_without_secrets(self):
        fail = errors.RPCError(None, f"strange {STORED['session']} {STORED['api_hash']}", 400)
        client, _ = make(FakeTelethon(fail=fail))
        with self.assertRaises(TelegramError) as caught:
            client.get_me()
        self.assertEqual(caught.exception.code, "API_ERROR")
        self.assertNotIn(STORED["session"], str(caught.exception))
        self.assertNotIn(STORED["api_hash"], str(caught.exception))

    def test_flood_wait_revoked_key_and_network(self):
        flood = translate(errors.FloodWaitError(None, capture=30))
        self.assertEqual(flood.code, "FLOOD_WAIT")
        self.assertIn("30", str(flood))
        self.assertEqual(translate(errors.AuthKeyUnregisteredError(None)).code, "NOT_LOGGED_IN")
        self.assertEqual(translate(ValueError('No user has "x" as username')).code, "NOT_FOUND")
        self.assertEqual(translate(ConnectionError("down")).code, "NETWORK_ERROR")


if __name__ == "__main__":
    unittest.main()
