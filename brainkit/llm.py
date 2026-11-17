import json
import time
import urllib.error
import urllib.request

from . import config as C, store


class NoKey(Exception):
    pass


def price(model):
    for key, value in C.PRICES.items():
        if model.startswith(key):
            return value
    return C.DEFAULT_PRICE


def _post(body):
    request = urllib.request.Request(
        C.LLM_BASE + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + C.LLM_KEY,
        },
    )
    with urllib.request.urlopen(request, timeout=C.TIMEOUT) as response:
        return json.load(response)


def call(model, messages, tokens, temp, reason=None):
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": tokens,
        "temperature": temp,
    }
    if reason:
        body["reasoning_effort"] = reason
    try:
        data = _post(body)
    except urllib.error.HTTPError as exc:
        if reason and exc.code in (400, 422):
            body.pop("reasoning_effort", None)
            data = _post(body)
        elif exc.code in (429, 500, 502, 503):
            time.sleep(2.0)
            data = _post(body)
        else:
            raise
    usage = data.get("usage") or {}
    price_in, price_out = price(model)
    cost = (
        usage.get("prompt_tokens", 0) / 1000 * price_in
        + usage.get("completion_tokens", 0) / 1000 * price_out
    )
    store.spend_add(model, cost, usage.get("total_tokens", 0))
    return data["choices"][0]["message"]["content"].strip(), {
        "model": model,
        "tokens": usage.get("total_tokens", 0),
        "cost": cost,
    }


def complete(tier, messages, tokens=None, temp=None):
    if not C.LLM_KEY:
        return None, {"model": "local", "tokens": 0, "cost": 0.0}
    cfg = C.TIERS[tier]
    last = None
    for index, model in enumerate(cfg["models"]):
        if store.budget_left() <= 0 and index < len(cfg["models"]) - 1:
            continue
        try:
            return call(
                model,
                messages,
                tokens or cfg["tokens"],
                cfg["temp"] if temp is None else temp,
                cfg["reason"],
            )
        except Exception as exc:
            last = exc
            continue
    return None, {
        "model": "failed",
        "tokens": 0,
        "cost": 0.0,
        "error": str(last)[:150],
    }
