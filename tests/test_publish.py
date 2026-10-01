import asyncio
import json
import os
import unittest
from unittest.mock import patch

from telegram_mcp import server, workspace
from telegram_mcp.client import TelegramError
from test_drafts import WorkspaceTestCase

CHANNEL = "@bot_dev_py_ai"
ADMIN = {"status": "administrator", "can_post_messages": True, "can_edit_messages": True}


class FakeClient:
    def __init__(self):
        self.member = dict(ADMIN)
        self.sent = []
        self.edited = []
        self.fail_send = None
        self.fail_edit = None

    def get_me(self):
        return {"id": 42, "username": "pub_bot", "first_name": "Publisher"}

    def get_chat(self, chat_id):
        return {"id": -100, "title": "Bot Dev", "type": "channel"}

    def get_chat_member(self, chat_id, user_id):
        return self.member

    def send_message(self, chat_id, text, parse_mode="HTML"):
        if self.fail_send:
            raise TelegramError(self.fail_send, "API_ERROR")
        self.sent.append((chat_id, text))
        return {"message_id": 1000 + len(self.sent)}

    def edit_message_text(self, chat_id, message_id, text, parse_mode="HTML"):
        if self.fail_edit:
            raise TelegramError(self.fail_edit, "API_ERROR")
        self.edited.append((chat_id, message_id, text))
        return {"message_id": message_id}


class PublishTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.client = FakeClient()
        for patcher in (patch.object(server, "CLIENT", self.client), patch.dict(os.environ)):
            patcher.start()
            self.addCleanup(patcher.stop)
        os.environ.pop("TELEGRAM_OWNER_ID", None)
        server.telegram_init_channel()
        workspace.save_owner(111, "Anton")

    def call(self, tool, **kwargs):
        return json.loads(tool(**kwargs))

    def prepare(self, name="fsm", text="<b>FSM</b> за минуту", preview=True, overwrite=False):
        saved = self.call(server.telegram_save_draft, name=name, text=text, overwrite=overwrite)
        sha = saved["sha256"]
        if preview:
            with patch.object(server, "CLIENT", self.client):
                # просмотр использует тот же фейковый клиент
                self.client.get_updates = lambda: []
                self.assertEqual(self.call(server.telegram_preview, name=name)["status"], "sent_to_owner")
        return sha

    def publish(self, name="fsm", sha=None, **kwargs):
        return self.call(server.telegram_publish, name=name, confirm_sha256=sha, **kwargs)

    # -- публикация --------------------------------------------------------

    def test_happy_path_publishes_and_records(self):
        sha = self.prepare()
        result = self.publish(sha=sha)
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["link"], "https://t.me/bot_dev_py_ai/1002")
        self.assertEqual(self.client.sent[-1], (CHANNEL, "<b>FSM</b> за минуту"))
        record = workspace.read_published(CHANNEL, "fsm")
        self.assertEqual((record["status"], record["sha256"], record["message_id"]), ("published", sha, 1002))
        self.assertEqual(self.call(server.telegram_list_published)["published"][0]["name"], "fsm")

    def test_preview_sends_to_owner_not_to_channel(self):
        self.prepare()
        self.assertEqual(self.client.sent, [(111, "<b>FSM</b> за минуту")])

    def test_not_previewed_is_refused(self):
        sha = self.prepare(preview=False)
        self.assertEqual(self.publish(sha=sha)["code"], "NOT_PREVIEWED")
        self.assertFalse([m for m in self.client.sent if m[0] == CHANNEL])

    def test_text_changed_after_preview_is_refused(self):
        self.prepare()
        new_sha = self.call(server.telegram_save_draft, name="fsm", text="<b>Другое</b>", overwrite=True)["sha256"]
        self.assertEqual(self.publish(sha=new_sha)["code"], "CHANGED_AFTER_PREVIEW")
        self.assertFalse([m for m in self.client.sent if m[0] == CHANNEL])

    def test_wrong_or_missing_confirmation_is_refused(self):
        self.prepare()
        for sha in (None, "", "0" * 64, "abc"):
            with self.subTest(sha=sha):
                self.assertEqual(self.publish(sha=sha)["code"], "BAD_CONFIRMATION")
        self.assertFalse([m for m in self.client.sent if m[0] == CHANNEL])

    def test_channel_outside_allowlist_is_refused(self):
        sha = self.prepare()
        self.assertEqual(self.publish(sha=sha, channel="@someone_else")["code"], "CHANNEL_NOT_ALLOWED")
        self.assertFalse([m for m in self.client.sent if m[0] == CHANNEL])

    def test_second_publish_of_same_draft_is_refused(self):
        sha = self.prepare()
        self.publish(sha=sha)
        self.assertEqual(self.publish(sha=sha)["code"], "ALREADY_PUBLISHED")
        self.assertEqual(len([m for m in self.client.sent if m[0] == CHANNEL]), 1)

    def test_failed_send_leaves_no_record_and_allows_retry(self):
        sha = self.prepare()
        self.client.fail_send = "sendMessage: Bad Request: chat not found"
        self.assertEqual(self.publish(sha=sha)["code"], "API_ERROR")
        self.assertIsNone(workspace.read_published(CHANNEL, "fsm"))
        self.client.fail_send = None
        self.assertEqual(self.publish(sha=sha)["status"], "published")

    def test_interrupted_send_blocks_blind_retry(self):
        sha = self.prepare()
        workspace.reserve_published(CHANNEL, "fsm", {"status": "sending", "sha256": sha})
        result = self.publish(sha=sha)
        self.assertEqual(result["code"], "ALREADY_PUBLISHED")
        self.assertIn("Проверьте канал", result["message"])
        self.assertFalse([m for m in self.client.sent if m[0] == CHANNEL])

    def test_bot_without_post_right_is_refused(self):
        sha = self.prepare()
        self.client.member = {"status": "administrator", "can_post_messages": False}
        self.assertEqual(self.publish(sha=sha)["code"], "NO_POST_RIGHT")
        self.assertFalse([m for m in self.client.sent if m[0] == CHANNEL])

    def test_invalid_draft_is_refused(self):
        sha = self.call(server.telegram_save_draft, name="bad", text="<h1>x</h1>")["sha256"]
        self.assertEqual(self.publish(name="bad", sha=sha)["code"], "DRAFT_INVALID")

    def test_lost_record_after_send_is_reported_loudly(self):
        sha = self.prepare()
        with patch.object(workspace, "write_published", side_effect=OSError("disk full")):
            result = self.publish(sha=sha)
        self.assertEqual(result["code"], "RECORD_FAILED")
        self.assertIn("ВЫШЕЛ", result["message"])

    # -- правка ------------------------------------------------------------

    def test_edit_flow_updates_message_and_keeps_history(self):
        self.publish(sha=self.prepare())
        new_sha = self.prepare(text="<b>FSM</b> за две минуты", overwrite=True)
        result = self.call(server.telegram_edit_published, name="fsm", confirm_sha256=new_sha)
        self.assertEqual((result["status"], result["edit_count"]), ("edited", 1))
        self.assertEqual(self.client.edited, [(CHANNEL, 1002, "<b>FSM</b> за две минуты")])
        record = workspace.read_published(CHANNEL, "fsm")
        self.assertEqual(record["sha256"], new_sha)
        self.assertEqual(record["edits"][0]["previous_text"], "<b>FSM</b> за минуту")

    def test_edit_requires_preview_and_a_published_post(self):
        sha = self.prepare()
        self.assertEqual(self.call(server.telegram_edit_published, name="fsm", confirm_sha256=sha)["code"],
                         "NOT_PUBLISHED")
        self.publish(sha=sha)
        new_sha = self.prepare(text="<b>Новое</b>", overwrite=True, preview=False)
        self.assertEqual(self.call(server.telegram_edit_published, name="fsm", confirm_sha256=new_sha)["code"],
                         "CHANGED_AFTER_PREVIEW")
        self.assertEqual(self.client.edited, [])

    def test_edit_with_same_text_is_refused(self):
        sha = self.prepare()
        self.publish(sha=sha)
        self.assertEqual(self.call(server.telegram_edit_published, name="fsm", confirm_sha256=sha)["code"],
                         "NOT_MODIFIED")

    def test_failed_edit_keeps_record_unchanged(self):
        sha = self.prepare()
        self.publish(sha=sha)
        new_sha = self.prepare(text="<b>Новое</b>", overwrite=True)
        self.client.fail_edit = "editMessageText: Bad Request: message can't be edited"
        self.assertEqual(self.call(server.telegram_edit_published, name="fsm", confirm_sha256=new_sha)["code"],
                         "API_ERROR")
        self.assertEqual(workspace.read_published(CHANNEL, "fsm")["sha256"], sha)

    # -- чего быть не должно ----------------------------------------------

    def test_no_tool_can_delete_anything(self):
        names = [tool.name for tool in asyncio.run(server.mcp.list_tools())]
        self.assertFalse([n for n in names if "delete" in n or "remove" in n], names)
        for method in ("delete_message", "deleteMessage"):
            self.assertFalse(hasattr(self.client, method))


if __name__ == "__main__":
    unittest.main()
