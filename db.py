import hashlib
import json
import os
import sqlite3
import threading
import time

from config import DATA, OWNERS

os.makedirs(DATA, exist_ok=True)
os.makedirs(DATA + "/files", exist_ok=True)
for _attempt in range(30):
    try:
        C = sqlite3.connect(
            DATA + "/bot.db",
            check_same_thread=False,
            timeout=5,
        )
        C.row_factory = sqlite3.Row
        C.execute("PRAGMA journal_mode=WAL")
        break
    except sqlite3.OperationalError:
        if _attempt == 29:
            raise
        time.sleep(1)
L = threading.Lock()


def q(s, p=()):
    with L:
        return [dict(r) for r in C.execute(s, p).fetchall()]


def x(s, p=()):
    with L:
        cur = C.execute(s, p)
        C.commit()
        return cur.lastrowid


def now():
    return int(time.time())


C.executescript(
    """
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        name TEXT DEFAULT '',
        balance INTEGER DEFAULT 5,
        pro_until INTEGER DEFAULT 0,
        sub INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_bonus INTEGER DEFAULT 0,
        ref_by INTEGER DEFAULT 0,
        ref_count INTEGER DEFAULT 0,
        ref_paid INTEGER DEFAULT 0,
        favs TEXT DEFAULT '[]',
        created INTEGER
    );
    CREATE TABLE IF NOT EXISTS jobs(
        id TEXT PRIMARY KEY,
        uid INTEGER,
        kind TEXT,
        params TEXT,
        status TEXT DEFAULT 'pending',
        tries INTEGER DEFAULT 0,
        run_at INTEGER DEFAULT 0,
        cost INTEGER DEFAULT 0,
        files TEXT DEFAULT '[]',
        error TEXT DEFAULT '',
        notify INTEGER DEFAULT 0,
        send INTEGER DEFAULT 0,
        ts INTEGER
    );
    CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,files TEXT,ts INTEGER);
    CREATE TABLE IF NOT EXISTS promos(code TEXT PRIMARY KEY,kind TEXT,value INTEGER,max INTEGER,used INTEGER DEFAULT 0,exp INTEGER);
    CREATE TABLE IF NOT EXISTS payments(uid INTEGER,payload TEXT,amount INTEGER,ts INTEGER);
    CREATE TABLE IF NOT EXISTS events(uid INTEGER,name TEXT,ts INTEGER);
    CREATE TABLE IF NOT EXISTS likes(uid INTEGER,work TEXT,ts INTEGER,PRIMARY KEY(uid,work));
    CREATE TABLE IF NOT EXISTS feed(work TEXT PRIMARY KEY,uid INTEGER,ts INTEGER,caption TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS flags(key TEXT PRIMARY KEY,val TEXT,pct INTEGER DEFAULT 100);
    CREATE TABLE IF NOT EXISTS spend(id INTEGER PRIMARY KEY AUTOINCREMENT,provider TEXT,cost REAL,ts INTEGER);
    CREATE TABLE IF NOT EXISTS init_sessions(hash TEXT PRIMARY KEY,uid INTEGER,ts INTEGER);
    CREATE TABLE IF NOT EXISTS quests(uid INTEGER,key TEXT,ts INTEGER,PRIMARY KEY(uid,key));
    CREATE TABLE IF NOT EXISTS rag(uid INTEGER,chunk TEXT,ts INTEGER);
    CREATE TABLE IF NOT EXISTS presets(
        uid INTEGER,
        id TEXT,
        data TEXT,
        ts INTEGER,
        PRIMARY KEY(uid,id)
    );
    CREATE TABLE IF NOT EXISTS docs(
        id TEXT PRIMARY KEY,
        chat_id INTEGER,
        uid INTEGER,
        name TEXT,
        kind TEXT,
        text TEXT,
        meta TEXT,
        ts INTEGER
    );
    CREATE TABLE IF NOT EXISTS chat_ctx(
        chat_id INTEGER PRIMARY KEY,
        last_doc TEXT,
        auto INTEGER DEFAULT -1,
        pending INTEGER DEFAULT 0,
        ts INTEGER
    );
    CREATE TABLE IF NOT EXISTS intel_cache(
        hash TEXT,
        task TEXT,
        result TEXT,
        ts INTEGER,
        PRIMARY KEY(hash,task)
    );
    CREATE INDEX IF NOT EXISTS d_chat ON docs(chat_id,ts);
    CREATE INDEX IF NOT EXISTS j_status ON jobs(status,run_at);
    CREATE INDEX IF NOT EXISTS j_uid ON jobs(uid,ts);
    """
)

