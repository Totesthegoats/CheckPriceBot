"""Shared result type for the price extraction ladder."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtractedPrice:
    price_cents: int
    currency: str
    selector_used: str | None
