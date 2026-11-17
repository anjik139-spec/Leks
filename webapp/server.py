"""Mini App backend: initData auth, state, generation, Telegram Stars."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import store

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_API = os.getenv("BOT_API", "https://api.telegram.org")
ROOT = Path(__file__).resolve().parent
COST = {"photo": 1, "video": 3, "song": 2}

app = FastAPI(title="Ghost Studio")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GeneratePayload(BaseModel):
    mode: str = Field(pattern="^(photo|video|song)$")
    prompt: str = Field(min_length=1, max_length=300)
    style: str = "Кино"
    hq: bool = False
    usedTpl: bool = False
    aspect: str = "4:5"
    dur: int = Field(default=6, ge=3, le=16)
    motion: int = Field(default=5, ge=1, le=10)
    tempo: int = Field(default=104, ge=70, le=150)
    mood: str = "Мечтательная"


class DeletePayload(BaseModel):
    id: str


class RestorePayload(BaseModel):
    work: dict


class InvoicePayload(BaseModel):
    plan: str = Field(pattern="^(month|year)$")


def _validate_init_data(raw: str) -> dict:
    if not raw:
        raise HTTPException(401, "initData missing")
    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    received = pairs.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise HTTPException(401, "invalid initData")
    try:
        return json.loads(pairs["user"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "invalid user") from exc


def _auth(init_data: str) -> tuple[int, str]:
    if not init_data:
        if os.getenv("WEBAPP_DEV", "0") == "1":
            return 1, "Dev"
        raise HTTPException(401, "initData required")
    user = _validate_init_data(init_data)
    uid = int(user["id"])
    name = " ".join(
        filter(None, [user.get("first_name"), user.get("last_name")])
    ) or user.get("username") or str(uid)
    return uid, name


def _public(uid: int, name: str, state: dict) -> dict:
    return {
        "user": {"id": uid, "name": name, "owner": uid in store.OWNERS},
        "pro": store.is_pro(uid, state),
        "pro_until": state.get("pro_until", 0),
        "balance": state.get("balance", 0),
        "stats": state.get("stats", {}),
        "works": state.get("works", []),
    }


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/api/state")
async def state(x_telegram_init_data: str = Header(default="")) -> dict:
    uid, name = _auth(x_telegram_init_data)
    return _public(uid, name, store.get(uid))


@app.post("/api/me")
async def me(request: Request) -> dict:
    body = await request.json()
    uid, name = _auth(str(body.get("initData", "")))
    data = store.get(uid)
    return {"id": uid, "name": name, "pro": store.is_pro(uid, data)}


@app.post("/api/generate")
async def generate(
    payload: GeneratePayload,
    x_telegram_init_data: str = Header(default=""),
) -> dict:
    uid, name = _auth(x_telegram_init_data)
    current = store.get(uid)
    cost = COST[payload.mode] + (1 if payload.hq else 0)

    if not store.is_pro(uid, current) and current.get("balance", 0) < cost:
        raise HTTPException(402, "nobalance")

    def mutate(u: dict) -> None:
        if not store.is_pro(uid, u):
            u["balance"] = u.get("balance", 0) - cost
        now = int(time.time())
        work = {
            "id": f"w{now}{hashlib.md5(payload.prompt.encode()).hexdigest()[:5]}",
            "seed": int(hashlib.md5(f"{payload.prompt}{now}".encode()).hexdigest()[:8], 16),
            "ts": now,
            **payload.model_dump(),
        }
        stats = u.setdefault(
            "stats",
            {"gen": 0, "photo": 0, "video": 0, "song": 0, "tpl": 0, "night": 0},
        )
        stats["gen"] = stats.get("gen", 0) + 1
        stats[payload.mode] = stats.get(payload.mode, 0) + 1
        if payload.usedTpl:
            stats["tpl"] = stats.get("tpl", 0) + 1
        u.setdefault("works", []).insert(0, work)

    updated = store.update(uid, mutate)
    work = updated["works"][0]
    return {"work": work, "balance": updated["balance"], "stats": updated["stats"]}


@app.post("/api/delete")
async def delete(
    payload: DeletePayload,
    x_telegram_init_data: str = Header(default=""),
) -> dict:
    uid, _ = _auth(x_telegram_init_data)
    updated = store.update(
        uid,
        lambda u: u.__setitem__(
            "works", [w for w in u.get("works", []) if w.get("id") != payload.id]
        ),
    )
    return {"works": updated.get("works", [])}


@app.post("/api/restore")
async def restore(
    payload: RestorePayload,
    x_telegram_init_data: str = Header(default=""),
) -> dict:
    uid, _ = _auth(x_telegram_init_data)

    def mutate(u: dict) -> None:
        works = u.setdefault("works", [])
        if not any(w.get("id") == payload.work.get("id") for w in works):
            works.insert(0, payload.work)
        works.sort(key=lambda w: w.get("ts", 0), reverse=True)

    updated = store.update(uid, mutate)
    return {"works": updated.get("works", [])}


@app.post("/api/invoice")
async def invoice(
    payload: InvoicePayload,
    x_telegram_init_data: str = Header(default=""),
) -> dict:
    uid, _ = _auth(x_telegram_init_data)
    if not BOT_TOKEN:
        raise HTTPException(503, "bot token missing")
    price = 250 if payload.plan == "month" else 1990
    body = {
        "title": "Ghost Studio PRO",
        "description": "Безлимитные генерации и высокое качество",
        "payload": f"pro:{payload.plan}:{uid}:{int(time.time())}",
        "currency": "XTR",
        "prices": [{"label": "PRO", "amount": price}],
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{BOT_API}/bot{BOT_TOKEN}/createInvoiceLink",
            json=body,
        )
    if response.status_code != 200:
        raise HTTPException(502, "telegram invoice failed")
    return {"link": response.json()["result"]}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "index.html")
