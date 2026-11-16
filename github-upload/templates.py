"""Каталог шаблонов: документы, таблицы и файлы."""

from __future__ import annotations

import csv
import datetime
import io
import json

TODAY = datetime.date(2026, 11, 17)
D0 = TODAY.strftime("%d.%m.%Y")
ORG1 = {
    "name": "ООО «Ромашка»",
    "inn": "7701234560",
    "kpp": "770101001",
    "addr": "г. Москва, ул. Ленина, д. 10, оф. 5",
    "acc": "40702810900000012345",
    "bank": "ПАО Сбербанк",
    "bik": "044525225",
    "ks": "30101810400000000225",
}
ORG2 = {
    "name": "ООО «Василёк»",
    "inn": "7812345675",
    "kpp": "781201001",
    "addr": "г. Санкт-Петербург, Невский пр., д. 20",
    "acc": "40702810100000054321",
    "bank": "ПАО Сбербанк",
    "bik": "044030653",
    "ks": "30101810500000000653",
}
PERSON = {
    "fio": "Иванов Иван Иванович",
    "pos": "менеджер по продажам",
    "phone": "+7 900 123-45-67",
    "email": "ivanov@example.ru",
}
DISCLAIMER = (
    "Образец носит справочный характер. Проверьте формулировки под свою ситуацию."
)

DOCS: dict = {}
SHEETS: dict = {}
FILES: dict = {}


def h(text):
    return ("h", text)


def p(text):
    return ("p", text)


def c(text):
    return ("c", text)


def t(rows):
    return ("t", rows)


def sign(a, b=""):
    return ("sign", [a, b])


def D(key, title, cat, desc, fields, sample, body):
    DOCS[key] = {
        "key": key,
        "type": "doc",
        "title": title,
        "cat": cat,
        "desc": desc,
        "fields": [{"id": a, "label": b, "kind": c} for a, b, c in fields],
        "sample": sample,
        "body": body,
    }


def S(key, title, cat, desc, spec):
    SHEETS[key] = dict(spec, key=key, type="sheet", title=title, cat=cat, desc=desc)


def F(key, title, cat, desc, ext, mime, build):
    FILES[key] = {
        "key": key,
        "type": "file",
        "title": title,
        "cat": cat,
        "desc": desc,
        "ext": ext,
        "mime": mime,
        "build": build,
    }


def _doc(key, title, cat, desc, fields, sample, lines):
    D(key, title, cat, desc, fields, sample, lambda d: lines(d))


def _simple(fields, sample, heading, phrase):
    return lambda d: [
        p(sample.get("to", "")),
        p("от " + d.get("fio", PERSON["fio"])),
        h(heading),
        p(phrase(d)),
        sign(f"{d.get('date', D0)}    ______________ / {d.get('fio', PERSON['fio'])}"),
    ]


_doc(
    "otpusk",
    "Заявление на отпуск",
    "Кадры",
    "Ежегодный оплачиваемый отпуск",
    [
        ("to", "Кому", "text"),
        ("fio", "ФИО", "text"),
        ("pos", "Должность", "text"),
        ("start", "Дата начала", "date"),
        ("days", "Дней", "number"),
        ("date", "Дата", "date"),
    ],
    {
        "to": "Генеральному директору ООО «Ромашка» Петрову П.П.",
        "fio": PERSON["fio"],
        "pos": PERSON["pos"],
        "start": "01.12.2026",
        "days": "14",
        "date": D0,
    },
    _simple(
        [],
        {},
        "ЗАЯВЛЕНИЕ",
        lambda d: f"Прошу предоставить ежегодный оплачиваемый отпуск с {d['start']} на {d['days']} календарных дней.",
    ),
)

