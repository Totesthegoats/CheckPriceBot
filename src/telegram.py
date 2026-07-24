"""Minimal Telegram Bot API client: send_message, send_photo, get_updates."""
from __future__ import annotations

import os
from typing import Any

import httpx

API_BASE = "https://api.telegram.org"


class TelegramClient:
    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
        self._base = f"{API_BASE}/bot{self.token}"

    def send_message(self, text: str, chat_id: str | None = None) -> None:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                f"{self._base}/sendMessage",
                json={
                    "chat_id": chat_id or self.chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
            resp.raise_for_status()

    def send_photo(self, photo_path: str, caption: str = "", chat_id: str | None = None) -> None:
        with open(photo_path, "rb") as f, httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self._base}/sendPhoto",
                data={"chat_id": chat_id or self.chat_id, "caption": caption},
                files={"photo": f},
            )
            resp.raise_for_status()

    def get_updates(self, offset: int, timeout: int = 0) -> list[dict[str, Any]]:
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                f"{self._base}/getUpdates",
                params={"offset": offset, "timeout": timeout},
            )
            resp.raise_for_status()
            return resp.json().get("result", [])
