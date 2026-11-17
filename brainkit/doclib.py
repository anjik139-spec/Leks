import collections
import csv
import hashlib
import io
import json
import math
import re
import shutil
import urllib.parse
import urllib.request

from . import config as C

MOD_RE = re.compile(
    "|".join(w.strip() for w in C.MODERATION.split(",") if w.strip()),
    re.I,
)


def _dec(b):
    for e in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode("utf-8", "ignore")


def ocr(img):
    if not shutil.which("tesseract"):
        return ""
    try:
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(
            Image.open(io.BytesIO(img)), lang=C.OCR_LANGS
        )
    except Exception:
        return ""


def extract(name, data):
    ext = (name.rsplit(".", 1)[-1] if "." in name else "").lower()
    o = {
        "name": name,
        "kind": "file",
        "text": "",
        "pages": 0,
        "meta": {"name": name, "size": len(data)},
        "tables": [],
        "images": [],
        "warn": [],
    }
    try:
        if ext in (
            "jpg",
            "jpeg",
            "png",
            "webp",
            "bmp",
            "tif",
            "tiff",
            "heic",
        ):
            from PIL import Image

            im = Image.open(io.BytesIO(data))
            o["kind"] = "image"
            o["meta"].update(
                width=im.width,
                height=im.height,
                format=im.format,
                mode=im.mode,
            )
            cols = sorted(
                im.convert("RGB").resize((32, 32)).getcolors(1024) or [],
                reverse=True,
            )[:4]
            o["meta"]["colors"] = ["#%02x%02x%02x" % c[1] for c in cols]
            o["images"] = [data]
            o["text"] = ocr(data)
            o["pages"] = 1
            if not o["text"].strip():
                o["warn"].append(
                    "Текст не распознан (нет tesseract или текста на фото)"
                )
        elif ext == "pdf":
            import fitz

            d = fitz.open(stream=data, filetype="pdf")
            o["kind"] = "pdf"
            o["pages"] = len(d)
            parts = []
            for i, pg in enumerate(d):
                t = pg.get_text()
                if len(t.strip()) < 40 and i < C.MAX_OCR_PAGES:
                    ib = pg.get_pixmap(dpi=170).tobytes("png")
                    if len(o["images"]) < 3:
                        o["images"].append(ib)
                    t = ocr(ib) or t
                parts.append(f"[Стр. {i+1}]\n{t}")
            o["text"] = "\n".join(parts)
            o["meta"]["scanned"] = len(o["text"].strip()) < 100
        elif ext == "docx":
            from docx import Document

            doc = Document(io.BytesIO(data))
            o["kind"] = "docx"
            o["text"] = "\n".join(p.text for p in doc.paragraphs)
            for tb in doc.tables:
                rows = [[c.text.strip() for c in r.cells] for r in tb.rows]
                o["tables"].append(rows)
                o["text"] += "\n" + "\n".join(
                    " | ".join(r) for r in rows
                )
        elif ext in ("xlsx", "xlsm"):
            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(data), data_only=True)
            o["kind"] = "xlsx"
            for ws in wb.worksheets:
                rows = [
                    [("" if c is None else str(c)) for c in r]
                    for r in ws.iter_rows(values_only=True)
                ]
                rows = [r for r in rows if any(x.strip() for x in r)][:400]
                o["tables"].append(rows)
                o["text"] += f"\n[Лист {ws.title}]\n" + "\n".join(
                    " | ".join(r) for r in rows
                )
        elif ext == "csv":
            rows = list(csv.reader(io.StringIO(_dec(data))))[:400]
            o["kind"] = "csv"
            o["tables"] = [rows]
            o["text"] = "\n".join(" | ".join(r) for r in rows)
        elif ext in ("txt", "md", "json", "log", "xml", "html"):
            o["kind"] = "text"
            o["text"] = _dec(data)
            if ext in ("html", "xml"):
                o["text"] = re.sub(r"<[^>]+>", " ", o["text"])
        elif ext == "rtf":
            try:
                from striprtf.striprtf import rtf_to_text

                o["text"] = rtf_to_text(_dec(data))
            except Exception:
                o["text"] = re.sub(
                    r"\\[a-z]+-?\d* ?|[{}]", "", _dec(data)
                )
            o["kind"] = "rtf"
        elif ext == "pptx":
            from pptx import Presentation

            pr = Presentation(io.BytesIO(data))
            o["kind"] = "pptx"
            o["pages"] = len(pr.slides)
            o["text"] = "\n".join(
                f"[Слайд {i+1}]\n"
                + "\n".join(
                    s.text_frame.text
                    for s in sl.shapes
                    if s.has_text_frame
                )
                for i, sl in enumerate(pr.slides)
            )
        elif ext == "zip":
            import zipfile

            z = zipfile.ZipFile(io.BytesIO(data))
            o["kind"] = "zip"
            o["text"] = "Содержимое архива:\n" + "\n".join(
                z.namelist()[:200]
            )
        else:
            o["warn"].append(
                "Формат не поддержан: " + (ext or "без расширения")
            )
    except ImportError as e:
        o["warn"].append("Не хватает библиотеки: " + str(e)[:90])
    except Exception as e:
        o["warn"].append("Ошибка чтения: " + str(e)[:120])
    o["text"] = o["text"][: C.CTX_LIMIT]
    o["hash"] = hashlib.sha256(data).hexdigest()[:16]
    return o


