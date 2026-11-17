import argparse
import sys

from . import core, documents


def main():
    parser = argparse.ArgumentParser(
        description="Проверка мозга без Telegram"
    )
    parser.add_argument(
        "question",
        nargs="?",
        default="Что в этом документе? Кратко и с ошибками.",
    )
    parser.add_argument(
        "--file", help="путь к PDF/DOCX/XLSX/CSV/TXT/фото"
    )
    parser.add_argument(
        "--tier", default="max", choices=["basic", "pro", "max"]
    )
    parser.add_argument("--uid", type=int, default=0)
    args = parser.parse_args()
    context = ""
    if args.file:
        with open(args.file, "rb") as file:
            extracted = documents.extract(args.file, file.read())
        context = extracted["text"]
        print(
            f"[{extracted['kind']}] {extracted['pages']} стр., "
            f"{len(context)} символов. {extracted['warn']}"
        )
        if not context.strip():
            print("Текст не извлёкся — проверь зависимости/OCR.")
            sys.exit(1)
    result = core.ask(
        args.question,
        context,
        args.tier,
        args.uid,
    )
    print(
        "\n"
        + result["answer"]
        + "\n\n"
        + core.footer(result["meta"])
    )


if __name__ == "__main__":
    main()
