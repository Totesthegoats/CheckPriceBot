"""Gzipped page-diff snapshots and sale-keyword gating for page_diff items."""
from __future__ import annotations

import gzip
import os
import re

from selectolax.parser import HTMLParser

SALE_KEYWORDS = (
    "sale",
    "% off",
    "discount",
    "clearance",
    "reduced",
    "offer",
    "black friday",
    "midseason",
)


def clean_page_text(html: str) -> str:
    tree = HTMLParser(html)
    for tag in ("script", "style", "svg"):
        for node in tree.css(tag):
            node.decompose()
    for node in tree.css("*"):
        for attr in list(node.attributes.keys()):
            if attr != "href":
                node.attrs.pop(attr, None)
    text = tree.text(separator=" ", deep=True)
    return re.sub(r"\s+", " ", text).strip()


def found_sale_keywords(text: str) -> set[str]:
    lower = text.lower()
    return {kw for kw in SALE_KEYWORDS if kw in lower}


def _snapshot_path(item_id: int) -> str:
    return f"snapshots/{item_id}.txt.gz"


def load_snapshot(item_id: int) -> str | None:
    path = _snapshot_path(item_id)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        compressed = f.read()
    return gzip.decompress(compressed).decode("utf-8")


def save_snapshot(item_id: int, text: str) -> None:
    os.makedirs("snapshots", exist_ok=True)
    with open(_snapshot_path(item_id), "wb") as f:
        f.write(gzip.compress(text.encode("utf-8")))
