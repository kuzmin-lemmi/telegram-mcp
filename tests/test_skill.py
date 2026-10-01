import re
import unittest
from pathlib import Path

from telegram_mcp import server

SKILL = Path(__file__).resolve().parent.parent / "skills" / "telegram-post" / "SKILL.md"


class SkillTests(unittest.TestCase):
    def test_frontmatter_has_name_and_description(self):
        text = SKILL.read_text(encoding="utf-8")
        match = re.match(r"---\nname: (\S+)\ndescription: (.+)\n---\n", text)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "telegram-post")

    def test_every_tool_named_in_the_skill_exists(self):
        import asyncio

        text = SKILL.read_text(encoding="utf-8")
        registered = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
        mentioned = {name for name in re.findall(r"`(telegram_[a-z_]+)`", text)}
        self.assertTrue(mentioned)
        self.assertFalse(mentioned - registered, mentioned - registered)


if __name__ == "__main__":
    unittest.main()
