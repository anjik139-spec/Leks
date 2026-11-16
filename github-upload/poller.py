import asyncio
import os
import socket

import db
from config import REDIS_URL

NAME = "bot:poller"
ID = f"{socket.gethostname()}:{os.getpid()}"
TTL = 45
_RENEW = """
if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('EXPIRE',KEYS[1],ARGV[2]) else return 0 end
"""
_RELEASE = """
if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) else return 0 end
"""


async def _redis():
    if not REDIS_URL:
        return None
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        return None


async def holder():
    r = await _redis()
    if r:
        v = await r.get(NAME)
        await r.close()
        return v
    h = db.lock_holder(NAME)
    return h["owner"] if h else None


class Guard:
    def __init__(self):
        self.r = None
        self.ok = False
        self.task = None

    async def __aenter__(self):
        self.r = await _redis()
        if self.r:
            self.ok = bool(
                await self.r.set(NAME, ID, nx=True, ex=TTL)
            ) or (await self.r.get(NAME) == ID)
        else:
            self.ok = db.lock_acquire(NAME, ID, TTL)
        if self.ok:
            self.task = asyncio.create_task(self._renew())
        return self

    async def _renew(self):
        while True:
            await asyncio.sleep(max(5, TTL // 3))
            try:
                if self.r:
                    await self.r.eval(_RENEW, 1, NAME, ID, TTL)
                else:
                    db.lock_acquire(NAME, ID, TTL)
            except Exception:
                pass

    async def __aexit__(self, *a):
        if self.task:
            self.task.cancel()
        try:
            if self.r:
                await self.r.eval(_RELEASE, 1, NAME, ID)
            else:
                db.lock_release(NAME, ID)
        except Exception:
            pass
        if self.r:
            try:
                await self.r.close()
            except Exception:
                pass
