import importlib.util
import os
import re
import shutil
import sys
import time
import zipfile

ROOT = os.getcwd()
SKIP = {".git", "venv", ".venv", "__pycache__", "node_modules", "brain_data", "data"}
SECRET_FILES = {".env", ".env.lex", ".env.brain"}


def backup():
    name = f"backup_before_brain_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for filename in files:
                if filename in SECRET_FILES:
                    continue
                if filename.endswith(
                    (".py", ".txt", ".yml", ".yaml", ".toml", "Dockerfile")
                ):
                    path = os.path.join(root, filename)
                    archive.write(path, os.path.relpath(path, ROOT))
    print("✅ Бэкап:", name)
    return name


def detect():
    frameworks = set()
    mains = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(root, filename)
            try:
                with open(path, encoding="utf-8", errors="ignore") as file:
                    source = file.read()
            except Exception:
                continue
            if re.search(r"from\s+aiogram|import\s+aiogram", source):
                frameworks.add("aiogram")
            if re.search(r"import\s+telebot|from\s+telebot", source):
                frameworks.add("telebot")
            if re.search(
                r"Dispatcher\(|start_polling\(|infinity_polling\(|\.polling\(",
                source,
            ):
                mains.append(os.path.relpath(path, ROOT))
    return frameworks, mains


def deps():
    need = {
        "fitz": "PDF",
        "docx": "DOCX",
        "openpyxl": "XLSX",
        "PIL": "фото",
        "pytesseract": "OCR",
    }
    have, missing = [], []
    for module, label in need.items():
        target = have if importlib.util.find_spec(module) else missing
        target.append(f"{label} ({module})")
    print("📦 Есть:", ", ".join(have) or "только stdlib")
    print("📦 Нет (необязательно):", ", ".join(missing) or "—")
    print(
        "🔤 tesseract:",
        "найден" if shutil.which("tesseract") else "не найден (OCR сканов не будет)",
    )


def env():
    if os.path.exists(".env.brain"):
        print("ℹ️ .env.brain уже есть")
        return
    template = """OWNER_IDS=ЗАМЕНИ_НА_СВОЙ_ID
BRAIN_ALLOW_OTHERS=0
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
MODEL_BASIC=gpt-4o-mini
MODEL_PRO=gpt-4o
MODEL_MAX=o3
REASONING=high
DAILY_BUDGET_USD=2
BRAIN_CACHE_DOCS=0
BRAIN_LOG_CONTENT=0
BRAIN_STORE_TEXT=0
BRAIN_CTX_TTL=7200
BRAIN_AUTO=1
BRAIN_MAX_FILE_MB=20
OCR_LANGS=rus+eng
"""
    with open(".env.brain", "w", encoding="utf-8") as file:
        file.write(template)
    print("✅ Создан .env.brain — впиши OWNER_IDS и ключ")


def main():
    print("=== Установка brainkit ===")
    backup_name = backup()
    frameworks, mains = detect()
    deps()
    env()
    print("\n🔍 Фреймворк:", ", ".join(frameworks) or "не определён")
    print("🔍 Точка запуска:", ", ".join(mains[:5]) or "не найдена")
    print("\n=== ВСТАВЬ ЭТО ===")
    if "aiogram" in frameworks:
        print(
            "from brainkit.adapters.aiogram3 import router as brain_router"
        )
        print("dp.include_router(brain_router)   # ДО общих обработчиков текста")
    if "telebot" in frameworks:
        print(
            "from brainkit.adapters.telebot import register as brain_register"
        )
        print("brain_register(bot)   # ДО catch-all обработчиков")
    print("\nЗагрузка .env.brain перед импортом brainkit:")
    print("from dotenv import load_dotenv; load_dotenv('.env.brain')")
    print(
        "\nПроверка без Telegram:  python -m brainkit.cli --file договор.pdf --tier max"
    )
    print(
        "Откат: удали 2 строки выше, папку brainkit/ и восстанови",
        backup_name,
    )


if __name__ == "__main__":
    main()
