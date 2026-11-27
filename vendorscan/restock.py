"""Scarcity and restock research: should the buyer wait instead of paying a reseller premium?

Combines idealo's own price history (the product's normal price) with Tavily web
search (official store, restock or pre-order news, successor models). Web content
is untrusted data: it is quoted as evidence, never followed as instructions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from statistics import median

import httpx
from pydantic import BaseModel, Field

from .config import require
from .cost_engine import price_premium
from .models import Evidence, EvidenceStatus

TAVILY_URL = "https://api.tavily.com/search"
QUOTE_LIMIT = 300

# Words that suggest the product will be (or is again) available at normal price.
RESTOCK_TERMS = ("restock", "back in stock", "wieder verfügbar", "wieder lieferbar",
                 "pre-order", "preorder", "vorbestell", "new batch", "next sale")
SUCCESSOR_TERMS = ("successor", "next generation", "announced", "launch", "nachfolger")


class RestockReport(BaseModel):
    product_name: str
    normal_price: Decimal | None = None       # median of idealo price history
    lowest_current_price: Decimal | None = None
    premium: Decimal | None = None             # 0.30 = 30% above normal
    restock_signal: bool = False
    successor_signal: bool = False
    summary: str | None = None                 # Tavily's short answer, untrusted
    evidence: list[Evidence] = Field(default_factory=list)


def normal_price_from_history(history: dict) -> Decimal | None:
    """Median price from an idealo price-history response, or None if it has no prices.

    The response shape is not confirmed yet, so this looks for any list of points
    with a numeric ``price`` field and ignores everything else.
    """
    prices: list[Decimal] = []

    def walk(node):
        if isinstance(node, dict):
            value = node.get("price")
            if isinstance(value, (int, float, str)):
                try:
                    prices.append(Decimal(str(value)))
                except ArithmeticError:
                    pass
            for child in node.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(history)
    positive = [p for p in prices if p > 0]
    return Decimal(median(positive)).quantize(Decimal("0.01")) if positive else None


async def tavily_search(query: str, *, client: httpx.AsyncClient, max_results: int = 5,
                        topic: str = "general") -> dict:
    response = await client.post(TAVILY_URL, json={
        "query": query, "max_results": max_results, "topic": topic,
        "search_depth": "basic", "include_answer": True,
    }, headers={"Authorization": f"Bearer {require('TAVILY_API_KEY')}"}, timeout=20)
    response.raise_for_status()
    return response.json()


def _evidence_from(results: list[dict], field: str, terms: tuple[str, ...]) -> list[Evidence]:
    found = []
    now = datetime.now(timezone.utc)
    for item in results:
        text = f"{item.get('title', '')} {item.get('content', '')}"
        lowered = text.lower()
        hit = next((t for t in terms if t in lowered), None)
        if hit:
            start = max(lowered.index(hit) - 120, 0)
            found.append(Evidence(field=field, status=EvidenceStatus.AMBIGUOUS, url=item.get("url"),
                                  quote=text[start:start + QUOTE_LIMIT].strip(), retrieved_at=now))
    return found


async def research_restock(product_name: str, *, history: dict | None = None,
                           lowest_current_price: Decimal | None = None,
                           client: httpx.AsyncClient | None = None) -> RestockReport:
    """Collect evidence on whether waiting for a restock is a realistic option."""
    report = RestockReport(product_name=product_name, lowest_current_price=lowest_current_price)
    if history:
        report.normal_price = normal_price_from_history(history)
    if report.normal_price and lowest_current_price:
        report.premium = price_premium(lowest_current_price, report.normal_price)

    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        restock = await tavily_search(
            f"{product_name} official store sold out restock back in stock EU", client=client)
        successor = await tavily_search(f"{product_name} successor release date", client=client)
    finally:
        if owns_client:
            await client.aclose()

    report.summary = restock.get("answer")
    restock_evidence = _evidence_from(restock.get("results", []), "restock", RESTOCK_TERMS)
    successor_evidence = _evidence_from(successor.get("results", []), "successor", SUCCESSOR_TERMS)
    report.restock_signal = bool(restock_evidence)
    report.successor_signal = bool(successor_evidence)
    report.evidence = restock_evidence + successor_evidence
    return report
