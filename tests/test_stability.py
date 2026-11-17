import json
import os
import time

import core
import db
import gen
import housekeeping
import ratelimit


def _job(uid, kind="photo", status="pending", cost=1, **kw):
    jid = "t" + str(time.time_ns())
    cols = dict(
        id=jid,
        uid=uid,
        kind=kind,
        params=json.dumps({"prompt": "тест"}),
        status=status,
        cost=cost,
        ts=db.now(),
        priority=0,
        notify=0,
        tries=0,
        run_at=0,
        started=0,
        heartbeat=0,
        cancel=0,
    )
    cols.update(kw)
    db.x(
        "INSERT INTO jobs("
        + ",".join(cols)
        + ") VALUES("
        + ",".join("?" * len(cols))
        + ")",
        tuple(cols.values()),
    )
    return jid


def test_user_and_tier():
    u = db.user(1, "Owner")
    assert u["id"] == 1 and db.tier_of(1) == "studio" and db.is_pro(1)
    db.upd(2, balance=5)
    assert db.tier_of(2) == "free" and not db.is_pro(2)
    lvl = db.add_xp(2, 500)
    assert lvl >= 2


def test_submit_cost_and_limits():
    db.upd(3, balance=1, pro_until=0)
    r = core.submit(3, "photo", {"prompt": "кот"})
    assert r["job"] and db.user(3)["balance"] == 0
    try:
        core.submit(3, "photo", {"prompt": "ещё"})
        assert False
    except core.Err as e:
        assert e.code in ("nobalance", "busy")
    try:
        core.submit(1, "photo", {"prompt": "порно"})
        assert False
    except core.Err as e:
        assert e.code == "moderation"


def test_reaper():
    db.upd(4, balance=10)
    jid = _job(
        4,
        status="running",
        cost=2,
        tries=1,
        started=db.now() - 9999,
        heartbeat=db.now() - 9999,
    )
    assert db.reap(stale=60) >= 1
    assert (
        db.q("SELECT status FROM jobs WHERE id=?", (jid,))[0]["status"]
        == "pending"
    )
    jid2 = _job(
        4,
        status="running",
        cost=2,
        tries=3,
        started=db.now() - 9999,
        heartbeat=db.now() - 9999,
    )
    b0 = db.user(4)["balance"]
    db.reap(stale=60)
    assert (
        db.q("SELECT status FROM jobs WHERE id=?", (jid2,))[0]["status"]
        == "error"
    )
    assert db.user(4)["balance"] == b0 + 2


def test_cancel():
    db.upd(5, balance=3)
    jid = _job(5, cost=2)
    assert db.cancel_job(5, jid) == "cancelled"
    assert db.user(5)["balance"] == 5
    jrun = _job(5, status="running", cost=1)
    assert db.cancel_job(5, jrun) == "stopping"
    assert (
        db.q("SELECT cancel FROM jobs WHERE id=?", (jrun,))[0]["cancel"] == 1
    )
    assert db.cancel_job(5, "nope") == "notfound"


def test_notify_modes():
    assert core.should_notify(1, "video") and not core.should_notify(
        1, "photo"
    )
    db.upd(6, notify_mode="all")
    assert core.should_notify(6, "photo")
    db.upd(6, notify_mode="off")
    assert not core.should_notify(6, "video")


def test_housekeeping():
    gen.save("ref_old.png", b"x")
    gen.save("keep.png", b"y")
    old = db.now() - 40 * 86400
    os.utime(gen.path("ref_old.png"), (old, old))
    jid = _job(7, status="done")
    db.x(
        "UPDATE jobs SET files=? WHERE id=?",
        (json.dumps([{"name": "keep.png"}]), jid),
    )
    os.utime(gen.path("keep.png"), (old, old))
    r = housekeeping.sweep()
    assert "ref_old.png" in r["sample"] or r["files"] >= 1
    assert os.path.exists(gen.path("keep.png"))


def test_ratelimit_memory():
    k = "test-" + str(time.time())
    assert all(ratelimit.memory(k, 3, 60) for _ in range(3))
    assert not ratelimit.memory(k, 3, 60)


def test_audit():
    db.audit(1, "grant", 9, {"days": 30})
    assert (
        db.q("SELECT * FROM audit ORDER BY ts DESC LIMIT 1")[0]["action"]
        == "grant"
    )
