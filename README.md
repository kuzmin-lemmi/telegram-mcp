# Telegram MCP

MCP-сервер, с помощью которого ИИ (OpenCode, Claude Desktop, Claude Code) готовит посты для Telegram-канала. Сначала пост показывается автору в личных сообщениях, и только после явного «да» уходит в канал. Материал для постов ИИ берёт из курсов через [Stepik MCP](https://github.com/kuzmin-lemmi/Stepik_mcp).

> **Статус: часть 2 из 5.** Можно проверять связь и вести черновики. Просмотр в личке, публикация и связка со Stepik появятся в следующих частях.

## План

| Часть | Содержание | Статус |
| :---: | --- | :---: |
| 1 | Каркас, подключение к Telegram, `telegram_check` | ✅ |
| 2 | Папка канала: черновики и проверка поста | ✅ |
| 3 | Просмотр: бот присылает пост автору в личку | ⏳ |
| 4 | Публикация и правка: список каналов, одобрение, запись `published/` | |
| 5 | Конфиги клиентов, инструкция для ИИ, связка со Stepik | |

## Установка

Нужен Python 3.12+.

```powershell
git clone https://github.com/kuzmin-lemmi/telegram-mcp.git
cd telegram-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## Настройка

| Переменная | Назначение |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather. **Никому не присылайте** |
| `TELEGRAM_ALLOWED_CHANNELS` | Каналы через запятую: `@bot_dev_py_ai`. Только в них сервер будет работать |
| `TELEGRAM_CHANNEL_ROOT` | Папка с каналами (абсолютный путь). По умолчанию `~/Channels`, то есть `C:\Users\<вы>\Channels` |

Бот должен быть администратором канала **только с правами «Публикация сообщений» и «Редактирование сообщений»**. Остальные права выключите: `telegram_check` предупредит, если они включены.

### OpenCode

```jsonc
"telegram": {
  "type": "local",
  "command": ["C:\\path\\to\\telegram-mcp\\.venv\\Scripts\\python.exe", "-m", "telegram_mcp"],
  "enabled": true,
  "environment": {
    "TELEGRAM_BOT_TOKEN": "<токен>",
    "TELEGRAM_ALLOWED_CHANNELS": "@bot_dev_py_ai"
  }
}
```

### Claude Desktop

```json
"telegram": {
  "command": "C:\\path\\to\\telegram-mcp\\.venv\\Scripts\\telegram-mcp.exe",
  "env": {
    "TELEGRAM_BOT_TOKEN": "<токен>",
    "TELEGRAM_ALLOWED_CHANNELS": "@bot_dev_py_ai"
  }
}
```

## Инструменты

| Инструмент | Что делает |
| --- | --- |
| `telegram_check` | Какой это бот, есть ли он в разрешённых каналах, с какими правами; предупреждает о лишних |
| `telegram_init_channel` | Создаёт папку канала: `drafts/`, `published/`, `AGENTS.md`, `STYLE.md`, `content-plan.md` |
| `telegram_save_draft` | Сохраняет черновик; существующий заменяется только с `overwrite=true` |
| `telegram_read_draft`, `telegram_list_drafts` | Читают черновик и список черновиков |
| `telegram_check_draft` | Проверяет теги, ссылки, длину (4096 символов, 1024 для подписи к картинке), следы Markdown; возвращает хэш текста |

Ничего из этого в канал не отправляет.

## Формат постов

Черновики пишутся в **Telegram-HTML**: `<b>`, `<i>`, `<u>`, `<s>`, `<code>`, `<pre>`, `<a href="https://…">`, `<blockquote>`, `<tg-spoiler>`. Символы `<`, `>` и `&` в тексте пишутся как `&lt;`, `&gt;`, `&amp;`. Markdown Telegram не понимает, `telegram_check_draft` предупредит, если найдёт его следы.

## Разработка

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check src tests
```