for _key, _title, _heading, _phrase, _fields, _sample in [
    (
        "uvolnenie",
        "Заявление на увольнение",
        "ЗАЯВЛЕНИЕ",
        lambda d: f"Прошу уволить меня по собственному желанию {d['last']}.",
        [("last", "Последний день", "date"), ("date", "Дата", "date")],
        {"last": "01.12.2026", "date": D0},
    ),
    (
        "obyasnitelnaya",
        "Объяснительная записка",
        "ОБЪЯСНИТЕЛЬНАЯ ЗАПИСКА",
        lambda d: d["why"],
        [("what", "Что произошло", "textarea"), ("why", "Причина", "textarea")],
        {"what": "Отсутствие на рабочем месте.", "why": "Уважительная причина."},
    ),
    (
        "sluzhebka",
        "Служебная записка",
        "СЛУЖЕБНАЯ ЗАПИСКА",
        lambda d: d["text"],
        [("theme", "Тема", "text"), ("text", "Содержание", "textarea")],
        {"theme": "Служебная записка", "text": "Прошу рассмотреть вопрос."},
    ),
    (
        "pretenziya",
        "Претензия",
        "ПРЕТЕНЗИЯ",
        lambda d: d["text"],
        [("text", "Суть требования", "textarea")],
        {"text": "Прошу исполнить обязательства в установленный срок."},
    ),
]:
    _doc(
        _key,
        _title,
        "Кадры" if _key in ("uvolnenie", "obyasnitelnaya", "sluzhebka") else "Обращения",
        _title,
        [("to", "Кому", "text"), ("fio", "ФИО", "text"), ("date", "Дата", "date")] + _fields,
        {"to": "", "fio": PERSON["fio"], "date": D0, **_sample},
        _simple([], {}, _heading, _phrase),
    )

_doc(
    "uslugi",
    "Договор оказания услуг",
    "Договоры",
    "Базовый договор с предметом и суммой",
    [
        ("a", "Заказчик", "text"),
        ("b", "Исполнитель", "text"),
        ("subject", "Предмет", "textarea"),
        ("sum", "Сумма, ₽", "money"),
        ("date", "Дата", "date"),
    ],
    {
        "a": ORG1["name"],
        "b": ORG2["name"],
        "subject": "Разработка и поддержка сайта.",
        "sum": "150 000",
        "date": D0,
    },
    lambda d: [
        h("ДОГОВОР ОКАЗАНИЯ УСЛУГ"),
        c(d["date"]),
        p(f"{d['a']} и {d['b']} заключили договор."),
        p("Предмет: " + d["subject"]),
        p(f"Стоимость услуг — {d['sum']} руб., НДС не облагается."),
        p("Оплата: аванс 50%, остаток после подписания акта."),
        t([["Заказчик", "Исполнитель"], [d["a"], d["b"]]]),
    ],
)

_doc(
    "arenda",
    "Договор аренды",
    "Договоры",
    "Аренда нежилого помещения",
    [
        ("a", "Арендодатель", "text"),
        ("b", "Арендатор", "text"),
        ("obj", "Объект", "text"),
        ("rent", "Аренда, ₽/мес", "money"),
        ("date", "Дата", "date"),
    ],
    {"a": ORG1["name"], "b": ORG2["name"], "obj": "нежилое помещение 45 м²", "rent": "60 000", "date": D0},
    lambda d: [
        h("ДОГОВОР АРЕНДЫ"),
        c(d["date"]),
        p(f"{d['a']} — арендодатель, {d['b']} — арендатор."),
        p("Объект: " + d["obj"]),
        p(f"Арендная плата — {d['rent']} руб. в месяц."),
    ],
)

_doc(
    "nda",
    "Соглашение о неразглашении",
    "Договоры",
    "Защита конфиденциальной информации",
    [("a", "Сторона 1", "text"), ("b", "Сторона 2", "text"), ("term", "Срок", "text"), ("fine", "Штраф, ₽", "money")],
    {"a": ORG1["name"], "b": ORG2["name"], "term": "3 года", "fine": "500 000"},
    lambda d: [
        h("СОГЛАШЕНИЕ О НЕРАЗГЛАШЕНИИ"),
        p(f"{d['a']} и {d['b']} обязуются не раскрывать конфиденциальную информацию."),
        p(f"Срок — {d['term']}, штраф — {d['fine']} руб."),
    ],
)

