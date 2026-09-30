"""Проверка текста поста в формате Telegram HTML. Чистая логика, без сети."""

import hashlib
import html
import re
from html.parser import HTMLParser

MAX_TEXT = 4096
MAX_CAPTION = 1024
NEAR_LIMIT = 0.95

# Разрешённые теги Telegram Bot API (parse_mode=HTML) и их допустимые атрибуты.
ALLOWED_TAGS = {
    "b": set(), "strong": set(), "i": set(), "em": set(), "u": set(), "ins": set(),
    "s": set(), "strike": set(), "del": set(),
    "a": {"href"},
    "code": {"class"},
    "pre": set(),
    "blockquote": {"expandable"},
    "span": {"class"},
    "tg-spoiler": set(),
    "tg-emoji": {"emoji-id"},
}

BARE_AMPERSAND = re.compile(r"&(?!(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)")
MARKDOWN_HINTS = (
    (re.compile(r"\*\*[^*\n]+\*\*"), "**жирный** — Telegram-HTML не понимает Markdown, используйте <b>…</b>"),
    (re.compile(r"(?m)^#{1,6} \S"), "заголовок через # — в Telegram нет заголовков, используйте <b>…</b>"),
    (re.compile(r"```"), "блок кода через ``` — используйте <pre><code>…</code></pre>"),
    (re.compile(r"\[[^\]\n]+\]\(https?://[^)\s]+\)"), "ссылка [текст](url) — используйте <a href=\"url\">текст</a>"),
)


def content_hash(text):
    """Хэш текста поста. Перевод строк CRLF и пробелы по краям не считаются изменением."""
    normalized = text.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class _Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.errors = []
        self.warnings = []
        self.stack = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"Тег <{tag}> не поддерживается Telegram.")
            return
        for name, value in attrs:
            if name not in ALLOWED_TAGS[tag]:
                self.errors.append(f"Атрибут «{name}» у тега <{tag}> не поддерживается.")
            elif tag == "a" and name == "href":
                if not (value or "").startswith(("https://", "http://", "tg://")):
                    self.errors.append(f"Ссылка «{value}» должна начинаться с https://")
                elif value.startswith("http://"):
                    self.warnings.append(f"Ссылка «{value}» без шифрования (http).")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"Закрывающий тег </{tag}> не поддерживается.")
        elif not self.stack or self.stack[-1] != tag:
            self.errors.append(f"Тег </{tag}> закрыт не там, где открыт.")
        else:
            self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        self.errors.append(f"Тег <{tag}/> не может быть самозакрывающимся.")

    def handle_entityref(self, name):
        self.text.append(html.unescape(f"&{name};"))

    def handle_charref(self, name):
        self.text.append(html.unescape(f"&#{name};"))

    def handle_data(self, data):
        if "<" in data or ">" in data:
            self.errors.append("Символы < и > в тексте нужно писать как &lt; и &gt;.")
        self.text.append(data)


def check_post(text, has_image=False):
    """Проверка текста поста. Возвращает словарь с ошибками, предупреждениями, длиной и хэшем."""
    errors, warnings = [], []
    body = text.replace("\r\n", "\n").strip()
    if not body:
        errors.append("Пост пустой.")

    checker = _Checker()
    checker.feed(body)
    checker.close()
    errors += checker.errors
    warnings += checker.warnings
    for tag in checker.stack:
        errors.append(f"Тег <{tag}> не закрыт.")
    if BARE_AMPERSAND.search(body):
        errors.append("Одиночный & нужно писать как &amp;.")
    for pattern, hint in MARKDOWN_HINTS:
        if pattern.search(re.sub(r"<pre.*?</pre>", "", body, flags=re.S)):
            warnings.append("Похоже на Markdown: " + hint)

    visible = "".join(checker.text)
    length = len(visible)
    limit = MAX_CAPTION if has_image else MAX_TEXT
    if length > limit:
        errors.append(
            f"Текст длиннее лимита Telegram: {length} из {limit} символов"
            + (" (подпись к картинке)." if has_image else ".")
        )
    elif length > limit * NEAR_LIMIT:
        warnings.append(f"Текст почти на пределе: {length} из {limit} символов.")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "length": length,
        "limit": limit,
        "sha256": content_hash(body),
    }
