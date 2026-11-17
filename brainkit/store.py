import json
import os
import sqlite3
import threading
import time

from . import config as C

try:
    import db as _main
except Exception:
    _main = None

os.makedirs(C.DATA_DIR, exist_ok=True)
_DB = os.path.join(C.DATA_DIR, "brain.db")
_conn = sqlite3.connect(_DB, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")
_L = threading.Lock()
_conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS kv(
        uid INTEGER,
        k TEXT,
        v TEXT,
        PRIMARY KEY(uid,k)
    );
    CREATE TABLE IF NOT EXISTS spend(
        day TEXT,
        model TEXT,
        cost REAL,
        tokens INTEGER,
        ts INTEGER
    );
    CREATE TABLE IF NOT EXISTS cache(
        k TEXT PRIMARY KEY,
        v TEXT,
        ts INTEGER
    );
    CREATE TABLE IF NOT EXISTS logs(
        ts INTEGER,
        uid INTEGER,
        tier TEXT,
        model TEXT,
        tokens INTEGER,
        cost REAL,
        ms INTEGER,
        ground REAL,
        q TEXT,
        a TEXT
    );
    """
)


def q(sql, p=()):
    with _L:
        return [dict(r) for r in _conn.execute(sql, p).fetchall()]


def x(sql, p=()):
    with _L:
        c = _conn.execute(sql, p)
        _conn.commit()
        return c.lastrowid


def now():
    return int(time.time())


def day():
    return time.strftime("%Y-%m-%d")


def setting(uid, k, default=""):
    r = q("SELECT v FROM kv WHERE uid=? AND k=?", (uid, k))
    return r[0]["v"] if r else default


def set_setting(uid, k, v):
    x("INSERT OR REPLACE INTO kv VALUES(?,?,?)", (uid, k, str(v)))


def spend_add(model, cost, tokens=0):
    if _main:
        try:
            _main.spend_add("brain:" + model, cost, tokens)
            return
        except Exception:
            pass
    x(
        "INSERT INTO spend VALUES(?,?,?,?,?)",
        (day(), model, round(cost, 6), tokens, now()),
    )


def spend_today():
    if _main:
        try:
            return round(_main.spend_today(), 4)
        except Exception:
            pass
    r = q(
        "SELECT COALESCE(SUM(cost),0) s FROM spend WHERE day=?",
        (day(),),
    )
    return round(r[0]["s"], 4)


def budget_left():
    return max(0.0, C.DAILY_BUDGET - spend_today())


def spend_breakdown(days=1):
    if _main:
        try:
            return _main.spend_breakdown(days)
        except Exception:
            pass
    return q(
        "SELECT model provider,ROUND(SUM(cost),4) s,SUM(tokens) t "
        "FROM spend WHERE ts>? GROUP BY model",
        (now() - days * 86400,),
    )


def cache_get(k):
    if not C.CACHE_DOCS:
        return None
    r = q("SELECT v,ts FROM cache WHERE k=?", (k,))
    if r and now() - r[0]["ts"] < 86400:
        return json.loads(r[0]["v"])
    return None


def cache_set(k, v):
    if C.CACHE_DOCS:
        x(
            "INSERT OR REPLACE INTO cache VALUES(?,?,?)",
            (k, json.dumps(v, ensure_ascii=False), now()),
        )


def log(uid, tier, meta, ms, question, answer):
    x(
        "INSERT INTO logs VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            now(),
            uid,
            tier,
            meta.get("model", ""),
            meta.get("tokens", 0),
            meta.get("cost", 0),
            ms,
            meta.get("ground", 1.0),
            question[:400] if C.LOG_CONTENT else f"<{len(question)} chars>",
            answer[:800] if C.LOG_CONTENT else f"<{len(answer)} chars>",
        ),
    )


def stats(days=7):
    since = now() - days * 86400
    return {
        "calls": q(
            "SELECT COUNT(*) c FROM logs WHERE ts>?", (since,)
        )[0]["c"],
        "cost": round(
            q(
                "SELECT COALESCE(SUM(cost),0) s FROM logs WHERE ts>?",
                (since,),
            )[0]["s"],
            4,
        ),
        "today": spend_today(),
        "left": round(budget_left(), 4),
        "by_tier": q(
            "SELECT tier,COUNT(*) c FROM logs WHERE ts>? GROUP BY tier",
            (since,),
        ),
    }
