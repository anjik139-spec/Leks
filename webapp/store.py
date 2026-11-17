"""JSON storage for the Mini App."""

import json
import os
import threading
import time

PATH = os.environ.get("DATA_PATH", "data/state.json")
LOCK = threading.Lock()
OWNERS = {
    int(x)
    for x in os.environ.get("OWNER_IDS", "").replace(" ", "").split(",")
    if x
}


def _load():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    os.makedirs(os.path.dirname(PATH) or ".", exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, PATH)


def default_user():
    now = int(time.time())
    return {
        "balance": 5,
        "pro_until": 0,
        "stats": {"gen": 3, "photo": 1, "video": 1, "song": 1, "tpl": 0, "night": 0},
        "works": [
            {
                "id": "w1",
                "mode": "photo",
                "prompt": "Неоновый дождь над спящим городом",
                "style": "Неон",
                "aspect": "4:5",
                "hq": True,
                "seed": 1844674407,
                "ts": now - 86400,
            },
            {
                "id": "w2",
                "mode": "song",
                "prompt": "Лунная колыбельная для призрака",
                "style": "Кино",
                "mood": "Мечтательная",
                "tempo": 92,
                "dur": 10,
                "seed": 2844674407,
                "ts": now - 43200,
            },
            {
                "id": "w3",
                "mode": "video",
                "prompt": "Призрак плывёт над облаками на закате",
                "style": "Аниме",
                "aspect": "16:9",
                "dur": 6,
                "motion": 5,
                "seed": 3844674407,
                "ts": now - 3600,
            },
        ],
    }


def get(uid):
    with LOCK:
        d = _load()
        return d.get(str(uid), default_user())


def update(uid, fn):
    with LOCK:
        d = _load()
        u = d.get(str(uid), default_user())
        fn(u)
        d[str(uid)] = u
        _save(d)
        return u


def is_pro(uid, u=None):
    u = u or get(uid)
    return uid in OWNERS or u.get("pro_until", 0) > time.time()


def grant_pro(uid, days):
    update(
        uid,
        lambda u: u.__setitem__(
            "pro_until",
            max(u.get("pro_until", 0), time.time()) + days * 86400,
        ),
    )
