import json
import os

try:
    from dotenv import load_dotenv

    load_dotenv(".env.lex")
    if os.environ.get("PYTEST"):
        load_dotenv(".env.brain")
    else:
        load_dotenv(".env.brain", override=True)
except Exception:
    pass


def _b(k, d="0"):
    return os.environ.get(k, d).strip() == "1"


def _i(k, d):
    try:
        return int(os.environ.get(k, d))
    except Exception:
        return d


def _f(k, d):
    try:
        return float(os.environ.get(k, d))
    except Exception:
        return d


OWNERS = {
    int(x)
    for x in os.environ.get("OWNER_IDS", "").replace(" ", "").split(",")
    if x.strip().isdigit()
}
ALLOW_OTHERS = _b("BRAIN_ALLOW_OTHERS", "0")
OTHERS_TIER = os.environ.get("BRAIN_OTHERS_TIER", "basic")

LLM_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
MODEL_BASIC = os.environ.get("MODEL_BASIC", "gpt-4o-mini")
MODEL_PRO = os.environ.get("MODEL_PRO", "gpt-4o")
MODEL_MAX = os.environ.get("MODEL_MAX", "o3")
REASONING = os.environ.get("REASONING", "high")
TIMEOUT = _i("BRAIN_TIMEOUT", 180)

_root = None
try:
    import config as _root
except Exception:
    _root = None

DAILY_BUDGET = _f(
    "DAILY_BUDGET_USD", getattr(_root, "DAILY_BUDGET", 2.0)
)
MAX_OCR_PAGES = _i(
    "MAX_OCR_PAGES", getattr(_root, "MAX_OCR_PAGES", 12)
)
LT_URL = os.environ.get("LT_URL", getattr(_root, "LT_URL", ""))
MODERATION = os.environ.get(
    "MODERATION",
    getattr(
        _root,
        "MODERATION",
        "nsfw,porn, porno, порно, эротик, наркот, расчлен, "
        "beheading, gore, underage, малолет",
    ),
)
try:
    PRICES = json.loads(os.environ.get("PRICE_MAP", "{}"))
except Exception:
    PRICES = {}
DEFAULT_PRICE = [_f("PRICE_IN", 0.0025), _f("PRICE_OUT", 0.010)]

CACHE_DOCS = _b("BRAIN_CACHE_DOCS", "0")
LOG_CONTENT = _b("BRAIN_LOG_CONTENT", "0")
STORE_TEXT = _b("BRAIN_STORE_TEXT", "0")
CTX_TTL = _i("BRAIN_CTX_TTL", 7200)
CTX_LIMIT = _i("BRAIN_CTX_LIMIT", 120000)
AUTO = _b("BRAIN_AUTO", "1")
MAX_FILE_MB = _i("BRAIN_MAX_FILE_MB", 20)
OCR_LANGS = os.environ.get("OCR_LANGS", "rus+eng")
DATA_DIR = os.environ.get("BRAIN_DATA_DIR", "brain_data")

TIERS = {
    "basic": {
        "models": [MODEL_BASIC],
        "tokens": 800,
        "temp": 0.3,
        "steps": 0,
        "critique": 0,
        "best": 1,
        "ctx": 6000,
        "tools": [],
        "reason": None,
    },
    "pro": {
        "models": [MODEL_PRO, MODEL_BASIC],
        "tokens": 1800,
        "temp": 0.2,
        "steps": 3,
        "critique": 1,
        "best": 1,
        "ctx": 18000,
        "tools": ["docs", "calc", "fields", "errors"],
        "reason": None,
    },
    "max": {
        "models": [MODEL_MAX, MODEL_PRO, MODEL_BASIC],
        "tokens": 3200,
        "temp": 0.15,
        "steps": 6,
        "critique": 2,
        "best": 2,
        "ctx": 45000,
        "tools": ["docs", "calc", "fields", "errors"],
        "reason": REASONING,
    },
}
ORDER = ["basic", "pro", "max"]

if not OWNERS:
    try:
        from config import OWNERS as _ROOT_OWNERS

        OWNERS = set(_ROOT_OWNERS)
    except Exception:
        pass
