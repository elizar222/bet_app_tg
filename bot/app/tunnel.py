"""Бесплатный https-туннель cloudflared, чтобы мини-апп открывался в Telegram с домашнего ПК.

Включается, если в .env WEBAPP_URL=auto. При запуске скачивает cloudflared
(один раз, в папку tools/), поднимает туннель и возвращает его адрес вида
https://xxx.trycloudflare.com. Адрес каждый раз новый — кнопка мини-аппа
в боте обновляется автоматически.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from app.config import BASE_DIR

log = logging.getLogger("tunnel")

TOOLS_DIR = BASE_DIR / "tools"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
RELEASES = "https://github.com/cloudflare/cloudflared/releases/latest/download/"


def _download_name() -> str | None:
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64" if machine in {"amd64", "x86_64"} else "386"
    if sys.platform == "win32":
        return f"cloudflared-windows-{arch}.exe"
    if sys.platform.startswith("linux"):
        return f"cloudflared-linux-{arch}"
    return None  # macOS: brew install cloudflared


def find_or_download() -> Path | None:
    local = TOOLS_DIR / ("cloudflared.exe" if sys.platform == "win32" else "cloudflared")
    if local.exists():
        return local
    found = shutil.which("cloudflared")
    if found:
        return Path(found)
    name = _download_name()
    if name is None:
        log.error("Установи cloudflared вручную: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        return None
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Скачиваю cloudflared (один раз, ~30 МБ)...")
    tmp = local.with_suffix(".part")
    urllib.request.urlretrieve(RELEASES + name, tmp)
    tmp.replace(local)
    if sys.platform != "win32":
        local.chmod(0o755)
    return local


class Tunnel:
    """cloudflared в отдельном процессе. Лог читается в потоке — так работает
    с любым event loop (на Windows run.py ставит Selector, где asyncio-подпроцессов нет)."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.url: str | None = None
        self._found = threading.Event()

    async def start(self, port: int, timeout: float = 60) -> str | None:
        try:
            binary = await asyncio.to_thread(find_or_download)
        except Exception as exc:  # noqa: BLE001
            log.error("Не удалось скачать cloudflared: %s", exc)
            return None
        if binary is None:
            return None

        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.proc = subprocess.Popen(
            [str(binary), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=flags,
        )
        threading.Thread(target=self._read_log, daemon=True).start()
        found = await asyncio.to_thread(self._found.wait, timeout)
        if not found:
            log.error("cloudflared не выдал адрес за %s с — проверь интернет", timeout)
            return None
        return self.url

    def _read_log(self) -> None:
        assert self.proc and self.proc.stderr
        for raw in self.proc.stderr:
            if self.url is None:
                match = URL_RE.search(raw.decode(errors="ignore"))
                if match:
                    self.url = match.group(0)
                    self._found.set()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