def chunks(text, size=1400):
    parts = [p for p in re.split(r"\n{2,}", text) if p.strip()]
    out, cur = [], ""
    for p in parts:
        if len(cur) + len(p) > size and cur:
            out.append(cur)
            cur = ""
        cur += p + "\n\n"
    if cur.strip():
        out.append(cur)
    return out or ([text[:size]] if text else [])


def retrieve(text, query, k=4):
    cs = chunks(text)
    qw = re.findall(r"[а-яa-z0-9]{3,}", (query or "").lower())
    if not qw or not cs:
        return cs[:k]
    df = collections.Counter()
    for c in cs:
        for w in set(qw):
            if w in c.lower():
                df[w] += 1
    N = len(cs)
    scored = []
    for c in cs:
        lc = c.lower()
        s = 0.0
        for w in qw:
            tf = lc.count(w)
            if tf:
                s += tf / (tf + 1.5) * math.log(1 + N / (1 + df[w]))
        scored.append((s, c))
    scored.sort(reverse=True)
    return [c for s, c in scored[:k] if s > 0] or cs[:1]


def summarize_local(text, n=5):
    sents = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text))
        if 25 < len(s.strip()) < 400
    ]
    if not sents:
        return text[:600]
    freq = collections.Counter(re.findall(r"[а-яa-z]{4,}", text.lower()))
    top = {w for w, _ in freq.most_common(25)}
    scored = []
    for i, s in enumerate(sents):
        ws = re.findall(r"[а-яa-z]{4,}", s.lower())
        sc = sum(1 for w in ws if w in top) / (
            len(ws) ** 0.5 or 1
        ) + (0.4 if i < 3 else 0)
        scored.append((sc, i, s))
    scored.sort(reverse=True)
    return "\n".join(
        "• " + s for _, _, s in sorted(scored[:n], key=lambda x: x[1])
    )


FIELDS = {
    "Даты": r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
    "Суммы": r"\b\d[\d\s]{2,}(?:[.,]\d{2})?\s*(?:₽|руб\.?|рублей|USD|\$|EUR|€|тенге|сум)\b",
    "ИНН": r"\bИНН\s*[:№]?\s*(\d{10}|\d{12})\b",
    "Телефоны": r"(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}\b",
    "Email": r"[\w.+-]+@[\w-]+\.[\w.]{2,}",
    "СНИЛС": r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b",
    "Счета": r"\b\d{20}\b",
    "Договор №": r"(?:договор|контракт)\s*№\s*[\w\-/]+",
}


def extract_fields(text):
    out = {}
    for k, pat in FIELDS.items():
        vals = []
        for m in re.finditer(pat, text, re.I):
            v = (
                m.group(1) if m.groups() else m.group()
            ).strip()
            if v not in vals:
                vals.append(v)
        if vals:
            out[k] = vals[:8]
    return out


fields = extract_fields


def inn_ok(s):
    d = [int(c) for c in s]
    if len(d) == 10:
        w = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return sum(a * b for a, b in zip(w, d[:9])) % 11 % 10 == d[9]
    if len(d) == 12:
        w1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        w2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        return (
            sum(a * b for a, b in zip(w1, d[:10])) % 11 % 10
            == d[10]
            and sum(a * b for a, b in zip(w2, d[:11])) % 11 % 10
            == d[11]
        )
    return True


