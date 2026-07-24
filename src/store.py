"""Load/save watchlist.json and state.json with atomic writes."""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any

WATCHLIST_PATH = "watchlist.json"
STATE_PATH = "state.json"

DEFAULT_WATCHLIST: dict[str, Any] = {"items": [], "next_id": 1}
DEFAULT_STATE: dict[str, Any] = {
    "telegram_offset": 0,
    "last_run": None,
    "pending": None,
    "proxy_requests_this_month": 0,
    "proxy_month": None,
}


def _atomic_write(path: str, data: dict[str, Any]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def load_watchlist(path: str = WATCHLIST_PATH) -> dict[str, Any]:
    if not os.path.exists(path):
        return json.loads(json.dumps(DEFAULT_WATCHLIST))
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_watchlist(data: dict[str, Any], path: str = WATCHLIST_PATH) -> None:
    _atomic_write(path, data)


def load_state(path: str = STATE_PATH) -> dict[str, Any]:
    if not os.path.exists(path):
        return json.loads(json.dumps(DEFAULT_STATE))
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for key, value in DEFAULT_STATE.items():
        data.setdefault(key, value)
    return data


def save_state(data: dict[str, Any], path: str = STATE_PATH) -> None:
    _atomic_write(path, data)


def next_item_id(watchlist: dict[str, Any]) -> int:
    item_id = watchlist["next_id"]
    watchlist["next_id"] = item_id + 1
    return item_id


def find_item(watchlist: dict[str, Any], item_id: int) -> dict[str, Any] | None:
    for item in watchlist["items"]:
        if item["id"] == item_id:
            return item
    return None


def remove_item(watchlist: dict[str, Any], item_id: int) -> bool:
    before = len(watchlist["items"])
    watchlist["items"] = [i for i in watchlist["items"] if i["id"] != item_id]
    return len(watchlist["items"]) < before
