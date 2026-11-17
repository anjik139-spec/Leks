import glob
import json
import os
import tempfile

import db
import gen
from config import (
    CACHE_TTL_DAYS,
    DATA,
    EPHEMERAL_TTL_DAYS,
    EVENTS_TTL_DAYS,
    ORPHAN_TTL_DAYS,
)

EPH = ("ref_", "mask_", "dig_", "rep_", "tpl_")


def _referenced():
    ref = set()
    for j in db.q("SELECT files,params FROM jobs"):
        try:
            for f in json.loads(j["files"] or "[]"):
                ref.add(f["name"])
        except Exception:
            pass
        try:
            p = json.loads(j["params"] or "{}")
            for k in ("ref", "mask"):
                if p.get(k):
                    ref.add(str(p[k]))
        except Exception:
            pass
    try:
        for d in db.q("SELECT id FROM docs"):
            ref.add(f"src_{d['id']}.bin")
    except Exception:
        pass
    return ref


def sweep(dry=False):
    t = db.now()
    ref = _referenced()
    removed = []
    freed = 0
    root = os.path.join(DATA, "files")
    if os.path.isdir(root):
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if not os.path.isfile(path):
                continue
            age = t - int(os.path.getmtime(path))
            eph = name.startswith(EPH)
            old_eph = eph and age > EPHEMERAL_TTL_DAYS * 86400
            orphan = (
                (name not in ref)
                and not eph
                and age > ORPHAN_TTL_DAYS * 86400
            )
            if old_eph or orphan:
                sz = os.path.getsize(path)
                freed += sz
                removed.append(name)
                if not dry:
                    gen.remove(name)
    tmp_cut = t - 86400
    tmp_n = 0
    for p in glob.glob(os.path.join(tempfile.gettempdir(), "lex_*")):
        try:
            if os.path.getmtime(p) < tmp_cut:
                if not dry:
                    os.remove(p)
                tmp_n += 1
        except Exception:
            pass
    pruned = {}
    if not dry:
        for table, days in (
            ("idempotency", 1),
            ("events", EVENTS_TTL_DAYS),
            ("intel_cache", CACHE_TTL_DAYS),
            ("cache", CACHE_TTL_DAYS),
            ("init_sessions", 2),
        ):
            try:
                db.x(
                    f"DELETE FROM {table} WHERE ts<?",
                    (t - days * 86400,),
                )
                pruned[table] = db.q("SELECT changes() c")[0]["c"]
            except Exception:
                pruned[table] = "n/a"
        try:
            db.x("DELETE FROM locks WHERE expires<?", (t,))
        except Exception:
            pass
        try:
            db.x("VACUUM")
        except Exception:
            pass
    return {
        "files": len(removed),
        "freed_mb": round(freed / 1048576, 2),
        "tmp": tmp_n,
        "pruned": pruned,
        "sample": removed[:10],
        "dry": dry,
    }
