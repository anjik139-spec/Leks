import asyncio

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .. import core

router = Router(name="brainkit")


def _own(m: Message):
    return core.allowed(m.from_user.id)


def _busy(m: Message) -> bool:
    """Мастер шаблонов или ожидание вопроса — не вмешиваемся."""
    try:
        import bot_templates

        if bot_templates.WIZ.get((m.chat.id, m.from_user.id)):
            return True
    except Exception:
        pass
    try:
        import db

        if db.ctx(m.chat.id).get("pending"):
            return True
    except Exception:
        pass
    return False


@router.message(Command("model"))
async def model_cmd(m: Message, command: CommandObject):
    if not _own(m):
        return
    arg = (command.args or "").strip().lower()
    if not arg:
        await m.answer(
            "Текущий: "
            + core.tier_for(m.from_user.id).upper()
            + "\n/model basic — быстро и дёшево"
            "\n/model pro — план + самокритика"
            "\n/model max — агент + best-of-2 + проверка чисел"
        )
        return
    ok, msg = core.set_tier(m.from_user.id, arg)
    await m.answer(f"🧠 Мозг: {msg.upper()}" if ok else "⛔ " + msg)


@router.message(Command("brain"))
async def brain_cmd(m: Message):
    if not _own(m):
        return
    await m.answer(core.status(m.from_user.id), parse_mode="HTML")


@router.message(Command("forget"))
async def forget_cmd(m: Message):
    if not _own(m):
        return
    core.forget(m.chat.id)
    try:
        import db

        db.ctx_set(m.chat.id, last_doc="", pending=0)
    except Exception:
        pass
    await m.answer("🧹 Контекст очищен: и память мозга, и активный документ чата.")


@router.message(Command("ask"))
async def ask_cmd(m: Message, command: CommandObject):
    if not _own(m) or _busy(m):
        return
    q = (command.args or "").strip()
    if not q:
        await m.answer("Формат: /ask какой срок оплаты?")
        return
    ctx = core.context(m.chat.id)
    if not ctx:
        try:
            import chat as chat_mod

            c = __import__("db").ctx(m.chat.id)
            if c.get("last_doc"):
                o = chat_mod.load_doc(c["last_doc"])
                ctx = (o or {}).get("text", "")
        except Exception:
            pass
    if not ctx.strip():
        await m.answer(
            "🧹 Контекст пуст: пришли документ/фото или сначала разбери файл. "
            "Без источника отвечать не буду."
        )
        return
    tier = core.tier_for(m.from_user.id)
    prog = await m.answer(f"🧠 Думаю на {tier.upper()}…")
    r = await asyncio.to_thread(core.ask, q, ctx, tier, m.from_user.id)
    try:
        await prog.delete()
    except Exception:
        pass
    text = r["answer"] + "\n\n" + core.footer(r["meta"])
    for i in range(0, len(text), 3700):
        await m.answer(text[i : i + 3700])