def snils_ok(s):
    d = re.sub(r"\D", "", s)
    if len(d) != 11:
        return True
    n = sum(int(d[i]) * (9 - i) for i in range(9))
    c = n % 101
    c = 0 if c in (100, 101) else c
    return c == int(d[9:11])


def luhn_ok(s):
    d = [int(c) for c in s][::-1]
    t = 0
    for i, x in enumerate(d):
        if i % 2:
            x *= 2
            x = x - 9 if x > 9 else x
        t += x
    return t % 10 == 0


MIX = re.compile(
    r"\b(?=[а-яёА-ЯЁ]*[a-zA-Z])(?=[a-zA-Z]*[а-яёА-ЯЁ])"
    r"[а-яёА-ЯЁa-zA-Z]{3,}\b"
)
RULES = [
    (r"[ \t]{2,}", "Лишние пробелы", "Заменить на один пробел", "style"),
    (
        r"\s+[,.;:!?]",
        "Пробел перед знаком препинания",
        "Убрать пробел",
        "punct",
    ),
    (
        r"[,;:!?](?=[А-Яа-яA-Za-z])",
        "Нет пробела после знака",
        "Добавить пробел",
        "punct",
    ),
    (
        r"\b([А-Яа-яёЁ]{2,})\s+\1\b",
        "Повтор слова",
        "Убрать дубль",
        "typo",
    ),
    (r"\s-\s", "Дефис вместо тире", "Заменить « - » на « — »", "style"),
    (
        r"_{3,}|\[указать[^\]]*\]|\bXX\.XX\.XXXX\b",
        "Незаполненный шаблон",
        "Заполнить поле",
        "critical",
    ),
    (
        r"\b(в целях осуществления|имеет место быть|на сегодняшний день)\b",
        "Канцелярит",
        "Упростить",
        "style",
    ),
]


