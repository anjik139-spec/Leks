"""Keep a localhost.run tunnel alive and repoint the Telegram menu button."""

from __future__ import annotations

import logging
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = Path(os.getenv("WEBAPP_ENV", r"C:\bots\voicebot\.env"))
LOG_PATH = ROOT / "logs" / "tunnel.log"
URL_RE = re.compile(r"https://[a-z0-9]+\.app\.lhr\.life")
SSH = r"C:\WINDOWS\System32\OpenSSH\ssh.exe"
LOCAL_PORT = 8090
PROXY = "http://127.0.0.1:10809"

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("tunnel")


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def update_env(url: str) -> None:
    text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    if re.search(r"(?m)^WEBAPP_URL=", text):
        text = re.sub(r"(?m)^WEBAPP_URL=.*$", f"WEBAPP_URL={url}", text)
    else:
        text += f"\nWEBAPP_URL={url}\n"
    tmp = ENV_PATH.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(ENV_PATH)


def healthy(url: str) -> bool:
    try:
        response = httpx.get(
            f"{url}/api/health",
            timeout=10,
            trust_env=False,
            follow_redirects=True,
        )
        return response.status_code == 200 and response.json().get("ok") is True
    except Exception:
        return False


def set_menu(url: str) -> None:
    values = read_env()
    token = values.get("BOT_TOKEN", "")
    if not token:
        log.error("BOT_TOKEN missing")
        return
    try:
        with httpx.Client(timeout=30, proxy=PROXY) as client:
            for _ in range(2):
                response = client.post(
                    f"https://api.telegram.org/bot{token}/setChatMenuButton",
                    json={
                        "menu_button": {
                            "type": "web_app",
                            "text": "Студия",
                            "web_app": {"url": url},
                        }
                    },
                )
                if response.status_code != 200:
                    log.error("set_menu_http %s", response.status_code)
                    return
                time.sleep(2)
        log.info("menu_updated %s", url)
    except Exception as exc:
        log.exception("set_menu_failed: %s", exc)


def reader(proc: subprocess.Popen, lines: "queue.Queue[str]") -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def start_ssh() -> tuple[subprocess.Popen, str]:
    log.info("starting ssh tunnel")
    proc = subprocess.Popen(
        [
            SSH,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-R", f"80:localhost:{LOCAL_PORT}",
            "nokey@localhost.run",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=reader, args=(proc, lines), daemon=True).start()
    deadline = time.time() + 45
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            continue
        match = URL_RE.search(line)
        if match:
            return proc, match.group(0)
        log.info("ssh: %s", line[:160])
    proc.kill()
    raise RuntimeError("tunnel URL not found")


def main() -> None:
    current = ""
    while True:
        try:
            proc, url = start_ssh()
            log.info("tunnel_url %s", url)
            if url != current:
                update_env(url)
                set_menu(url)
                current = url
            tries = 0
            while tries < 40 and not healthy(url):
                tries += 1
                time.sleep(3)
            if tries >= 40:
                log.error("tunnel unhealthy %s", url)
                proc.kill()
                time.sleep(10)
                continue
            last_check = time.time()
            while proc.poll() is None:
                time.sleep(5)
                if time.time() - last_check > 30:
                    last_check = time.time()
                    if not healthy(url):
                        log.error("health lost %s", url)
                        proc.kill()
                        break
            log.warning("ssh exited")
        except Exception as exc:
            log.exception("tunnel_loop: %s", exc)
        time.sleep(8)


if __name__ == "__main__":
    main()
