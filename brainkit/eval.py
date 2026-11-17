import time

from . import core

CASES = [
    (
        "Договор №12 от 17.11.2026. Сумма 150000 руб. Срок: до 31.12.2026. Аванс 50%.",
        "какая сумма и срок?",
        ["150000", "31.12.2026"],
    ),
    (
        "Итого: 100000. Позиции: 60000 и 30000.",
        "сходится ли итог? если нет — сколько должно быть?",
        ["90000"],
    ),
    (
        "ИНН 7701234561. Подпись: ______",
        "какие ошибки в реквизитах?",
        ["инн"],
    ),
    (
        "Аренда 60000 руб./мес, срок 11 месяцев с 01.12.2026.",
        "сколько всего за срок?",
        ["660000"],
    ),
    (
        "Просрочка 15 дней, пеня 0,1% в день от 150000.",
        "размер пени?",
        ["2250"],
    ),
    (
        "Оплата в течение 5 банковских дней с даты счёта от 17.11.2026.",
        "когда крайний срок оплаты примерно?",
        ["2"],
    ),
]


def run():
    print(f"{'УРОВЕНЬ':8} {'ТОЧНОСТЬ':10} {'ВРЕМЯ':8} {'ЦЕНА':10}")
    for tier in ("basic", "pro", "max"):
        ok = 0
        started = time.time()
        cost = 0.0
        for context, question, expected in CASES:
            result = core.ask(question, context, tier=tier)
            answer = (
                result["answer"].lower().replace(" ", "").replace(",", "")
            )
            ok += all(
                item.lower().replace(" ", "") in answer
                for item in expected
            )
            cost += result["meta"]["cost"]
        print(
            f"{tier.upper():8} {ok}/{len(CASES):<8} "
            f"{round(time.time() - started, 1)}с   ${round(cost, 4)}"
        )


if __name__ == "__main__":
    run()
