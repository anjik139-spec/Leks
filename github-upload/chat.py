import asyncio
import json
import os
import re
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import bot_templates
import brainkit
import core
import db
import gen
import intel
import providers
from config import (
    AUTO_GROUP,
    AUTO_PRIVATE,
    DATA,
    INTEL_CONCURRENCY,
    MAX_FILE_MB,
)

r = Router()
SEM = asyncio.Semaphore(INTEL_CONCURRENCY)
ALBUMS = {}
ME = {"username": None}
TASKS = {
    "describe": "🔍 Что это",
    "summary": "📝 Кратко",
    "errors": "⚠️ Ошибки",
    "extract": "📊 Данные",
    "translate": "🌍 Перевод",
    "qa": "❓ Вопрос",
}
INTENTS = [
    ("describe", r"опиши|что на|что это|посмотри|расскажи что|что изображено|разбери"),
    ("summary", r"кратко|пересказ|суммар|выжимк|итог|о чём|о чем|содержани"),
    ("errors", r"ошибк|проверь|вычитай|коррект|опечатк|замечани|вычитк"),
    ("extract", r"извлеки|данные|реквизит|вытащи|таблиц|сумм|дат[ыу]|поиск по"),
    ("translate", r"перевед|translate|на английск"),
    ("generate", r"сгенер|нарисуй|сделай фото|сделай картинк|преврати в|арт|стилиз"),
]


def parse_tasks(text):
    lowered = (text or "").lower()
    return [key for key, pattern in INTENTS if re.search(pattern, lowered)]


