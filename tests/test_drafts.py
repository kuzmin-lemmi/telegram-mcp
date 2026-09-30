import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_mcp import server, workspace
from telegram_mcp.client import TelegramError
from telegram_mcp.validate import MAX_CAPTION, MAX_TEXT, check_post, content_hash


class ValidateTests(unittest.TestCase):
    def test_valid_post(self):
        result = check_post('<b>FSM</b> — это <i>память</i> бота.\n<a href="https://t.me/x">канал</a>\n<code>a &lt; b</code>')
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["warnings"], [])

    def test_unsupported_and_unclosed_tags(self):
        self.assertFalse(check_post("<h1>Заголовок</h1>")["ok"])
        self.assertFalse(check_post("<b>не закрыт")["ok"])
        self.assertFalse(check_post("<b><i>криво</b></i>")["ok"])
        self.assertFalse(check_post("строка<br/>строка")["ok"])

    def test_bare_special_characters_are_errors(self):
        self.assertFalse(check_post("a & b")["ok"])
        self.assertFalse(check_post("if a < b: pass")["ok"])
        self.assertTrue(check_post("a &amp; b &lt; c")["ok"])

    def test_links_must_be_https(self):
        self.assertFalse(check_post('<a href="javascript:alert(1)">x</a>')["ok"])
        result = check_post('<a href="http://example.com">x</a>')
        self.assertTrue(result["ok"])
        self.assertTrue(result["warnings"])

    def test_markdown_is_flagged(self):
        result = check_post("**жирный** и [ссылка](https://example.com)\n# Заголовок")
        self.assertEqual(len(result["warnings"]), 3)

    def test_markdown_inside_pre_is_not_flagged(self):
        self.assertEqual(check_post("<pre>x = **kw</pre>")["warnings"], [])

    def test_length_limits(self):
        self.assertTrue(check_post("я" * MAX_TEXT)["ok"])
        self.assertFalse(check_post("я" * (MAX_TEXT + 1))["ok"])
        self.assertFalse(check_post("я" * (MAX_CAPTION + 1), has_image=True)["ok"])
        self.assertTrue(check_post("я" * MAX_CAPTION, has_image=True)["ok"])

    def test_tags_do_not_count_towards_length(self):
        self.assertEqual(check_post("<b>abc</b>")["length"], 3)
        self.assertEqual(check_post("&lt;&amp;")["length"], 2)

    def test_empty_post_is_an_error(self):
        self.assertFalse(check_post("  \n ")["ok"])

    def test_hash_ignores_line_endings_and_edges_only(self):
        self.assertEqual(content_hash("a\r\nb\n"), content_hash("a\nb"))
        self.assertNotEqual(content_hash("a b"), content_hash("a  b"))


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TELEGRAM_MCP_TEST_TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "Channels"
        patcher = patch.dict(os.environ, {
            "TELEGRAM_CHANNEL_ROOT": str(self.root),
            "TELEGRAM_ALLOWED_CHANNELS": "@bot_dev_py_ai",
        })
        patcher.start()
        self.addCleanup(patcher.stop)


