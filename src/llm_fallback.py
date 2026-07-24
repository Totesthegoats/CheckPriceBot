"""LLM fallback for price extraction: last resort before asking the user."""
from __future__ import annotations

import json
import os

from selectolax.parser import HTMLParser

from src.extract_types import ExtractedPrice
from src.price_string import parse_price

MODEL = "claude-sonnet-4-6"
SYSTEM_PROMPT = (
    "You extract the current product price from raw HTML. "
    'Respond with ONLY JSON in the form {"price": "49.99", "currency": "EUR", '
    '"selector": "span.product-price"} and nothing else.'
)


def extract_llm(html: str, api_key: str | None = None) -> ExtractedPrice | None:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    tree = HTMLParser(html)
    for tag in ("script", "style", "svg"):
        for node in tree.css(tag):
            node.decompose()
    text = (tree.html or "")[:40000]

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    raw = response.content[0].text if response.content else ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    cents = parse_price(str(data.get("price", "")))
    if cents is None:
        return None
    selector = data.get("selector")
    if selector and tree.css_first(selector) is None:
        selector = None
    return ExtractedPrice(cents, data.get("currency", "EUR"), selector)