_doc(
    "schet",
    "Счёт на оплату",
    "Финансы",
    "Счёт с реквизитами и позициями",
    [("num", "Номер", "text"), ("date", "Дата", "date"), ("buy", "Покупатель", "text"), ("sum", "Сумма, ₽", "money")],
    {"num": "128", "date": D0, "buy": ORG2["name"], "sum": "150 000"},
    lambda d: [
        h(f"СЧЁТ № {d['num']} от {d['date']}"),
        p(f"Поставщик: {ORG1['name']}, ИНН {ORG1['inn']}"),
        p(f"Покупатель: {d['buy']}"),
        t([["Наименование", "Сумма, ₽"], ["Услуги", d["sum"]], ["ИТОГО", d["sum"]]]),
        p("Оплатить в течение 5 банковских дней."),
    ],
)

_doc(
    "raspiska",
    "Расписка",
    "Финансы",
    "Подтверждение получения денег",
    [("fio", "ФИО", "text"), ("from", "От кого", "text"), ("sum", "Сумма, ₽", "money"), ("back", "Вернуть до", "date")],
    {"fio": PERSON["fio"], "from": "Петрова П.П.", "sum": "100 000", "back": "17.05.2027"},
    lambda d: [
        h("РАСПИСКА"),
        p(f"Я, {d['fio']}, получил от {d['from']} {d['sum']} руб."),
        p(f"Обязуюсь вернуть до {d['back']}."),
    ],
)

_doc(
    "doverennost",
    "Доверенность",
    "Обращения",
    "Представление интересов",
    [("fio", "Доверитель", "text"), ("to", "Представитель", "text"), ("powers", "Полномочия", "textarea")],
    {"fio": PERSON["fio"], "to": "Сидоров С.С.", "powers": "представлять интересы в государственных органах."},
    lambda d: [
        h("ДОВЕРЕННОСТЬ"),
        p(f"Я, {d['fio']}, доверяю {d['to']} {d['powers']}"),
    ],
)

_doc(
    "rezume",
    "Резюме",
    "Личное",
    "Опыт, навыки и контакты",
    [("fio", "ФИО", "text"), ("role", "Должность", "text"), ("phone", "Телефон", "text"), ("email", "Email", "text"), ("exp", "Опыт", "textarea")],
    {"fio": PERSON["fio"], "role": "Менеджер по продажам", "phone": PERSON["phone"], "email": PERSON["email"], "exp": "2022–2026 — ООО «Ромашка»."},
    lambda d: [
        h(d["fio"]),
        c(d["role"]),
        p(f"{d['phone']} · {d['email']}"),
        p("ОПЫТ\n" + d["exp"]),
    ],
)

# Остальные документы строятся по тому же принципу.
for _key, _title, _cat, _desc in [
    ("priem", "Заявление о приёме на работу", "Кадры", "Оформление трудоустройства"),
    ("prikaz", "Приказ", "Кадры", "Распорядительный документ"),
    ("protokol", "Протокол совещания", "Кадры", "Фиксация решений"),
    ("akt_pp", "Акт приёма-передачи", "Договоры", "Передача имущества"),
    ("akt_rabot", "Акт выполненных работ", "Договоры", "Закрытие этапа"),
    ("kp", "Коммерческое предложение", "Продажи", "КП клиенту"),
    ("garant", "Гарантийное письмо", "Продажи", "Гарантия оплаты"),
    ("uvedomlenie", "Уведомление", "Обращения", "Официальное извещение"),
    ("harakteristika", "Характеристика", "Кадры", "С места работы"),
    ("opis", "Опись вложения", "Обращения", "Опись к отправлению"),
]:
    _doc(
        _key,
        _title,
        _cat,
        _desc,
        [("to", "Кому", "text"), ("fio", "ФИО", "text"), ("text", "Содержание", "textarea"), ("date", "Дата", "date")],
        {"to": "", "fio": PERSON["fio"], "text": _desc, "date": D0},
        lambda d, heading=_title: [
            p(d.get("to", "")),
            h(heading.upper()),
            p(d.get("text", "")),
            sign(f"{d.get('date', D0)}    ______________"),
        ],
    )