class WorkspaceTests(WorkspaceTestCase):
    def test_init_creates_structure_and_keeps_existing_files(self):
        first = workspace.init_channel("@bot_dev_py_ai")
        folder = self.root / "bot_dev_py_ai"
        self.assertEqual(sorted(first["created"]), ["AGENTS.md", "STYLE.md", "content-plan.md"])
        self.assertTrue((folder / "drafts").is_dir() and (folder / "published").is_dir())
        (folder / "STYLE.md").write_text("мои правила", encoding="utf-8")
        second = workspace.init_channel("@bot_dev_py_ai")
        self.assertEqual(second["created"], [])
        self.assertEqual((folder / "STYLE.md").read_text(encoding="utf-8"), "мои правила")

    def test_numeric_channel_gets_safe_folder_name(self):
        self.assertEqual(workspace.channel_dirname("-1001234567890"), "id-1001234567890")

    def test_draft_roundtrip_and_overwrite_protection(self):
        workspace.init_channel("@bot_dev_py_ai")
        workspace.save_draft("@bot_dev_py_ai", "fsm-intro", "<b>v1</b>")
        with self.assertRaises(TelegramError) as caught:
            workspace.save_draft("@bot_dev_py_ai", "fsm-intro", "<b>v2</b>")
        self.assertEqual(caught.exception.code, "DRAFT_EXISTS")
        self.assertEqual(workspace.read_draft("@bot_dev_py_ai", "fsm-intro"), "<b>v1</b>")
        workspace.save_draft("@bot_dev_py_ai", "fsm-intro", "<b>v2</b>", overwrite=True)
        self.assertEqual(workspace.read_draft("@bot_dev_py_ai", "fsm-intro"), "<b>v2</b>")
        self.assertEqual(workspace.list_drafts("@bot_dev_py_ai"), ["fsm-intro"])
        self.assertEqual(list((self.root / "bot_dev_py_ai" / "drafts").glob(".tg-*.tmp")), [])

    def test_unsafe_draft_names_are_rejected(self):
        workspace.init_channel("@bot_dev_py_ai")
        for name in ("../x", "a/b", "a\\b", "..", "", "C:evil", "UPPER", "x" * 61, "a.html"):
            with self.subTest(name=name), self.assertRaises(TelegramError):
                workspace.save_draft("@bot_dev_py_ai", name, "x")
        self.assertEqual(list(self.root.rglob("*.html")), [])

    def test_uninitialized_channel_is_reported(self):
        with self.assertRaises(TelegramError) as caught:
            workspace.list_drafts("@bot_dev_py_ai")
        self.assertEqual(caught.exception.code, "NOT_INITIALIZED")

    def test_relative_root_is_rejected(self):
        with patch.dict(os.environ, {"TELEGRAM_CHANNEL_ROOT": "relative/path"}):
            with self.assertRaises(TelegramError):
                workspace.workspace_root()


class ToolTests(WorkspaceTestCase):
    def call(self, tool, **kwargs):
        return json.loads(tool(**kwargs))

    def test_full_draft_flow_through_tools(self):
        self.call(server.telegram_init_channel)
        saved = self.call(server.telegram_save_draft, name="fsm-intro", text="<b>FSM</b> за минуту")
        self.assertEqual(saved["status"], "saved")
        self.assertEqual(saved["errors"], [])
        self.assertEqual(self.call(server.telegram_list_drafts)["drafts"], ["fsm-intro"])
        self.assertEqual(self.call(server.telegram_read_draft, name="fsm-intro")["text"], "<b>FSM</b> за минуту")
        checked = self.call(server.telegram_check_draft, name="fsm-intro")
        self.assertTrue(checked["ok"])
        self.assertEqual(checked["sha256"], saved["sha256"])

    def test_broken_draft_is_saved_but_reported(self):
        self.call(server.telegram_init_channel)
        saved = self.call(server.telegram_save_draft, name="broken", text="<h1>x</h1>")
        self.assertEqual(saved["status"], "saved")
        self.assertTrue(saved["errors"])

    def test_channel_outside_allowlist_is_rejected(self):
        result = self.call(server.telegram_init_channel, channel="@someone_else")
        self.assertEqual(result["code"], "CHANNEL_NOT_ALLOWED")
        self.assertFalse((self.root / "someone_else").exists())

    def test_channel_link_is_accepted(self):
        result = self.call(server.telegram_init_channel, channel="https://t.me/bot_dev_py_ai")
        self.assertEqual(result["folder"], str(self.root / "bot_dev_py_ai"))

    def test_several_channels_require_explicit_choice(self):
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_CHANNELS": "@a,@b"}):
            self.assertEqual(self.call(server.telegram_list_drafts)["code"], "CHANNEL_REQUIRED")

    def test_tool_schemas_keep_real_parameters(self):
        tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
        schema = tools["telegram_save_draft"]
        schema = getattr(schema, "input_schema", None) or schema.inputSchema
        self.assertEqual(set(schema["properties"]), {"name", "text", "channel", "overwrite"})
        self.assertEqual(set(schema["required"]), {"name", "text"})


if __name__ == "__main__":
    unittest.main()
