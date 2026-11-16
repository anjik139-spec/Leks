import os

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNERS = {int(x) for x in os.environ.get("OWNER_IDS", "0").split(",") if x.strip()}
WEBAPP_URL = os.environ.get("WEBAPP_URL", "http://localhost:8080").rstrip("/")
DATA = os.environ.get("DATA_DIR", "data")
BOT_API_URL = os.environ.get("BOT_API_URL", "https://api.telegram.org").rstrip("/")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

LLM_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
VISION_MODEL = os.environ.get("VISION_MODEL", LLM_MODEL)
LT_URL = os.environ.get("LT_URL", "")
OCR_LANGS = os.environ.get("OCR_LANGS", "rus+eng")
MAX_OCR_PAGES = int(os.environ.get("MAX_OCR_PAGES", "12"))
AUTO_PRIVATE = os.environ.get("AUTO_PRIVATE", "1") == "1"
AUTO_GROUP = os.environ.get("AUTO_GROUP", "0") == "1"
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "20"))
INTEL_CONCURRENCY = int(os.environ.get("INTEL_CONCURRENCY", "2"))

PHOTO_API_URL = os.environ.get("PHOTO_API_URL", "")
PHOTO_API_KEY = os.environ.get("PHOTO_API_KEY", "")
PHOTO_MODEL = os.environ.get("PHOTO_MODEL", "gpt-image-1")
VIDEO_API_URL = os.environ.get("VIDEO_API_URL", "")
VIDEO_API_KEY = os.environ.get("VIDEO_API_KEY", "")
SUNO_API_URL = os.environ.get("SUNO_API_URL", "")
SUNO_API_KEY = os.environ.get("SUNO_API_KEY", "")

REDIS_URL = os.environ.get("REDIS_URL", "")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
S3_KEY = os.environ.get("S3_KEY", "")
S3_SECRET = os.environ.get("S3_SECRET", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "lex")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
MAIL_FROM = os.environ.get("MAIL_FROM", SMTP_USER)

DAILY_BUDGET = float(os.environ.get("DAILY_BUDGET", "5"))
INIT_TTL = 3600
WORKERS = int(os.environ.get("WORKERS", "2"))
JOB_STALE_SEC = int(os.environ.get("JOB_STALE_SEC", "180"))
NOTIFY_DEFAULT = os.environ.get("NOTIFY_DEFAULT", "smart")
TTS_ENABLED = os.environ.get("TTS_ENABLED", "1") == "1"
TTS_VOICE = os.environ.get("TTS_VOICE", "ru-RU-DmitryNeural")
TTS_MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "600"))
EPHEMERAL_TTL_DAYS = int(os.environ.get("EPHEMERAL_TTL_DAYS", "7"))
ORPHAN_TTL_DAYS = int(os.environ.get("ORPHAN_TTL_DAYS", "3"))
EVENTS_TTL_DAYS = int(os.environ.get("EVENTS_TTL_DAYS", "90"))
CACHE_TTL_DAYS = int(os.environ.get("CACHE_TTL_DAYS", "30"))
MODERATION = os.environ.get(
    "MODERATION",
    "nsfw,porn, porno, порно, эротик, наркот, расчлен, beheading, gore, underage, малолет",
)
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

if SENTRY_DSN:
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.2)
    except Exception:
        pass