MIG = [
    "ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN skin TEXT DEFAULT 'mint'",
    "ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'free'",
    "ALTER TABLE users ADD COLUMN trial_used INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN api_key TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN doc_profile TEXT DEFAULT '{}'",
    "ALTER TABLE users ADD COLUMN last_seen INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN write_ok INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN winback INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN reminded INTEGER DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 0",
    "ALTER TABLE cache ADD COLUMN emb TEXT DEFAULT ''",
    "ALTER TABLE cache ADD COLUMN kind TEXT DEFAULT ''",
    "ALTER TABLE jobs ADD COLUMN started INTEGER DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN heartbeat INTEGER DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN cancel INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN notify_mode TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN voice_mode INTEGER DEFAULT 0",
    """CREATE TABLE IF NOT EXISTS audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER,
        uid INTEGER,
        action TEXT,
        target TEXT,
        details TEXT,
        ip TEXT
    )""",
    "ALTER TABLE spend ADD COLUMN tokens INTEGER DEFAULT 0",
    """CREATE TABLE IF NOT EXISTS idempotency(
        key TEXT PRIMARY KEY,
        uid INTEGER,
        response TEXT,
        ts INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS locks(
        name TEXT PRIMARY KEY,
        owner TEXT,
        expires INTEGER
    )""",
]
for migration in MIG:
    try:
        x(migration)
    except Exception:
        pass


def user(uid, name=""):
    r = q("SELECT * FROM users WHERE id=?", (uid,))
    if r:
        if name and r[0]["name"] != name:
            x("UPDATE users SET name=? WHERE id=?", (name, uid))
        return r[0]
    x(
        "INSERT INTO users(id,name,created,last_seen) VALUES(?,?,?,?)",
        (uid, name, now(), now()),
    )
    return q("SELECT * FROM users WHERE id=?", (uid,))[0]


def upd(uid, **kw):
    user(uid)
    x(
        "UPDATE users SET " + ",".join(k + "=?" for k in kw) + " WHERE id=?",
        (*kw.values(), uid),
    )
    return user(uid)


def is_pro(uid, u=None):
    u = u or user(uid)
    return uid in OWNERS or u["pro_until"] > now()


def tier_of(uid, u=None):
    u = u or user(uid)
    if uid in OWNERS:
        return "studio"
    return u["tier"] if u["pro_until"] > now() else "free"


def add_xp(uid, n):
    u = user(uid)
    xp = u["xp"] + n
    level = int((xp / 100) ** 0.5) + 1
    upd(uid, xp=xp)
    return level


def favs(uid):
    return json.loads(user(uid)["favs"] or "[]")


def set_favs(uid, f):
    upd(uid, favs=json.dumps(f))


def cache_get(k):
    r = q("SELECT files FROM cache WHERE key=?", (k,))
    return json.loads(r[0]["files"]) if r else None


def cache_set(k, f, emb="", kind=""):
    x(
        "INSERT OR REPLACE INTO cache(key,files,ts,emb,kind) VALUES(?,?,?,?,?)",
        (k, json.dumps(f), now(), json.dumps(emb), kind),
    )


def claim():
    with L:
        r = C.execute(
            "UPDATE jobs SET status='running',tries=tries+1,started=?,heartbeat=? "
            "WHERE id=(SELECT id FROM jobs WHERE status='pending' AND run_at<=? AND cancel=0 "
            "ORDER BY priority DESC,ts LIMIT 1) RETURNING *",
            (now(), now(), now()),
        ).fetchone()
        C.commit()
        return dict(r) if r else None


