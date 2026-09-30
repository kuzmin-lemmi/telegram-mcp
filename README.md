# Telegram MCP

MCP-сервер, с помощью которого ИИ (OpenCode, Claude Desktop, Claude Code) готовит посты для Telegram-канала. Сначала пост показывается автору в личных сообщениях, и только после явного «да» уходит в канал. Материал для постов ИИ берёт из курсов через [Stepik MCP](https://github.com/kuzmin-lemmi/Stepik_mcp).

> **Статус: часть 1 из 5.** Пока есть только проверка связи. Просмотр, публикация и связка со Stepik появятся в следующих частях.

## План

| Часть | Содержание | Статус |
| :---: | --- | :---: |
| 1 | Каркас, подключение к Telegram, `telegram_check` | ✅ |
| 2 | Папка канала: черновики и проверка поста | ⏳ |
| 3 | Просмотр: бот присылает пост автору в личку | |
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

## Разработка

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check src tests
```
