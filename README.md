# Telegram MCP

MCP-сервер, с помощью которого ИИ (OpenCode, Claude Desktop, Claude Code) готовит посты для Telegram-канала. Сначала пост показывается автору в личных сообщениях, и только после явного «да» уходит в канал. Материал для постов ИИ берёт из курсов через [Stepik MCP](https://github.com/kuzmin-lemmi/Stepik_mcp).

> **Статус: части 1–5 готовы.** Остаётся проверка на настоящем боте и канале.

## План

| Часть | Содержание | Статус |
| :---: | --- | :---: |
| 1 | Каркас, подключение к Telegram, `telegram_check` | ✅ |
| 2 | Папка канала: черновики и проверка поста | ✅ |
| 3 | Просмотр: бот присылает пост автору в личку | ✅ |
| 4 | Публикация и правка: список каналов, одобрение, запись `published/` | ✅ |
| 5 | Токен в защищённом хранилище, конфиги клиентов, инструкция для ИИ, связка со Stepik | ✅ |

## Установка

Нужен Python 3.12+.

```powershell
git clone https://github.com/kuzmin-lemmi/telegram-mcp.git
cd telegram-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## Токен бота

Токен от @BotFather сохраняется **один раз** в защищённом хранилище системы (в Windows это Диспетчер учётных данных). Ни в чат, ни в конфиги он не попадает.

```powershell
.\.venv\Scripts\telegram-mcp-setup.exe
```

Команда спросит токен (символы при вводе не видны), проверит его у Telegram и покажет только имя бота. `telegram-mcp-setup --status` покажет, сохранён ли токен, `--delete` удалит его. Если токен когда-либо попал в чат, перевыпустите его у @BotFather командой `/revoke`.

Запасной вариант: переменная окружения `TELEGRAM_BOT_TOKEN` (главнее хранилища), но тогда токен лежит в конфиге открытым текстом.

## Настройка

| Переменная | Назначение |
| --- | --- |
| `TELEGRAM_ALLOWED_CHANNELS` | Каналы через запятую: `@bot_dev_py_ai`. Только в них сервер будет работать |
| `TELEGRAM_OWNER_ID` | Необязательно. Номер вашего чата, если не хотите привязывать через `telegram_set_owner` |
| `TELEGRAM_CHANNEL_ROOT` | Папка с каналами (абсолютный путь). По умолчанию `~/Channels`, то есть `C:\Users\<вы>\Channels` |
| `TELEGRAM_BOT_TOKEN` | Необязательно, см. выше |

Бот должен быть администратором канала **только с правами «Публикация сообщений» и «Редактирование сообщений»**. Остальные права выключите: `telegram_check` предупредит, если они включены.

## Подключение к клиентам

Готовые примеры лежат в [`examples/`](examples). Замените `C:\path\to\telegram-mcp` на свой путь и перезапустите клиент.

**OpenCode** (`~/.config/opencode/opencode.jsonc`): блок `mcp.telegram` из [`examples/opencode.jsonc`](examples/opencode.jsonc).

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`): блок `mcpServers.telegram` из [`examples/claude_desktop_config.json`](examples/claude_desktop_config.json).

**Claude Code:**

```powershell
claude mcp add telegram --scope user -e TELEGRAM_ALLOWED_CHANNELS=@bot_dev_py_ai -- C:\path\to\telegram-mcp\.venv\Scripts\telegram-mcp.exe
```

> Для `telegram_publish` и `telegram_edit_published` **не включайте автоматическое разрешение**: пусть клиент каждый раз спрашивает. Это ещё одна защита от случайной публикации.

### Инструкция для ИИ

[`skills/telegram-post/SKILL.md`](skills/telegram-post) учит ИИ порядку работы: черновик, проверка, показ, ваше «публикуй», публикация. Там же сценарии «пост из урока Stepik» и «пост из ошибок учеников» и составление `STYLE.md` по вашим прошлым постам. Скопируйте папку `telegram-post` в `~/.claude/skills/` (Claude Code) или в папку skills вашего OpenCode. Те же основные правила ИИ получает и без skill, через описание инструментов.