def beat(jid):
    x(
        "UPDATE jobs SET heartbeat=? WHERE id=? AND status='running'",
        (now(), jid),
    )


def reap(stale=None):
    from config import JOB_STALE_SEC

    t = now()
    cut = t - (stale or JOB_STALE_SEC)
    n = 0
    rows = q(
        "SELECT * FROM jobs WHERE status='running' AND "
        "COALESCE(NULLIF(heartbeat,0),NULLIF(started,0),ts)<?",
        (cut,),
    )
    for j in rows:
        if j["tries"] < 3:
            x(
                "UPDATE jobs SET status='pending',run_at=?,heartbeat=0,error=? WHERE id=?",
                (t + 10, "перезапуск: воркер не отвечал", j["id"]),
            )
        else:
            x(
                "UPDATE jobs SET status='error',error=?,notify=0 WHERE id=?",
                ("воркер завис, попытки исчерпаны", j["id"]),
            )
            if j["cost"]:
                x(
                    "UPDATE users SET balance=balance+? WHERE id=?",
                    (j["cost"], j["uid"]),
                )
        n += 1
    return n


def cancel_job(uid, jid):
    r = q("SELECT * FROM jobs WHERE id=? AND uid=?", (jid, uid))
    if not r:
        return "notfound"
    j = r[0]
    if j["status"] == "pending":
        x(
            "UPDATE jobs SET status='cancelled',cancel=1,notify=1 WHERE id=?",
            (jid,),
        )
        if j["cost"]:
            x(
                "UPDATE users SET balance=balance+? WHERE id=?",
                (j["cost"], uid),
            )
        return "cancelled"
    if j["status"] == "running":
        x("UPDATE jobs SET cancel=1 WHERE id=?", (jid,))
        return "stopping"
    return "late"


def audit(uid, action, target="", details="", ip=""):
    x(
        "INSERT INTO audit(ts,uid,action,target,details,ip) VALUES(?,?,?,?,?,?)",
        (
            now(),
            uid,
            action,
            str(target),
            json.dumps(details, ensure_ascii=False)[:800],
            ip,
        ),
    )


def lock_acquire(name, owner, ttl=45):
    t = now()
    with L:
        r = C.execute(
            "SELECT owner,expires FROM locks WHERE name=?",
            (name,),
        ).fetchone()
        if r and r["expires"] > t and r["owner"] != owner:
            C.commit()
            return False
        C.execute(
            "INSERT OR REPLACE INTO locks VALUES(?,?,?)",
            (name, owner, t + ttl),
        )
        C.commit()
        return True


def lock_release(name, owner):
    x(
        "DELETE FROM locks WHERE name=? AND owner=?",
        (name, owner),
    )


def idem_claim(uid, key):
    if not key:
        return None
    x("DELETE FROM idempotency WHERE ts<?", (now() - 86400,))
    r = q(
        "SELECT response FROM idempotency WHERE key=? AND uid=?",
        (key, uid),
    )
    if r:
        return (
            json.loads(r[0]["response"])
            if r[0]["response"]
            else {"__inflight": True}
        )
    try:
        x(
            "INSERT INTO idempotency(key,uid,response,ts) VALUES(?,?,?,?)",
            (key, uid, "", now()),
        )
    except Exception:
        return {"__inflight": True}
    return None


def idem_done(uid, key, payload):
    if key:
        x(
            "UPDATE idempotency SET response=?,ts=? WHERE key=? AND uid=?",
            (
                json.dumps(payload, ensure_ascii=False),
                now(),
                key,
                uid,
            ),
        )


def idem_drop(uid, key):
    if key:
        x(
            "DELETE FROM idempotency WHERE key=? AND uid=?",
            (key, uid),
        )