def _sheet(key, title, cat, desc, headers, rows, formulas=None, widths=None, valid=None):
    S(
        key,
        title,
        cat,
        desc,
        {
            "headers": headers,
            "rows": rows,
            "formulas": formulas or {},
            "widths": widths or [18] * len(headers),
            "valid": valid or {},
            "total": {"label": "ИТОГО", "cols": []},
            "freeze": "A2",
        },
    )


_sheet(
    "budget",
    "Личный бюджет",
    "Финансы",
    "План/факт по категориям",
    ["Категория", "План ₽", "Факт ₽", "Отклонение ₽", "%"],
    [["Жильё", 45000, 45000], ["Продукты", 25000, 27400], ["Транспорт", 8000, 6200], ["Развлечения", 7000, 9800]],
    {"D": "=B{r}-C{r}", "E": "=IF(B{r}=0,0,C{r}/B{r})"},
    [24, 14, 14, 16, 10],
)
_sheet(
    "expenses",
    "Учёт расходов",
    "Финансы",
    "Журнал трат",
    ["Дата", "Категория", "Описание", "Сумма ₽"],
    [["17.11.2026", "Продукты", "Супермаркет", 3240], ["16.11.2026", "Транспорт", "Такси", 780]],
    {},
    [14, 18, 30, 14],
)
_sheet(
    "timesheet",
    "Табель рабочего времени",
    "Кадры",
    "Часы и оплата",
    ["Сотрудник", "Дней", "Часов/день", "Всего", "Ставка", "К оплате"],
    [["Иванов И.И.", 20, 8, 160, 560, 89600], ["Петров П.П.", 21, 8, 168, 900, 151200]],
    {"E": "=C{r}*D{r}", "F": "=E{r}*F{r}"},
)
_sheet(
    "invoice",
    "Счёт / инвойс",
    "Финансы",
    "Позиции и НДС",
    ["№", "Наименование", "Кол-во", "Цена ₽", "Сумма ₽"],
    [[1, "Разработка", 1, 120000], [2, "Поддержка", 1, 30000]],
    {"E": "=C{r}*D{r}"},
)
for _key, _title, _cat, _desc, _headers in [
    ("payroll", "Зарплатная ведомость", "Кадры", "Начисления и НДФЛ", ["ФИО", "Оклад", "Начислено", "НДФЛ", "К выплате"]),
    ("crm", "Воронка продаж", "Продажи", "Стадии сделок", ["Лид", "Компания", "Стадия", "Сумма", "Менеджер"]),
    ("project", "План проекта", "Проекты", "Задачи и сроки", ["Задача", "Ответственный", "Старт", "Финиш", "Статус"]),
    ("warehouse", "Склад и остатки", "Склад", "Остатки и дозаказ", ["Артикул", "Наименование", "Остаток", "Минимум", "Статус"]),
    ("price", "Прайс-лист", "Продажи", "Цены и скидки", ["Артикул", "Наименование", "Цена", "Скидка", "Итог"]),
    ("payments", "График платежей", "Финансы", "Долг и проценты", ["№", "Дата", "Платёж", "Долг", "Остаток"]),
    ("kpi", "KPI-дашборд", "Проекты", "План/факт", ["Показатель", "Вес", "План", "Факт", "Итог"]),
    ("checklist", "Чек-лист запуска", "Проекты", "Статусы задач", ["Пункт", "Ответственный", "Срок", "Статус"]),
    ("smeta", "Смета работ", "Финансы", "Позиции и итог", ["Работа", "Кол-во", "Цена", "Сумма"]),
    ("inventory", "Инвентаризация", "Склад", "Учёт и факт", ["Наименование", "По учёту", "Факт", "Расхождение"]),
]:
    _sheet(
        _key,
        _title,
        _cat,
        _desc,
        _headers,
        [["Пример", "1", "2", "3", "OK"]],
    )


