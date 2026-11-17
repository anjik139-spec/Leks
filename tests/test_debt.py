import json
import time

import brainkit
import core
import db
import doclib
import intel
from brainkit import config as bcfg
from brainkit import core as bc
from brainkit import documents as bd
from brainkit import store as bs
from brainkit import tools as bt


def test_single_ledger():
    b0 = db.spend_today()
    bs.spend_add("test-model", 0.25, 100)
    assert abs(db.spend_today() - b0 - 0.25) < 1e-6
    assert abs(bs.spend_today() - db.spend_today()) < 1e-6
    assert bs.budget_left() <= bcfg.DAILY_BUDGET
    assert any(
        r["provider"] == "brain:test-model"
        for r in db.spend_breakdown(1)
    )


def test_single_doclib():
    assert intel.extract is doclib.extract is bd.extract
    assert intel.retrieve is doclib.retrieve is bt.retrieve
    assert intel.local_errors is doclib.local_errors
    o = doclib.extract(
        "a.txt",
        "Итого: 100\nПозиции: 60 и 30\nИНН 7701234561".encode(),
    )
    assert o["hash"] and o["meta"]["size"] > 0
    e = doclib.local_errors(o["text"], [])
    assert any("ИНН" in x["title"] for x in e)


def test_idempotency():
    k = "k" + str(time.time_ns())
    assert db.idem_claim(1, k) is None
    assert db.idem_claim(1, k) == {"__inflight": True}
    db.idem_done(1, k, {"job": "j1", "cached": False})
    assert db.idem_claim(1, k)["job"] == "j1"
    db.idem_drop(1, k)
    assert db.idem_claim(1, k) is None


def test_lock():
    n = "test:lock"
    assert db.lock_acquire(n, "A", 30)
    assert not db.lock_acquire(n, "B", 30)
    assert db.lock_holder(n)["owner"] == "A"
    db.lock_release(n, "A")
    assert db.lock_acquire(n, "B", 30)
    db.lock_release(n, "B")


def test_single_tier_source():
    assert bc.set_tier(1, "pro")[0]
    assert bc.tier_for(1) == "pro"
    assert bs.setting(1, "tier") == "pro"
    assert db.user(1).get("brain", "") == ""
    bc.set_tier(1, "max")
    db.upd(2, pro_until=0)
    assert bc.tier_for(2) == "basic"
    assert not bc.set_tier(2, "max")[0]
