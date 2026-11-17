import asyncio
import hashlib
import hmac
import json
import os
import time
import urllib.parse

from aiohttp.test_utils import TestClient, TestServer

import db
import server


def init_data(uid):
    p = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE",
        "user": json.dumps({"id": uid, "first_name": "T"}),
    }
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(p.items()))
    sec = hmac.new(
        b"WebAppData",
        os.environ["BOT_TOKEN"].encode(),
        hashlib.sha256,
    ).digest()
    p["hash"] = hmac.new(sec, dcs.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(p)


def test_api():
    async def run():
        async with TestClient(TestServer(server.app)) as c:
            h1 = {"X-Telegram-Init-Data": init_data(1)}
            r = await c.get("/api/state", headers=h1)
            assert r.status == 200
            j = await r.json()
            assert j["user"]["owner"] is True

            r = await c.post(
                "/api/jobs",
                headers=h1,
                json={"mode": "photo", "prompt": "кот"},
            )
            assert r.status == 200
            jid = (await r.json())["job"]
            r = await c.post(
                "/api/cancel",
                headers=h1,
                json={"id": jid},
            )
            assert r.status == 200

            r = await c.get("/api/state")
            assert r.status == 401
            h2 = {"X-Telegram-Init-Data": init_data(2)}
            r = await c.get("/api/admin/stats", headers=h2)
            assert r.status == 403
            r = await c.get("/api/admin/audit", headers=h1)
            assert r.status == 200
            r = await c.post(
                "/api/admin/clean",
                headers=h1,
                json={"dry": True},
            )
            assert r.status == 200
            r = await c.get("/metrics")
            assert r.status == 200 and "lex_users" in await r.text()
            r = await c.get("/healthz")
            assert r.status == 200

    asyncio.run(run())