def _csv(rows):
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


FILES.update(
    {
        "csv_expenses": {
            "key": "csv_expenses",
            "type": "file",
            "title": "CSV: расходы",
            "cat": "Данные",
            "desc": "Готовый CSV для импорта",
            "ext": "csv",
            "mime": "text/csv",
            "build": lambda: _csv(
                [["date", "category", "amount"], ["2026-11-17", "Продукты", 3240]]
            ),
        },
        "csv_batch": {
            "key": "csv_batch",
            "type": "file",
            "title": "CSV: массовые заявления",
            "cat": "Данные",
            "desc": "Шаблон batch-документов",
            "ext": "csv",
            "mime": "text/csv",
            "build": lambda: _csv(
                [["org", "fio", "text"], [ORG1["name"], PERSON["fio"], "Заявление"]]
            ),
        },
        "json_config": {
            "key": "json_config",
            "type": "file",
            "title": "JSON: конфиг",
            "cat": "Данные",
            "desc": "Тарифы и лимиты",
            "ext": "json",
            "mime": "application/json",
            "build": lambda: json.dumps(
                {"app": "LexKL", "version": "2.0"}, ensure_ascii=False, indent=2
            ).encode(),
        },
        "md_tz": {
            "key": "md_tz",
            "type": "file",
            "title": "Markdown: ТЗ",
            "cat": "Данные",
            "desc": "Техническое задание",
            "ext": "md",
            "mime": "text/markdown",
            "build": lambda: "# ТЗ\n\nМодуль разбора документов.".encode(),
        },
        "ics_meeting": {
            "key": "ics_meeting",
            "type": "file",
            "title": "ICS: встреча",
            "cat": "Данные",
            "desc": "Событие календаря",
            "ext": "ics",
            "mime": "text/calendar",
            "build": lambda: (
                "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
                "UID:meet@lexkl\r\nSUMMARY:Планёрка\r\n"
                "DTSTART:20261118T100000Z\r\nDTEND:20261118T110000Z\r\n"
                "END:VEVENT\r\nEND:VCALENDAR\r\n"
            ).encode(),
        },
        "html_report": {
            "key": "html_report",
            "type": "file",
            "title": "HTML: отчёт",
            "cat": "Данные",
            "desc": "Автономный HTML-отчёт",
            "ext": "html",
            "mime": "text/html",
            "build": lambda: (
                "<!doctype html><html lang='ru'><meta charset='utf-8'>"
                "<title>Отчёт</title><h1>Отчёт</h1><table border='1'>"
                "<tr><th>Показатель</th><th>Факт</th></tr>"
                "<tr><td>Выручка</td><td>1 620 000</td></tr></table></html>"
            ).encode(),
        },
        "txt_checklist": {
            "key": "txt_checklist",
            "type": "file",
            "title": "TXT: чек-лист",
            "cat": "Данные",
            "desc": "Список запуска",
            "ext": "txt",
            "mime": "text/plain",
            "build": lambda: "[x] Домен\n[ ] Оплата Stars\n".encode(),
        },
        "xml_catalog": {
            "key": "xml_catalog",
            "type": "file",
            "title": "XML: каталог",
            "cat": "Данные",
            "desc": "Выгрузка прайса",
            "ext": "xml",
            "mime": "application/xml",
            "build": lambda: (
                '<?xml version="1.0" encoding="UTF-8"?><catalog>'
                '<item id="S-01"><name>Лендинг</name><price>60000</price></item>'
                "</catalog>"
            ).encode(),
        },
        "sql_schema": {
            "key": "sql_schema",
            "type": "file",
            "title": "SQL: схема БД",
            "cat": "Данные",
            "desc": "Таблицы users/jobs",
            "ext": "sql",
            "mime": "application/sql",
            "build": lambda: (
                "CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT);\n"
                "CREATE TABLE jobs(id TEXT PRIMARY KEY,uid INTEGER,kind TEXT);\n"
            ).encode(),
        },
    }
)