def kb(doc_id, kind):
    rows = [
        [
            InlineKeyboardButton(
                text=TASKS["describe"], callback_data=f"i:{doc_id}:describe"
            ),
            InlineKeyboardButton(
                text=TASKS["summary"], callback_data=f"i:{doc_id}:summary"
            ),
        ],
        [
            InlineKeyboardButton(
                text=TASKS["errors"], callback_data=f"i:{doc_id}:errors"
            ),
            InlineKeyboardButton(
                text=TASKS["extract"], callback_data=f"i:{doc_id}:extract"
            ),
        ],
        [
            InlineKeyboardButton(text="🎨 Фото по этому", callback_data=f"g:{doc_id}"),
            InlineKeyboardButton(text="❓ Спросить", callback_data=f"q:{doc_id}"),
        ],
        [
            InlineKeyboardButton(text="📄 Отчёт DOCX/PDF", callback_data=f"r:{doc_id}"),
            InlineKeyboardButton(
                text="🌍 Перевод", callback_data=f"i:{doc_id}:translate"
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def is_group(m):
    return m.chat.type in ("group", "supergroup")


async def auto_on(m):
    current = db.ctx(m.chat.id)
    if current["auto"] >= 0:
        return bool(current["auto"])
    return AUTO_GROUP if await is_group(m) else AUTO_PRIVATE


async def mentioned(m, bot):
    if not await is_group(m):
        return True
    if not ME["username"]:
        ME["username"] = (await bot.me()).username
    text = m.text or m.caption or ""
    if f"@{ME['username']}" in text:
        return True
    if (
        m.reply_to_message
        and m.reply_to_message.from_user
        and m.reply_to_message.from_user.id == bot.id
    ):
        return True
    for entity in (m.entities or []) + (m.caption_entities or []):
        if entity.type == "mention" and text[
            entity.offset : entity.offset + entity.length
        ].lower() == f"@{ME['username'].lower()}":
            return True
        if entity.type == "text_mention" and entity.user and entity.user.id == bot.id:
            return True
    return False


async def send_long(m, text, markup=None):
    text = text.strip() or "Пусто"
    parts = [text[i : i + 3700] for i in range(0, len(text), 3700)]
    for index, part in enumerate(parts):
        await m.answer(
            part,
            reply_markup=markup if index == len(parts) - 1 else None,
            disable_web_page_preview=True,
        )


def load_doc(doc_id):
    row = db.doc_get(doc_id)
    if not row:
        return None
    out = {
        "kind": row["kind"],
        "text": row["text"],
        "meta": json.loads(row["meta"] or "{}"),
        "tables": [],
        "images": [],
        "pages": 0,
        "hash": row["id"],
        "warn": [],
    }
    path = os.path.join(DATA, "files", f"src_{doc_id}.bin")
    if os.path.exists(path):
        try:
            with open(path, "rb") as file:
                raw = file.read()
            details = intel.extract(row["name"], raw)
            out["images"] = details["images"]
            out["tables"] = details["tables"]
            out["pages"] = details["pages"]
        except Exception:
            pass
    return out


async def do_tasks(m, doc_id, tasks, question=""):
    document = load_doc(doc_id)
    if not document:
        await m.answer("Документ не найден в контексте. Пришли файл заново.")
        return
    progress = await m.answer(
        "🔍 Разбираю: " + ", ".join(TASKS.get(task, task) for task in tasks) + "…"
    )
    async with SEM:
        result = await asyncio.to_thread(
            intel.run,
            document,
            tasks,
            question,
            brainkit.tier_for(m.from_user.id),
            m.from_user.id,
        )
    head = (
        f"📎 {document['meta'].get('name', 'файл')} · "
        f"{document['kind'].upper()}"
        + (f" · {document['pages']} стр." if document["pages"] else "")
    )
    body = [head]
    for task in tasks:
        if result.get(task):
            body.append(f"\n{TASKS.get(task, task)}\n{result[task]}")
    if result.get("_meta"):
        body.append("\n" + brainkit.footer(result["_meta"]))
    await progress.delete()
    await send_long(m, "\n".join(body), kb(doc_id, document["kind"]))
    if "generate" in tasks:
        await generate_from(m, doc_id)


async def generate_from(m, doc_id):
    document = load_doc(doc_id)
    if not document:
        return
    description = (
        intel.vision_ask(
            document["images"],
            "Составь промпт для генерации похожего изображения: объект, композиция, свет, стиль. До 45 слов, по-русски.",
        )
        if document["images"]
        else None
    )
    prompt = description or (
        document["text"][:200] if document["text"].strip() else "Арт по мотивам документа"
    )
    params = {"prompt": prompt, "style": "Кино", "aspect": "4:5"}
    if document["images"]:
        name = f"ref_{m.from_user.id}_{db.now()}.png"
        gen.save(name, document["images"][0])
        params["ref"] = name
        params["strength"] = 0.45
    try:
        core.submit(m.from_user.id, "photo", params)
        await m.answer(
            f"🎨 Генерация запущена по промпту:\n«{prompt}»\nРезультат придёт сюда 👻"
        )
    except core.Err as exc:
        await m.answer("Не запустилось: " + exc.code)


async def intake(m, bot, name, data, caption):
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        await m.answer(f"Файл больше {MAX_FILE_MB} МБ — пришли поменьше или текстом.")
        return
    extracted = await asyncio.to_thread(intel.extract, name, data)
    if extracted["kind"] == "csv":
        first_line = extracted["text"].splitlines()[0].lower() if extracted["text"] else ""
        if "org" in first_line and ("fio" in first_line or "text" in first_line):
            try:
                job = core.submit(
                    m.from_user.id,
                    "batch",
                    {"tpl": "zayavlenie", "csv": extracted["text"]},
                )
                await m.answer(
                    f"📄 CSV распознан как batch: запущено создание документов.\n"
                    f"Задача: {job['job']}"
                )
                return
            except core.Err as exc:
                await m.answer("Batch не запустился: " + exc.code)
                return
    doc_id = "d" + extracted["hash"][:10] + str(db.now() % 10000)
    db.doc_put(
        {
            "id": doc_id,
            "chat_id": m.chat.id,
            "uid": m.from_user.id,
            "name": name,
            "kind": extracted["kind"],
            "text": extracted["text"],
            "meta": extracted["meta"],
            "ts": db.now(),
        }
    )
    gen.save(f"src_{doc_id}.bin", data)
    db.ctx_set(m.chat.id, last_doc=doc_id, pending=0)
    db.ev(m.from_user.id, "intake_" + extracted["kind"])
    tasks = [task for task in parse_tasks(caption) if task != "generate"]
    want_generate = "generate" in parse_tasks(caption)
    if not tasks and await auto_on(m):
        tasks = ["summary", "errors"] if extracted["text"].strip() else ["describe"]
    if not tasks:
        info = (
            f"📎 Принял: {name} · {extracted['kind'].upper()}"
            + (f" · {extracted['pages']} стр." if extracted["pages"] else "")
        )
        if extracted["warn"]:
            info += "\n⚠️ " + "; ".join(extracted["warn"][:2])
        info += "\nВыбери, что сделать 👇"
        await m.answer(info, reply_markup=kb(doc_id, extracted["kind"]))
        return
    await do_tasks(m, doc_id, tasks)
    if want_generate:
        await generate_from(m, doc_id)


@r.message(Command("auto"))
async def auto_cmd(m: Message, command: CommandObject, bot: Bot):
    if await is_group(m):
        member = await bot.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ("administrator", "creator"):
            await m.answer("Менять авто-режим может только админ группы.")
            return
    argument = (command.args or "").strip().lower()
    if argument in ("on", "вкл"):
        db.ctx_set(m.chat.id, auto=1)
        await m.answer("⚡ Авто-разбор включён: кидай файл — сразу разберу.")
    elif argument in ("off", "выкл"):
        db.ctx_set(m.chat.id, auto=0)
        await m.answer("Авто-разбор выключен. Жду команду или @упоминание.")
    else:
        state = "вкл" if await auto_on(m) else "выкл"
        await m.answer(f"Авто-режим: {state}\n/auto on · /auto off")


@r.message(Command("context"))
async def ctx_cmd(m: Message):
    documents = db.docs_of(m.chat.id, 5)
    if not documents:
        await m.answer("Контекст пуст — пришли файл или фото.")
        return
    await m.answer(
        "🧠 В контексте чата:\n"
        + "\n".join(
            f"• {d['name']} ({d['kind']}, "
            f"{time.strftime('%d.%m %H:%M', time.localtime(d['ts']))})"
            for d in documents
        )
    )


@r.message(Command("clear"))
async def clear_cmd(m: Message):
    db.ctx_set(m.chat.id, last_doc="", pending=0)
    await m.answer("🧹 Контекст чата очищен. Сами файлы остаются в истории.")


@r.message(Command("ask"))
async def ask_cmd(m: Message, command: CommandObject):
    current = db.ctx(m.chat.id)
    if not current["last_doc"]:
        await m.answer("Сначала пришли документ или фото.")
        return
    question = (command.args or "").strip()
    if not question:
        await m.answer("Напиши вопрос: /ask какой срок оплаты?")
        return
    await do_tasks(m, current["last_doc"], ["qa"], question)


@r.message(Command("summary"))
async def s_cmd(m: Message):
    current = db.ctx(m.chat.id)
    if current["last_doc"]:
        await do_tasks(m, current["last_doc"], ["summary"])
    else:
        await m.answer("Пришли файл — сделаю пересказ.")


@r.message(Command("errors"))
async def e_cmd(m: Message):
    current = db.ctx(m.chat.id)
    if current["last_doc"]:
        await do_tasks(m, current["last_doc"], ["errors"])
    else:
        await m.answer("Пришли файл — проверю на ошибки.")


@r.message(Command("describe"))
async def d_cmd(m: Message):
    current = db.ctx(m.chat.id)
    if current["last_doc"]:
        await do_tasks(m, current["last_doc"], ["describe"])
    else:
        await m.answer("Пришли фото или файл.")


@r.message(Command("report"))
async def rep_cmd(m: Message):
    current = db.ctx(m.chat.id)
    if current["last_doc"]:
        await make_report(m, current["last_doc"])
    else:
        await m.answer("Нет документа для отчёта.")


async def make_report(m, doc_id):
    document = load_doc(doc_id)
    if not document:
        await m.answer("Документ не найден.")
        return
    progress = await m.answer("📄 Собираю отчёт…")
    async with SEM:
        result = await asyncio.to_thread(
            intel.run,
            document,
            ["describe", "summary", "errors", "extract"],
            "",
            brainkit.tier_for(m.from_user.id),
            m.from_user.id,
        )
        base = os.path.join(DATA, "files", "rep_" + doc_id)
        docx_path, pdf_path = await asyncio.to_thread(
            intel.report, document, result, base
        )
    await progress.delete()
    with open(docx_path, "rb") as file:
        docx_data = file.read()
    with open(pdf_path, "rb") as file:
        pdf_data = file.read()
    await m.answer_document(
        BufferedInputFile(docx_data, filename="razbor.docx"),
        caption="📄 Отчёт DOCX",
    )
    await m.answer_document(
        BufferedInputFile(pdf_data, filename="razbor.pdf"),
        caption="📄 Отчёт PDF",
    )


@r.callback_query(F.data.startswith("i:"))
async def cb_task(c: CallbackQuery):
    _, doc_id, task = c.data.split(":", 2)
    await c.answer()
    await do_tasks(c.message, doc_id, [task])


@r.callback_query(F.data.startswith("g:"))
async def cb_gen(c: CallbackQuery):
    await c.answer("Запускаю генерацию 🎨")
    await generate_from(c.message, c.data.split(":")[1])


@r.callback_query(F.data.startswith("r:"))
async def cb_rep(c: CallbackQuery):
    await c.answer("Собираю отчёт 📄")
    await make_report(c.message, c.data.split(":")[1])


@r.callback_query(F.data.startswith("q:"))
async def cb_q(c: CallbackQuery):
    db.ctx_set(c.message.chat.id, last_doc=c.data.split(":")[1], pending=1)
    await c.answer()
    await c.message.answer(
        "❓ Задай вопрос по документу следующим сообщением. Например: "
        "«какой срок оплаты?» или «найди противоречия в пунктах 3 и 5»."
    )


@r.message(F.photo | F.document)
async def on_file(m: Message, bot: Bot):
    if await is_group(m) and not await auto_on(m) and not await mentioned(m, bot):
        return
    if m.document:
        name = m.document.file_name or "file.bin"
        if (m.document.file_size or 0) > MAX_FILE_MB * 1024 * 1024:
            await m.answer(f"Файл больше {MAX_FILE_MB} МБ.")
            return
        buffer = await bot.download(m.document)
        data = buffer.read()
    else:
        name = f"photo_{db.now()}.jpg"
        buffer = await bot.download(m.photo[-1])
        data = buffer.read()
    caption = m.caption or ""
    if m.media_group_id:
        group = ALBUMS.setdefault(
            m.media_group_id, {"items": [], "m": m, "cap": ""}
        )
        group["items"].append((name, data))
        group["cap"] += " " + caption
        await asyncio.sleep(1.4)
        if ALBUMS.get(m.media_group_id) is not group:
            return
        group = ALBUMS.pop(m.media_group_id, None)
        if not group:
            return
        merged = group["items"][0][1]
        await intake(
            group["m"],
            bot,
            f"album_{len(group['items'])}_files.jpg",
            merged,
            group["cap"],
        )
        return
    await intake(m, bot, name, data, caption)


@r.message(F.voice)
async def on_voice(m: Message, bot: Bot):
    if await is_group(m) and not await mentioned(m, bot) and not await auto_on(m):
        return
    buffer = await bot.download(m.voice)
    text = providers.stt(buffer.read())
    if not text:
        await m.answer("Голос не распознан: нужен LLM_API_KEY или faster-whisper.")
        return
    await m.answer(f"🎤 «{text}»")
    await handle_text(m, bot, text)


@r.message(F.text & ~F.text.startswith("/"))
async def on_text(m: Message, bot: Bot):
    if await is_group(m) and not await mentioned(m, bot) and not await auto_on(m):
        return
    await handle_text(m, bot, m.text)


async def maybe_voice(m, bot, text):
    from config import TTS_ENABLED, TTS_MAX_CHARS

    if not TTS_ENABLED or not db.user(m.from_user.id).get("voice_mode"):
        return
    t = text.strip()
    if not t or len(t) > TTS_MAX_CHARS:
        return
    path = os.path.join(
        DATA,
        "files",
        f"tts_{m.from_user.id}_{db.now()}.mp3",
    )
    ok = await asyncio.to_thread(providers.tts, t, path)
    if ok:
        try:
            await bot.send_voice(m.chat.id, FSInputFile(path))
        except Exception:
            pass
        finally:
            try:
                os.remove(path)
            except Exception:
                pass


async def handle_text(m, bot, text):
    import bot_templates, brainkit

    if bot_templates.WIZ.get((m.chat.id, m.from_user.id)):
        return
    current = db.ctx(m.chat.id)
    if current["pending"] and current["last_doc"]:
        db.ctx_set(m.chat.id, pending=0)
        await do_tasks(m, current["last_doc"], ["qa"], text)
        return
    tasks = parse_tasks(text)
    if tasks and current["last_doc"]:
        want_generate = "generate" in tasks
        selected = [task for task in tasks if task != "generate"] or ["summary"]
        await do_tasks(m, current["last_doc"], selected)
        if want_generate:
            await generate_from(m, current["last_doc"])
        return
    if tasks and "generate" in tasks:
        try:
            core.submit(
                m.from_user.id,
                "photo",
                {"prompt": text, "style": "Кино"},
            )
            await m.answer("🎨 Генерация запущена, результат придёт сюда.")
        except core.Err as exc:
            await m.answer("Ошибка: " + exc.code)
        return
    if current["last_doc"] and ("?" in text or len(text.split()) > 2):
        await do_tasks(m, current["last_doc"], ["qa"], text)
        return
    ctx_text = ""
    if current["last_doc"]:
        document = load_doc(current["last_doc"])
        ctx_text = (document or {}).get("text", "")
    result = await asyncio.to_thread(
        brainkit.ask,
        text,
        ctx_text,
        brainkit.tier_for(m.from_user.id),
        m.from_user.id,
    )
    await m.answer(
        result["answer"] + "\n\n" + brainkit.footer(result["meta"])
    )
    await maybe_voice(m, bot, result["answer"])
