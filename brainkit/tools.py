import ast
import json
import operator
import re

from .doclib import chunks, errors, fields, inn_ok, luhn_ok, retrieve, snils_ok

OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _ev(n):
    if isinstance(n, ast.Expression):
        return _ev(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in OPS:
        return OPS[type(n.op)](_ev(n.left), _ev(n.right))
    if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
        return OPS[type(n.op)](_ev(n.operand))
    raise ValueError("разрешена только арифметика")


def calc(expr):
    try:
        return str(
            round(
                _ev(
                    ast.parse(
                        re.sub(r"[^\d+\-*/().% ]", "", str(expr)),
                        mode="eval",
                    )
                ),
                6,
            )
        )
    except Exception as e:
        return "ошибка: " + str(e)[:80]


def run_tool(name, arg, ctx):
    if name == "docs":
        return (
            "\n---\n".join(retrieve(ctx, str(arg), 4))[:6000]
            or "ничего не найдено"
        )
    if name == "calc":
        return calc(arg)
    if name == "fields":
        return json.dumps(fields(ctx), ensure_ascii=False)[:3000]
    if name == "errors":
        e = errors(ctx)
        return (
            "\n".join(
                f"{x['sev']}: {x['title']} — «{x['frag']}» → {x['fix']}"
                for x in e[:25]
            )
            or "явных ошибок нет"
        )
    return "неизвестный инструмент"