def blocks_of(key, fields=None, blank=False):
    template = DOCS[key]
    data = dict(template["sample"])
    if blank:
        data = {k: "" for k in data}
    if fields:
        data.update({k: v for k, v in fields.items() if v is not None})
    return template["body"](data), template["title"]


def blocks_text(blocks):
    out = []
    for kind, value in blocks:
        if kind in ("h", "c", "p"):
            out.append(value)
        elif kind == "t":
            out += [" | ".join(str(x) for x in row) for row in value]
        elif kind == "sign":
            out.append("    ".join(x for x in value if x))
    return "\n\n".join(out)


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def to_docx(blocks, title):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    for kind, value in blocks:
        if kind == "h":
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = paragraph.add_run(value)
            run.bold = True
            run.font.size = Pt(14)
        elif kind == "c":
            paragraph = document.add_paragraph(value)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif kind == "p":
            for line in value.split("\n"):
                document.add_paragraph(line)
        elif kind == "t":
            table = document.add_table(rows=0, cols=len(value[0]))
            table.style = "Table Grid"
            for index, row in enumerate(value):
                cells = table.add_row().cells
                for j, cell in enumerate(row):
                    cells[j].text = str(cell)
                    if index == 0:
                        for run in cells[j].paragraphs[0].runs:
                            run.bold = True
        elif kind == "sign":
            document.add_paragraph("")
            table = document.add_table(rows=1, cols=2)
            for j, value_item in enumerate(value[:2]):
                table.rows[0].cells[j].text = value_item
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def to_pdf(blocks, title):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    for name, path in (
        ("DJ", FONT),
        ("DJB", FONTB),
        ("DJ", r"C:\Windows\Fonts\arial.ttf"),
        ("DJB", r"C:\Windows\Fonts\arialbd.ttf"),
    ):
        try:
            pdfmetrics.registerFont(TTFont(name, path))
        except Exception:
            pass

    try:
        pdfmetrics.getFont("DJ")
        regular_name = "DJ"
    except Exception:
        regular_name = "Helvetica"
    try:
        pdfmetrics.getFont("DJB")
        heading_name = "DJB"
    except Exception:
        heading_name = "Helvetica-Bold"
    regular = ParagraphStyle(
        "reg", fontName=regular_name, fontSize=10.5, leading=15, spaceAfter=6
    )
    heading = ParagraphStyle(
        "head",
        fontName=heading_name,
        fontSize=14,
        leading=18,
        alignment=1,
        spaceAfter=10,
    )
    center = ParagraphStyle(
        "ctr", fontName=regular_name, fontSize=10.5, leading=15, alignment=1, spaceAfter=6
    )

    def esc(value):
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )

    story = []
    for kind, value in blocks:
        if kind == "h":
            story.append(Paragraph(esc(value), heading))
        elif kind == "c":
            story.append(Paragraph(esc(value), center))
        elif kind == "p":
            story.append(Paragraph(esc(value), regular))
        elif kind == "t":
            data = [[Paragraph(esc(cell), regular) for cell in row] for row in value]
            table = Table(data, hAlign="LEFT", repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aa6c8")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eeff")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story += [table, Spacer(1, 8)]
        elif kind == "sign":
            story.append(Spacer(1, 14))
            story.append(
                Table(
                    [
                        [
                            Paragraph(esc(value[0]), regular),
                            Paragraph(esc(value[1] if len(value) > 1 else ""), regular),
                        ]
                    ],
                    colWidths=[85 * mm, 85 * mm],
                )
            )
    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    ).build(story)
    return buffer.getvalue()


