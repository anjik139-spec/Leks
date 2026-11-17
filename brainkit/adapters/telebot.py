import threading

from .. import config as C, core, documents


def register(bot):
    def own(message):
        return core.allowed(message.from_user.id)

    def send_long(chat_id, text):
        for index in range(0, len(text), 3700):
            bot.send_message(chat_id, text[index : index + 3700])

    def answer(message, question):
        tier = core.tier_for(message.from_user.id)
        result = core.ask(
            question,
            core.context(message.chat.id),
            tier,
            message.from_user.id,
        )
        send_long(
            message.chat.id,
            result["answer"] + "\n\n" + core.footer(result["meta"]),
        )

    @bot.message_handler(commands=["model"])
    def model_cmd(message):
        if not own(message):
            return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.send_message(
                message.chat.id,
                "Текущий: "
                + core.tier_for(message.from_user.id).upper()
                + "\n/model basic|pro|max",
            )
            return
        ok, result = core.set_tier(
            message.from_user.id, parts[1].strip().lower()
        )
        bot.send_message(
            message.chat.id,
            f"🧠 Мозг: {result.upper()}" if ok else "⛔ " + result,
        )

    @bot.message_handler(commands=["brain"])
    def brain_cmd(message):
        if own(message):
            bot.send_message(
                message.chat.id,
                core.status(message.from_user.id),
                parse_mode="HTML",
            )

    @bot.message_handler(commands=["forget"])
    def forget_cmd(message):
        if own(message):
            core.forget(message.chat.id)
            bot.send_message(message.chat.id, "🧹 Контекст очищен.")

    @bot.message_handler(commands=["ask"])
    def ask_cmd(message):
        if not own(message):
            return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.send_message(message.chat.id, "Формат: /ask вопрос")
            return
        threading.Thread(
            target=answer,
            args=(message, parts[1]),
            daemon=True,
        ).start()

    @bot.message_handler(content_types=["document", "photo"])
    def on_file(message):
        if not own(message):
            return
        if message.document:
            if (message.document.file_size or 0) > C.MAX_FILE_MB * 1024 * 1024:
                bot.send_message(
                    message.chat.id, f"Файл больше {C.MAX_FILE_MB} МБ."
                )
                return
            name = message.document.file_name or "file.bin"
            data = bot.download_file(
                bot.get_file(message.document.file_id).file_path
            )
        else:
            name = f"photo_{message.message_id}.jpg"
            data = bot.download_file(
                bot.get_file(message.photo[-1].file_id).file_path
            )
        extracted = documents.extract(name, data)
        core.remember(message.chat.id, extracted["text"], name)
        head = (
            f"📎 {name} · {extracted['kind'].upper()}"
            + (
                f" · {extracted['pages']} стр."
                if extracted["pages"]
                else ""
            )
        )
        if extracted["warn"]:
            head += "\n⚠️ " + "; ".join(extracted["warn"][:2])
        bot.send_message(message.chat.id, head + "\nЗадай вопрос или /ask.")
        if C.AUTO and extracted["text"].strip():
            tier = core.tier_for(message.from_user.id)
            summary = core.task(
                "summary",
                extracted["text"],
                "",
                tier,
                message.from_user.id,
            )
            errors = core.task(
                "errors",
                extracted["text"],
                "",
                tier,
                message.from_user.id,
            )
            send_long(
                message.chat.id,
                "📝 Кратко\n"
                + summary["answer"]
                + "\n\n⚠️ Ошибки\n"
                + errors["answer"]
                + "\n\n"
                + core.footer(errors["meta"]),
            )

    @bot.message_handler(
        func=lambda message: message.text
        and not message.text.startswith("/")
        and own(message),
        content_types=["text"],
    )
    def on_text(message):
        threading.Thread(
            target=answer,
            args=(message, message.text),
            daemon=True,
        ).start()