def lock_holder(name):
    r = q("SELECT owner,expires FROM locks WHERE name=?", (name,))
    return r[0] if r and r[0]["expires"] > now() else None


def retry(j, err):
    if j["tries"] < 3:
        x(
            "UPDATE jobs SET status='pending',run_at=?,error=? WHERE id=?",
            (now() + 5 * j["tries"], err[:300], j["id"]),
        )
    else:
        x(
            "UPDATE jobs SET status='error',error=? WHERE id=?",
            (err[:300], j["id"]),
        )
        if j["cost"]:
            x(
                "UPDATE users SET balance=balance+? WHERE id=?",
                (j["cost"], j["uid"]),
            )


def busy(uid):
    return q(
        "SELECT COUNT(*) c FROM jobs WHERE uid=? AND status IN ('pending','running')",
        (uid,),
    )[0]["c"]


def ev(uid, name):
    x("INSERT INTO events VALUES(?,?,?)", (uid, name, now()))


def spend_add(p, c, tokens=0):
    x(
        "INSERT INTO spend(provider,cost,ts,tokens) VALUES(?,?,?,?)",
        (p, c, now(), tokens),
    )


def spend_breakdown(days=1):
    return q(
        "SELECT provider,ROUND(SUM(cost),4) s,SUM(tokens) t "
        "FROM spend WHERE ts>? GROUP BY provider ORDER BY s DESC",
        (now() - days * 86400,),
    )


def spend_today():
    return round(
        q(
            "SELECT COALESCE(SUM(cost),0) s FROM spend WHERE ts>?",
            (now() - 86400,),
        )[0]["s"],
        4,
    )


def flags_for(uid):
    out = {}
    for flag in q("SELECT * FROM flags"):
        if (
            flag["pct"] >= 100
            or int(
                hashlib.sha256(f"{uid}:{flag['key']}".encode()).hexdigest()[:4], 16
            )
            % 100
            < flag["pct"]
        ):
            out[flag["key"]] = flag["val"]
    return out


def like_toggle(uid, w):
    if q("SELECT 1 FROM likes WHERE uid=? AND work=?", (uid, w)):
        x("DELETE FROM likes WHERE uid=? AND work=?", (uid, w))
        return False
    x("INSERT INTO likes VALUES(?,?,?)", (uid, w, now()))
    return True


def likes_of(w):
    return q("SELECT COUNT(*) c FROM likes WHERE work=?", (w,))[0]["c"]


def doc_put(d):
    x(
        "INSERT OR REPLACE INTO docs VALUES(?,?,?,?,?,?,?,?)",
        (
            d["id"],
            d["chat_id"],
            d["uid"],
            d["name"],
            d["kind"],
            d["text"],
            json.dumps(d.get("meta", {}), ensure_ascii=False),
            d["ts"],
        ),
    )


def doc_get(i):
    r = q("SELECT * FROM docs WHERE id=?", (i,))
    return r[0] if r else None


def docs_of(chat, n=5):
    return q(
        "SELECT * FROM docs WHERE chat_id=? ORDER BY ts DESC LIMIT ?",
        (chat, n),
    )


def ctx(chat):
    r = q("SELECT * FROM chat_ctx WHERE chat_id=?", (chat,))
    if r:
        return r[0]
    x("INSERT INTO chat_ctx(chat_id,ts) VALUES(?,?)", (chat, now()))
    return q("SELECT * FROM chat_ctx WHERE chat_id=?", (chat,))[0]


def ctx_set(chat, **kw):
    ctx(chat)
    x(
        "UPDATE chat_ctx SET " + ",".join(k + "=?" for k in kw) + ",ts=? WHERE chat_id=?",
        (*kw.values(), now(), chat),
    )


def ical_get(h, t):
    r = q("SELECT result FROM intel_cache WHERE hash=? AND task=?", (h, t))
    return r[0]["result"] if r else None


def ical_set(h, t, r):
    x(
        "INSERT OR REPLACE INTO intel_cache VALUES(?,?,?,?)",
        (h, t, r, now()),
    )