def build_xlsx(spec):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = (
        spec["title"].replace("/", "-").replace("\\", "-")
        .replace("*", "").replace("?", "").replace(":", "-")
        .replace("[", "").replace("]", "")[:28]
    )
    headers = spec["headers"]
    rows = spec["rows"]
    sheet.append(headers)
    for row in rows:
        sheet.append(list(row))
    last = len(rows) + 1
    thin = Side(style="thin", color="C8D4EC")
    header_fill = PatternFill("solid", fgColor="7C5CFF")
    for index in range(1, len(headers) + 1):
        cell = sheet.cell(1, index)
        cell.fill = header_fill
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        sheet.column_dimensions[get_column_letter(index)].width = (
            spec.get("widths") or [18] * len(headers)
        )[index - 1]
    for row_index in range(2, last + 1):
        for col_index in range(1, len(headers) + 1):
            cell = sheet.cell(row_index, col_index)
            cell.border = Border(bottom=thin)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    for col, template in (spec.get("formulas") or {}).items():
        for row_index in range(2, last + 1):
            sheet[f"{col}{row_index}"] = template.format(r=row_index, p=row_index - 1)
    for ref, value in (spec.get("first") or {}).items():
        sheet[ref] = value
    for col, fmt in (spec.get("num") or {}).items():
        for row_index in range(2, last + 1):
            sheet[f"{col}{row_index}"].number_format = fmt
    if spec.get("total"):
        total_row = last + 1
        sheet.cell(total_row, 1, spec["total"].get("label", "ИТОГО"))
        for col in spec["total"].get("cols", []):
            sheet[f"{col}{total_row}"] = f"=SUM({col}2:{col}{last})"
        for col in range(1, len(headers) + 1):
            cell = sheet.cell(total_row, col)
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="E4EDFC")
    sheet.freeze_panes = spec.get("freeze", "A2")
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last}"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def render(key, fields=None, blank=False, fmt=None):
    if key in DOCS:
        blocks, title = blocks_of(key, fields, blank)
        fmt = fmt or "docx"
        data = to_pdf(blocks, title) if fmt == "pdf" else to_docx(blocks, title)
        mime = (
            "application/pdf"
            if fmt == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return f"{key}.{fmt}", data, mime
    if key in SHEETS:
        spec = SHEETS[key]
        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(spec["headers"])
            writer.writerows(spec["rows"])
            return f"{key}.csv", buffer.getvalue().encode("utf-8-sig"), "text/csv"
        return (
            f"{key}.xlsx",
            build_xlsx(spec),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if key in FILES:
        entry = FILES[key]
        return f"{key}.{entry['ext']}", entry["build"](), entry["mime"]
    raise KeyError(key)


def catalog():
    out = []
    for key, template in DOCS.items():
        blocks, _title = blocks_of(key)
        out.append(
            {
                "key": key,
                "type": "doc",
                "title": template["title"],
                "cat": template["cat"],
                "desc": template["desc"],
                "fields": [
                    dict(field, sample=template["sample"].get(field["id"], ""))
                    for field in template["fields"]
                ],
                "formats": ["docx", "pdf"],
                "preview": blocks_text(blocks)[:1800],
            }
        )
    for key, spec in SHEETS.items():
        out.append(
            {
                "key": key,
                "type": "sheet",
                "title": spec["title"],
                "cat": spec["cat"],
                "desc": spec["desc"],
                "fields": [],
                "formats": ["xlsx", "csv"],
                "preview_rows": [spec["headers"]] + spec["rows"][:7],
                "formula_cols": list((spec.get("formulas") or {}).keys()),
            }
        )
    for key, entry in FILES.items():
        out.append(
            {
                "key": key,
                "type": "file",
                "title": entry["title"],
                "cat": entry["cat"],
                "desc": entry["desc"],
                "fields": [],
                "formats": [entry["ext"]],
                "preview": entry["build"]().decode("utf-8", "ignore")[:1200],
            }
        )
    return out
