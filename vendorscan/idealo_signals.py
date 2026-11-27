"""idealo signals beyond the price list: 30-day price history and delivery times.

Missing data stays None. Price history is product-level context; it does not say
anything about a single offer.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from .idealo_normalize import parse_euro
from .models import Money


class PriceContext(BaseModel):
    min_price: Money
    max_price: Money
    avg_price: Money
    current_price: Money
    change_percent: Money | None = None  # over the period, as idealo reports it
    days: int | None = None
    points: int = 0


def price_context(history: dict | None) -> PriceContext | None:
    """Parse a ``get_product_price_history`` response, or None if it has no usable statistics."""
    trend = (history or {}).get("priceTrend") or {}
    stats = trend.get("statistics") or {}
    prices = {field: parse_euro(stats.get(key)) for field, key in (
        ("min_price", "minPrice"), ("max_price", "maxPrice"),
        ("avg_price", "avgPrice"), ("current_price", "currentPrice"))}
    if any(value is None for value in prices.values()):
        return None
    change = stats.get("priceChangePercent")
    return PriceContext(
        **prices,
        change_percent=None if change is None else Decimal(str(change)).quantize(Decimal("0.1")),
        days=None if trend.get("periodDays") is None else round(trend["periodDays"]),
        points=len(trend.get("history") or []))


def delivery_by_offer(raw_offers: list[dict]) -> dict[str, str]:
    """Offer key -> idealo's delivery text; offers without one are left out."""
    return {raw["key"]: text for raw in raw_offers
            if (text := (raw.get("delivery") or {}).get("deliveryText"))}
