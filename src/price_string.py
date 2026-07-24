"""Parse human-formatted price strings into integer minor units (cents)."""
from __future__ import annotations

import re

_THOUSANDS_COMMA_DECIMAL_DOT = re.compile(r"^\d{1,3}(,\d{3})*\.\d{2}$")
_THOUSANDS_DOT_DECIMAL_COMMA = re.compile(r"^\d{1,3}(\.\d{3})*,\d{2}$")


def parse_price(raw: str) -> int | None:
    """Handle "€49,99", "1.299,00", "£1,299.00", "EUR 49.99", non-breaking spaces."""
    if not raw:
        return None
    s = raw.replace("\xa0", " ").replace(" ", " ").strip()
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None

    if _THOUSANDS_COMMA_DECIMAL_DOT.match(s):
        s = s.replace(",", "")
    elif _THOUSANDS_DOT_DECIMAL_COMMA.match(s):
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        parts = s.split(",")
        if len(parts[-1]) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")

    try:
        value = float(s)
    except ValueError:
        return None

    return round(value * 100)
