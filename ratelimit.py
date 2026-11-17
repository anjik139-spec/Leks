import time

from config import REDIS_URL

_mem = {}
_r = None
_LUA = """
local cap=tonumber(ARGV[1]) local per=tonumber(ARGV[2]) local now=tonumber(ARGV[3])
local d=redis.call('HMGET',KEYS[1],'t','ts')
local tokens=tonumber(d[1]) local ts=tonumber(d[2])
if tokens==nil then tokens=cap ts=now end
tokens=math.min(cap,tokens+(now-ts)*cap/per)
local ok=0
if tokens>=1 then tokens=tokens-1 ok=1 end
redis.call('HMSET',KEYS[1],'t',tokens,'ts',now)
redis.call('EXPIRE',KEYS[1],math.ceil(per*2))
return ok
"""


def _client():
    global _r
    if _r is None and REDIS_URL:
        try:
            import redis.asyncio as aioredis

            _r = aioredis.from_url(REDIS_URL, decode_responses=True)
        except Exception:
            _r = False
    return _r or None


def memory(key, cap, per):
    t = time.time()
    b = _mem.setdefault(key, [cap, t])
    b[0] = min(cap, b[0] + (t - b[1]) * cap / per)
    b[1] = t
    if b[0] < 1:
        return False
    b[0] -= 1
    return True


async def allow(key, cap, per):
    c = _client()
    if c:
        try:
            return bool(
                await c.eval(
                    _LUA,
                    1,
                    "rl:" + key,
                    cap,
                    per,
                    time.time(),
                )
            )
        except Exception:
            pass
    return memory(key, cap, per)
