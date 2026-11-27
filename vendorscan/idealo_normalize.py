"""Turn raw idealo MCP responses into VendorScan models.

Field meanings confirmed against live responses on 2026-11-27:
- prices are German-formatted strings such as ``"1.307,98 €"``;
- ``minShippingCost`` is a separate string and is added to ``price``;
- search results carry ``price``: the lowest price idealo lists for the product,
  which can come from shops the MCP does not return (Amazon, eBay, Otto).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .models import Evidence, EvidenceStatus, Offer, Seller, TaxStatus

_NUMBER = re.compile(r"-?[\d.]+(?:,\d+)?")


def parse_euro(value: str | int | float | None) -> Decimal | None:
    """``"1.307,98 €"`` -> ``Decimal("1307.98")``; None or unparseable -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    match = _NUMBER.search(value.replace("\xa0", " "))
    if not match:
        return None
    try:
        return Decimal(match.group().replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def listed_lowest_price(search_result: dict) -> Decimal | None:
    """Lowest price idealo shows for a product in search, across all its shops."""
    return parse_euro(search_result.get("price"))


def offer_from_idealo(raw: dict, product_name: str) -> Offer:
    shop = raw.get("shop") or {}
    rating = shop.get("rating") or {}
    is_marketplace = shop.get("isMarketplace")
    seller_name = shop.get("merchantName") or shop.get("name") or "Unknown seller"
    if is_marketplace and shop.get("name") and shop.get("name") != seller_name:
        seller_name = f"{seller_name} (via {shop['name']})"

    flags = []
    if is_marketplace:
        flags.append("MARKETPLACE_SELLER")
    if not rating.get("count"):
        flags.append("NO_SELLER_RATINGS")
    flags.append("TAX_UNVERIFIED")  # idealo has no VAT-treatment field

    return Offer(
        offer_id=raw["key"],
        product_name=product_name,
        seller=Seller(name=seller_name, shop_id=shop.get("shopId"), rating=rating.get("avg"),
                      rating_count=rating.get("count"), is_marketplace=is_marketplace,
                      domain=shop.get("name") if "." in (shop.get("name") or "") else None),
        offer_url=raw.get("relocatorUrl"),
        item_gross=parse_euro(raw.get("price")),
        shipping_gross=parse_euro(raw.get("minShippingCost")),
        # German law (§ 270a BGB) bans surcharges for SEPA and card payments,
        # so an offer paid that way has no mandatory extra fee.
        mandatory_fees_gross=Decimal("0.00"),
        tax_status=TaxStatus.UNKNOWN,
        risk_flags=flags,
        evidence=[Evidence(field="tax_status", status=EvidenceStatus.MISSING, url=raw.get("relocatorUrl"))],
    )


def product_label(search_result: dict) -> str:
    name = search_result.get("name", "")
    delta = search_result.get("nameDelta")
    return f"{name} {delta}".strip() if delta else name