def local_errors(text, tables=None):
    out = []
    for ln, line in enumerate(text.split("\n"), 1):
        for pat, title, fix, sev in RULES:
            for m in re.finditer(pat, line, re.I):
                if (
                    sev == "style"
                    and sum(1 for o in out if o["sev"] == "style") >= 4
                ):
                    continue
                out.append(
                    {
                        "line": ln,
                        "title": title,
                        "frag": line[
                            max(0, m.start() - 25) : m.end() + 25
                        ].strip(),
                        "fix": fix,
                        "sev": sev,
                    }
                )
        for m in MIX.finditer(line):
            out.append(
                {
                    "line": ln,
                    "title": "Кириллица+латиница в слове",
                    "frag": m.group(),
                    "fix": "Проверить раскладку",
                    "sev": "typo",
                }
            )
    for a, b in (("(", ")"), ("[", "]"), ("{", "}"), ("«", "»")):
        if text.count(a) != text.count(b):
            out.append(
                {
                    "line": 0,
                    "title": f"Непарные {a}{b}",
                    "frag": f"{text.count(a)}/{text.count(b)}",
                    "fix": "Сбалансировать",
                    "sev": "punct",
                }
            )
    dates = re.findall(
        r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
        text,
    )
    if len({re.sub(r"\d", "D", d) for d in dates}) > 1:
        out.append(
            {
                "line": 0,
                "title": "Разные форматы дат",
                "frag": ", ".join(dates[:4]),
                "fix": "Один формат",
                "sev": "style",
            }
        )
    for m in re.finditer(
        r"\bИНН\s*[:№]?\s*(\d{10}|\d{12})\b", text, re.I
    ):
        if not inn_ok(m.group(1)):
            out.append(
                {
                    "line": 0,
                    "title": "ИНН: неверная контрольная сумма",
                    "frag": m.group(1),
                    "fix": "Проверить ИНН",
                    "sev": "critical",
                }
            )
    for m in re.finditer(
        r"\bСНИЛС\s*[:№]?\s*([\d\- ]{11,14})", text, re.I
    ):
        if not snils_ok(m.group(1)):
            out.append(
                {
                    "line": 0,
                    "title": "СНИЛС: неверная контрольная сумма",
                    "frag": m.group(1).strip(),
                    "fix": "Проверить СНИЛС",
                    "sev": "critical",
                }
            )
    for m in re.finditer(r"\b(?:\d[ -]?){13,19}\b", text):
        s = re.sub(r"\D", "", m.group())
        if 13 <= len(s) <= 19 and not luhn_ok(s):
            out.append(
                {
                    "line": 0,
                    "title": "Номер карты не проходит Луна",
                    "frag": s[:6] + "…" + s[-4:],
                    "fix": "Проверить номер",
                    "sev": "critical",
                }
            )
    low = text.lower()
    need = []
    if "договор" in low:
        need = ["подпис", "дата", "сторон"]
    elif "заявление" in low:
        need = ["кому", "от ", "дата", "подпис"]
    elif "счёт" in low or "счет" in low:
        need = ["сумм", "инн", "дата"]
    elif "доверенность" in low:
        need = ["доверя", "дата", "подпис"]
    for w in need:
        if w not in low:
            out.append(
                {
                    "line": 0,
                    "title": "Нет обязательного реквизита",
                    "frag": w.strip(),
                    "fix": "Добавить",
                    "sev": "critical",
                }
            )
    for i, tb in enumerate(tables or []):
        nums = []
        for r in tb:
            label = " ".join(r).lower()
            vals = []
            for c in r:
                s = re.sub(r"[^\d.,-]", "", c).replace(",", ".")
                if s and s.count(".") < 2:
                    try:
                        vals.append(float(s))
                    except Exception:
                        pass
            if (
                ("итого" in label or "всего" in label)
                and nums
                and vals
            ):
                if abs(sum(nums) - vals[-1]) > 0.01:
                    out.append(
                        {
                            "line": 0,
                            "title": f"Таблица {i+1}: сумма не сходится",
                            "frag": f"итого {vals[-1]} ≠ {round(sum(nums),2)}",
                            "fix": "Пересчитать",
                            "sev": "critical",
                        }
                    )
            elif vals:
                nums.extend(vals[:1])
    for s in [
        s
        for s in re.split(r"(?<=[.!?])\s+", text)
        if len(s.split()) > 45
    ][:2]:
        out.append(
            {
                "line": 0,
                "title": "Слишком длинное предложение",
                "frag": s[:70] + "…",
                "fix": "Разбить",
                "sev": "style",
            }
        )
    order = {"critical": 0, "typo": 1, "punct": 2, "style": 3}
    out.sort(key=lambda o: order.get(o["sev"], 9))
    seen, uniq = set(), []
    for o in out:
        k = (o["title"], o["frag"])
        if k not in seen:
            seen.add(k)
            uniq.append(o)
    return uniq[:40]


errors = local_errors


def lt_errors(text):
    if not C.LT_URL:
        return []
    out = []
    for part in [
        text[i : i + 18000]
        for i in range(0, min(len(text), 54000), 18000)
    ]:
        try:
            body = urllib.parse.urlencode(
                {
                    "text": part,
                    "language": "auto",
                    "enabledOnly": "false",
                }
            ).encode()
            req = urllib.request.Request(
                C.LT_URL,
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.load(r)
            for m in j.get("matches", [])[:60]:
                rep = ", ".join(
                    x["value"] for x in m.get("replacements", [])[:3]
                )
                out.append(
                    {
                        "line": part[: m["offset"]].count("\n") + 1,
                        "title": m.get("shortMessage")
                        or m["message"][:60],
                        "frag": part[
                            m["offset"] : m["offset"] + m["length"]
                        ],
                        "fix": rep or m["message"][:120],
                        "sev": "typo",
                    }
                )
        except Exception:
            break
    return out


def describe_local(o):
    m = o.get("meta", {})
    parts = [
        f"Тип: {o['kind'].upper()}",
        f"Файл: {m.get('name','—')}",
        f"Размер: {round(m.get('size',0)/1024,1)} КБ",
    ]
    if o["kind"] == "image":
        parts.append(
            f"Изображение {m.get('width')}×{m.get('height')}, "
            f"{m.get('format')}, цвета: {', '.join(m.get('colors', []))}"
        )
    if o.get("pages"):
        parts.append(f"Страниц/слайдов: {o['pages']}")
    parts.append(
        "Распознанный текст (начало):\n" + o["text"].strip()[:700]
        if o["text"].strip()
        else "Текст не распознан. Нужен LLM_API_KEY (vision) или tesseract."
    )
    return "\n".join(parts)
