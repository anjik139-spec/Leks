import asyncio

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import templates as T

r = Router()
WIZ = {}
CATS = [
    "Кадры",
    "Договоры",
    "Финансы",
    "Продажи",
    "Обращения",
    "Личное",
    "Проекты",
    "Склад",
    "Данные",
]
ICON = {"doc": "📄", "sheet": "📊", "file": "🗂"}


def all_items():
    return T.catalog()


def item(key):
    return next((x for x in all_items() if x["key"] == key), None)


def kb_cats():
    rows, line = [], []
    for i, cat in enumerate(CATS, 1):
        count = sum(1 for x in all_items() if x["cat"] == cat)
        line.append(
            InlineKeyboardButton(
                text=f"{cat} ({count})", callback_data=f"tc:{cat}"
            )
        )
        if i % 2 == 0:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    rows.append(
        [
            InlineKeyboardButton(text="📄 Документы", callback_data="tt:doc"),
            InlineKeyboardButton(text="📊 Таблицы", callback_data="tt:sheet"),
            InlineKeyboardButton(text="🗂 Файлы", callback_data="tt:file"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_list(items, back="tb"):
    rows = [
        [
            InlineKeyboardButton(
                text=f"{ICON[x['type']]} {x['title']}",
                callback_data=f"ti:{x['key']}",
            )
        ]
        for x in items[:24]
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Категории", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_item(x):
    rows = []
    if x["type"] == "doc":
        rows.append(
            [
                InlineKeyboardButton(
                    text="📄 Образец DOCX",
                    callback_data=f"tf:{x['key']}:docx:0",
                ),
                InlineKeyboardButton(
                    text="📑 Образец PDF",
                    callback_data=f"tf:{x['key']}:pdf:0",
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="📝 Пустой бланк",
                    callback_data=f"tf:{x['key']}:docx:1",
                ),
                InlineKeyboardButton(
                    text="✍️ Заполнить", callback_data=f"tw:{x['key']}"
                ),
            ]
        )
    elif x["type"] == "sheet":
        rows.append(
            [
                InlineKeyboardButton(
                    text="📊 Скачать XLSX",
                    callback_data=f"tf:{x['key']}:xlsx:0",
                ),
                InlineKeyboardButton(
                    text="📄 CSV", callback_data=f"tf:{x['key']}:csv:0"
                ),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⬇️ Скачать .{x['formats'][0]}",
                    callback_data=f"tf:{x['key']}:{x['formats'][0]}:0",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tc:{x['cat']}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card(x):
    text = (
        f"{ICON[x['type']]} <b>{x['title']}</b>\n{x['desc']}\n"
        f"Категория: {x['cat']}\n"
    )
    if x["type"] == "doc":
        text += "\nПоля: " + ", ".join(f["label"] for f in x["fields"])
        text += (
            "\n\n<i>Пример заполнен реальными данными — можно скачать как есть "
            "или сделать пустой бланк.</i>"
        )
    elif x["type"] == "sheet":
        text += f"\nСтолбцы: {', '.join(x['preview_rows'][0])}"
        if x.get("formula_cols"):
            text += (
                f"\nФормулы в столбцах: {', '.join(x['formula_cols'])} · "
                "автофильтр · закрепление шапки"
            )
    text += "\n\n⚠️ " + T.DISCLAIMER
    return text


@r.message(Command("templates", "samples"))
async def tpl(m: Message):
    await m.answer(
        f"📚 <b>Библиотека образцов</b>\n"
        f"{len(T.DOCS)} документов · {len(T.SHEETS)} таблиц · "
        f"{len(T.FILES)} файлов\n\nВыбери категорию или тип:",
        reply_markup=kb_cats(),
    )


@r.message(Command("sample"))
async def sample(m: Message, command: CommandObject):
    key = (command.args or "").strip()
    if not key:
        await m.answer("Формат: /sample otpusk\nСписок: /templates")
        return
    await send_key(m, key, None, False)


@r.message(Command("blank"))
async def blank(m: Message, command: CommandObject):
    key = (command.args or "").strip()
    if key in T.DOCS:
        await send_key(m, key, "docx", True)
    else:
        await m.answer("Пустой бланк есть только у документов. /templates")


async def send_key(m, key, fmt, blank):
    item_data = item(key)
    if not item_data:
        await m.answer("Не нашёл такой шаблон. /templates")
        return
    fmt = fmt or item_data["formats"][0]
    try:
        name, data, mime = await asyncio.to_thread(
            T.render, key, None, blank, fmt
        )
    except Exception as exc:
        await m.answer("Не собралось: " + str(exc)[:150])
        return
    caption = (
        f"{ICON[item_data['type']]} {item_data['title']}"
        + (" · пустой бланк" if blank else " · заполненный образец")
    )
    if item_data["type"] == "sheet":
        caption += "\nФормулы, автофильтр и оформление уже настроены."
    await m.answer_document(
        BufferedInputFile(data, filename=name), caption=caption
    )


@r.callback_query(F.data == "tb")
async def cb_back(c: CallbackQuery):
    await c.answer()
    await c.message.edit_text(
        "📚 <b>Библиотека образцов</b>\nВыбери категорию или тип:",
        reply_markup=kb_cats(),
    )


@r.callback_query(F.data.startswith("tc:"))
async def cb_cat(c: CallbackQuery):
    cat = c.data.split(":", 1)[1]
    items = [x for x in all_items() if x["cat"] == cat]
    await c.answer()
    await c.message.edit_text(
        f"📚 <b>{cat}</b> · {len(items)} шт.", reply_markup=kb_list(items)
    )


@r.callback_query(F.data.startswith("tt:"))
async def cb_type(c: CallbackQuery):
    kind = c.data.split(":", 1)[1]
    items = [x for x in all_items() if x["type"] == kind]
    names = {"doc": "Документы", "sheet": "Таблицы", "file": "Файлы"}
    await c.answer()
    await c.message.edit_text(
        f"{ICON[kind]} <b>{names[kind]}</b> · {len(items)} шт.",
        reply_markup=kb_list(items),
    )


@r.callback_query(F.data.startswith("ti:"))
async def cb_item(c: CallbackQuery):
    item_data = item(c.data.split(":", 1)[1])
    if not item_data:
        await c.answer("Не найдено", show_alert=True)
        return
    await c.answer()
    await c.message.edit_text(
        card(item_data), reply_markup=kb_item(item_data)
    )


@r.callback_query(F.data.startswith("tf:"))
async def cb_file(c: CallbackQuery):
    _, key, fmt, blank = c.data.split(":")
    await c.answer("Готовлю файл…")
    await send_key(c.message, key, fmt, blank == "1")


@r.callback_query(F.data.startswith("tw:"))
async def cb_wiz(c: CallbackQuery):
    key = c.data.split(":", 1)[1]
    item_data = item(key)
    if not item_data or not item_data["fields"]:
        await c.answer("Нет полей", show_alert=True)
        return
    WIZ[(c.message.chat.id, c.from_user.id)] = {
        "key": key,
        "i": 0,
        "data": {},
    }
    await c.answer()
    await c.message.answer(
        f"✍️ Заполняем «{item_data['title']}». Отвечай по очереди, /cancel — отмена.\n\n"
        f"<b>1/{len(item_data['fields'])}. {item_data['fields'][0]['label']}</b>\n"
        f"Пример: <code>{item_data['fields'][0]['sample']}</code>"
    )


@r.message(Command("cancel"))
async def wiz_cancel(m: Message):
    if WIZ.pop((m.chat.id, m.from_user.id), None):
        await m.answer("Отменено.")


@r.message(F.text & ~F.text.startswith("/"))
async def wiz_step(m: Message):
    state = WIZ.get((m.chat.id, m.from_user.id))
    if not state:
        return
    item_data = item(state["key"])
    field = item_data["fields"][state["i"]]
    state["data"][field["id"]] = m.text.strip()
    state["i"] += 1
    if state["i"] < len(item_data["fields"]):
        next_field = item_data["fields"][state["i"]]
        await m.answer(
            f"<b>{state['i'] + 1}/{len(item_data['fields'])}. "
            f"{next_field['label']}</b>\n"
            f"Пример: <code>{next_field['sample']}</code>"
        )
        return
    WIZ.pop((m.chat.id, m.from_user.id), None)
    name, data, mime = await asyncio.to_thread(
        T.render, state["key"], state["data"], False, "docx"
    )
    await m.answer_document(
        BufferedInputFile(data, filename=name),
        caption=f"📄 {item_data['title']} — заполнено вашими данными",
    )
    _, pdf, _ = await asyncio.to_thread(
        T.render, state["key"], state["data"], False, "pdf"
    )
    await m.answer_document(
        BufferedInputFile(pdf, filename=state["key"] + ".pdf"),
        caption="📑 Тот же документ в PDF",
    )