## Связка со Stepik

Два сервера не общаются друг с другом: их связывает ИИ, подключённый к обоим. Stepik MCP даёт уроки, комментарии и ошибки учеников, Telegram MCP показывает и публикует пост. Подробности и порядок шагов в skill выше.

## Инструменты

| Инструмент | Что делает |
| --- | --- |
| `telegram_check` | Какой это бот, есть ли он в разрешённых каналах, с какими правами; предупреждает о лишних |
| `telegram_init_channel` | Создаёт папку канала: `drafts/`, `published/`, `AGENTS.md`, `STYLE.md`, `content-plan.md` |
| `telegram_save_draft` | Сохраняет черновик; существующий заменяется только с `overwrite=true` |
| `telegram_read_draft`, `telegram_list_drafts` | Читают черновик и список черновиков |
| `telegram_check_draft` | Проверяет теги, ссылки, длину (4096 символов, 1024 для подписи к картинке), следы Markdown; возвращает хэш текста |
| `telegram_find_owner` | Показывает, кто нажимал `/start` у бота (нужно один раз) |
| `telegram_set_owner` | Запоминает получателя просмотров; принимает только того, кто писал боту |
| `telegram_preview` | Присылает черновик **только автору** в личку так, как он будет выглядеть в канале; запоминает хэш показанного текста |

Эти инструменты в канал ничего не отправляют. Отправляют только два следующих:

| Инструмент | Что делает |
| --- | --- |
| `telegram_publish` | **Публикует** пост в канал. Нужен `confirm_sha256` из ответа `telegram_preview` |
| `telegram_edit_published` | **Исправляет** уже вышедший пост; прежний текст сохраняется в `published/` |
| `telegram_list_published` | Список вышедших постов со ссылками |

### Когда публикация откажет

`telegram_publish` и `telegram_edit_published` ничего не отправят, если:

- канала нет в `TELEGRAM_ALLOWED_CHANNELS`;
- пост не прошёл проверку (`telegram_check_draft`);
- пост не показывали автору через `telegram_preview` (`NOT_PREVIEWED`);
- текст изменился после показа (`CHANGED_AFTER_PREVIEW`);
- `confirm_sha256` не совпал с хэшем текста (`BAD_CONFIRMATION`);
- у бота нет права публикации (`NO_POST_RIGHT`);
- для этого черновика уже есть запись о публикации (`ALREADY_PUBLISHED`): повторно тот же пост не уйдёт.

Запись в `published/<имя>.json` создаётся **до** отправки. Если процесс оборвётся в момент отправки, повторная попытка откажет и попросит проверить канал вручную, чтобы не выпустить пост дважды. **Удаления постов нет**: ни инструмента, ни права у бота.

Порядок работы: `save_draft` → `check_draft` → `preview` → ваш просмотр в Telegram → ваше «публикуй» в чате → `publish`.

### Как привязать просмотр (один раз)

1. Откройте бота в Telegram и нажмите **Start**.
2. Попросите ИИ: «найди владельца» (`telegram_find_owner`). Он покажет имя и username каждого, кто писал боту.
3. Подтвердите свой вариант: «это я» (`telegram_set_owner`).

Либо задайте номер своего чата настройкой `TELEGRAM_OWNER_ID`, она главнее сохранённого.

## Формат постов

Черновики пишутся в **Telegram-HTML**: `<b>`, `<i>`, `<u>`, `<s>`, `<code>`, `<pre>`, `<a href="https://…">`, `<blockquote>`, `<tg-spoiler>`. Символы `<`, `>` и `&` в тексте пишутся как `&lt;`, `&gt;`, `&amp;`. Markdown Telegram не понимает, `telegram_check_draft` предупредит, если найдёт его следы.

## Разработка

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check src tests
```
