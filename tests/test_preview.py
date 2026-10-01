import json
import os
import unittest
from unittest.mock import patch

from telegram_mcp import server, workspace
from telegram_mcp.client import TelegramError
from test_drafts import WorkspaceTestCase


def update(user_id, name="Anton", chat_type="private", is_bot=False, text="/start"):
    return {"message": {"from": {"id": user_id, "first_name": name, "username": name.lower(), "is_bot": is_bot},
                        "chat": {"id": user_id, "type": chat_type}, "text": text}}


class FakeClient:
    def __init__(self, updates=None, fail_send=None):
        self.updates = updates if updates is not None else [update(111)]
        self.fail_send = fail_send
        self.sent = []

    def get_updates(self):
        return self.updates

    def send_message(self, chat_id, text, parse_mode="HTML"):
        if self.fail_send:
            raise TelegramError(self.fail_send, "API_ERROR")
        self.sent.append((chat_id, text, parse_mode))
        return {"message_id": 500 + len(self.sent)}


class OwnerAndPreviewTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.client = FakeClient()
        patcher = patch.object(server, "CLIENT", self.client)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = patch.dict(os.environ)
        env.start()
        os.environ.pop("TELEGRAM_OWNER_ID", None)
        self.addCleanup(env.stop)
        server.telegram_init_channel()

    def call(self, tool, **kwargs):
        return json.loads(tool(**kwargs))

    def test_candidates_skip_bots_groups_and_duplicates(self):
        self.client.updates = [
            update(111), update(111, text="again"), update(222, is_bot=True), update(333, chat_type="supergroup"),
            update(444, name="Maria"),
        ]
        result = self.call(server.telegram_find_owner)
        self.assertEqual([c["user_id"] for c in result["candidates"]], [111, 444])

    def test_no_updates_is_explained(self):
        self.client.updates = []
        self.assertEqual(self.call(server.telegram_find_owner)["code"], "NO_UPDATES")

    def test_owner_must_be_someone_who_wrote_to_the_bot(self):
        self.assertEqual(self.call(server.telegram_set_owner, user_id=999)["code"], "UNKNOWN_USER")
        with self.assertRaises(TelegramError):
            workspace.get_owner()
        self.assertEqual(self.call(server.telegram_set_owner, user_id=111)["status"], "saved")
        self.assertEqual(workspace.get_owner()["user_id"], 111)

    def test_env_owner_overrides_file(self):
        workspace.save_owner(111, "Anton")
        with patch.dict(os.environ, {"TELEGRAM_OWNER_ID": "555"}):
            self.assertEqual(workspace.get_owner(), {"user_id": 555, "source": "env"})
        with patch.dict(os.environ, {"TELEGRAM_OWNER_ID": "abc"}):
            with self.assertRaises(TelegramError):
                workspace.get_owner()

    def test_preview_goes_only_to_owner_and_is_recorded(self):
        workspace.save_owner(111, "Anton")
        server.telegram_save_draft(name="fsm", text="<b>FSM</b>\r\n")
        result = self.call(server.telegram_preview, name="fsm")
        self.assertEqual(result["status"], "sent_to_owner")
        self.assertEqual(self.client.sent, [(111, "<b>FSM</b>", "HTML")])
        record = workspace.get_preview("@bot_dev_py_ai", "fsm")
        self.assertEqual(record["sha256"], result["sha256"])
        self.assertEqual(record["message_id"], 501)

    def test_preview_hash_matches_check_hash(self):
        workspace.save_owner(111, "Anton")
        server.telegram_save_draft(name="fsm", text="<b>FSM</b>")
        preview = self.call(server.telegram_preview, name="fsm")
        self.assertEqual(preview["sha256"], self.call(server.telegram_check_draft, name="fsm")["sha256"])

    def test_invalid_draft_is_not_sent(self):
        workspace.save_owner(111, "Anton")
        server.telegram_save_draft(name="bad", text="<h1>x</h1>")
        self.assertEqual(self.call(server.telegram_preview, name="bad")["code"], "DRAFT_INVALID")
        self.assertEqual(self.client.sent, [])
        self.assertIsNone(workspace.get_preview("@bot_dev_py_ai", "bad"))

    def test_preview_without_owner_explains_what_to_do(self):
        server.telegram_save_draft(name="fsm", text="<b>FSM</b>")
        self.assertEqual(self.call(server.telegram_preview, name="fsm")["code"], "NO_OWNER")

    def test_unreachable_owner_gets_a_hint(self):
        workspace.save_owner(111, "Anton")
        server.telegram_save_draft(name="fsm", text="<b>FSM</b>")
        self.client.fail_send = "sendMessage: Forbidden: bot can't initiate conversation with a user"
        self.assertEqual(self.call(server.telegram_preview, name="fsm")["code"], "OWNER_UNREACHABLE")
        self.assertIsNone(workspace.get_preview("@bot_dev_py_ai", "fsm"))

    def test_corrupt_state_file_is_reported_not_overwritten(self):
        (self.root / ".owner.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(TelegramError) as caught:
            workspace.get_owner()
        self.assertEqual(caught.exception.code, "BAD_STATE_FILE")
        self.assertEqual((self.root / ".owner.json").read_text(encoding="utf-8"), "{broken")


if __name__ == "__main__":
    unittest.main()
