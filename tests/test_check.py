import json
import os
import unittest
from unittest.mock import patch

from telegram_mcp import server
from telegram_mcp.checks import assess_member, normalize_channel, parse_allowed_channels
from telegram_mcp.client import TelegramClient, TelegramError

TOKEN = "123456:SECRET-TOKEN-VALUE"


class FakeClient:
    def __init__(self, member=None, fail_chat=False):
        self.member = member or {"status": "administrator", "can_post_messages": True, "can_edit_messages": True}
        self.fail_chat = fail_chat

    def get_me(self):
        return {"id": 42, "username": "pub_bot", "first_name": "Publisher"}

    def get_chat(self, chat_id):
        if self.fail_chat:
            raise TelegramError("getChat: chat not found", "API_ERROR")
        return {"id": -100, "title": "Bot Dev", "type": "channel"}

    def get_chat_member(self, chat_id, user_id):
        assert user_id == 42
        return self.member


class ChannelNamesTests(unittest.TestCase):
    def test_links_and_names_are_normalized(self):
        for value in ("https://t.me/bot_dev_py_ai", "t.me/bot_dev_py_ai", "bot_dev_py_ai", "@bot_dev_py_ai"):
            self.assertEqual(normalize_channel(value), "@bot_dev_py_ai")
        self.assertEqual(normalize_channel("-1001234567890"), "-1001234567890")

    def test_list_is_split_and_blank_parts_ignored(self):
        self.assertEqual(parse_allowed_channels("@a, b ,,"), ["@a", "@b"])
        self.assertEqual(parse_allowed_channels(""), [])
        self.assertEqual(parse_allowed_channels(None), [])


class AssessTests(unittest.TestCase):
    chat = {"title": "Bot Dev", "type": "channel"}

    def test_minimal_rights_are_ok(self):
        member = {"status": "administrator", "can_post_messages": True, "can_edit_messages": True}
        report = assess_member("@c", self.chat, member)
        self.assertTrue(report["ok"])
        self.assertEqual(report["warnings"], [])

    def test_extra_rights_produce_a_warning(self):
        member = {"status": "administrator", "can_post_messages": True, "can_delete_messages": True,
                  "can_invite_users": True}
        report = assess_member("@c", self.chat, member)
        self.assertFalse(report["ok"])
        self.assertEqual(report["extra_rights"], ["can_delete_messages", "can_invite_users"])

    def test_missing_post_right_is_reported(self):
        report = assess_member("@c", self.chat, {"status": "administrator"})
        self.assertFalse(report["can_post"])
        self.assertFalse(report["ok"])

    def test_non_admin_and_non_channel(self):
        self.assertFalse(assess_member("@c", self.chat, {"status": "left"})["ok"])
        group = {"title": "G", "type": "supergroup"}
        member = {"status": "administrator", "can_post_messages": True}
        self.assertFalse(assess_member("@c", group, member)["ok"])


class CheckToolTests(unittest.TestCase):
    def run_tool(self, client, channels="@bot_dev_py_ai"):
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_CHANNELS": channels}), \
                patch.object(server, "CLIENT", client):
            return json.loads(server.telegram_check())

    def test_ok(self):
        result = self.run_tool(FakeClient())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["bot"]["username"], "pub_bot")

    def test_unreachable_channel_needs_attention(self):
        result = self.run_tool(FakeClient(fail_chat=True))
        self.assertEqual(result["status"], "attention")
        self.assertIn("chat not found", result["channels"][0]["warnings"][0])

    def test_no_channels_configured_is_a_structured_error(self):
        result = self.run_tool(FakeClient(), channels="")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["code"], "NO_CHANNELS")

    def test_missing_token_is_a_structured_error(self):
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_CHANNELS": "@c"}), \
                patch.object(server, "CLIENT", TelegramClient("")):
            result = json.loads(server.telegram_check())
        self.assertEqual(result["code"], "NO_TOKEN")


class ClientTests(unittest.TestCase):
    def test_api_error_is_raised_with_description(self):
        client = TelegramClient(TOKEN)
        with patch.object(client, "_post", return_value={"ok": False, "description": "Forbidden"}):
            with self.assertRaises(TelegramError) as caught:
                client.get_me()
        self.assertIn("Forbidden", str(caught.exception))

    def test_token_is_removed_from_error_text(self):
        client = TelegramClient(TOKEN)
        data = {"ok": False, "description": f"bad url /bot{TOKEN}/getMe"}
        with patch.object(client, "_post", return_value=data):
            with self.assertRaises(TelegramError) as caught:
                client.get_me()
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertIn("<TOKEN>", str(caught.exception))

    def test_none_params_are_not_sent(self):
        client = TelegramClient(TOKEN)
        with patch.object(client, "_post", return_value={"ok": True, "result": {}}) as post:
            client.call("getChat", chat_id="@c", extra=None)
        post.assert_called_once_with("getChat", {"chat_id": "@c"})


if __name__ == "__main__":
    unittest.main()
