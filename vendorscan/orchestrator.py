"""One scan: idealo offers -> costs per buyer type -> restock research -> verdict.

Usage: python -m vendorscan.orchestrator "RedMagic Astra 2" --buyer business_vat
"""
from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

from .config import load_env
from .cost_engine import price_premium, rank_offers
from .idealo_normalize import listed_lowest_price, offer_from_idealo, product_label
from .models import BuyerType, CostBreakdown, Offer
from .restock import RestockReport, research_restock
from .verdict import Verdict, decide


class RankedOffer(BaseModel):
    offer: Offer
    cost: CostBreakdown


class ScanResult(BaseModel):
    query: str
    product: str
    product_url: str | None = None
    listed_lowest: Decimal | None = None
    total_offer_count: int | None = None
    variants: list[str] = Field(default_factory=list)
    by_buyer: dict[BuyerType, list[RankedOffer]] = Field(default_factory=dict)
    verdicts: dict[BuyerType, Verdict] = Field(default_factory=dict)
    restock: RestockReport | None = None
    source: str = "live"  # "live" or "replay:<file>"


def build_result(query: str, product: dict, raw_offers: list[dict], *,
                 variants: list[str] | None = None, restock: RestockReport | None = None,
                 budget: Decimal | None = None, source: str = "live") -> ScanResult:
    """Pure step after fetching: normalize, cost for every buyer type, decide."""
    label = product_label(product)
    offers = [offer_from_idealo(raw, label) for raw in raw_offers]
    listed = listed_lowest_price(product)
    result = ScanResult(query=query, product=label, product_url=product.get("url"),
                        listed_lowest=listed, total_offer_count=product.get("totalOfferCount"),
                        variants=variants or [], restock=restock, source=source)
    for buyer in BuyerType:
        ranked = rank_offers(offers, buyer)
        result.by_buyer[buyer] = [RankedOffer(offer=o, cost=c) for o, c in ranked]
        result.verdicts[buyer] = decide(ranked, buyer, listed_lowest=listed, budget=budget,
                                        restock_signal=bool(restock and restock.restock_signal))
    return result


async def scan(query: str, *, variant: int = 0, budget: Decimal | None = None,
               with_restock: bool = True) -> ScanResult:
    from idealo_client import connect

    load_env()
    async with connect() as idealo:
        found = (await idealo.search(query)).get("results", [])
        if not found:
            raise LookupError(f"idealo found no product for {query!r}")
        if not 0 <= variant < len(found):
            raise ValueError(f"variant must be between 0 and {len(found) - 1}")
        product = found[variant]
        offers = (await idealo.offers(product))["offers"]

    restock = None
    if with_restock:
        lowest = min((o.item_gross for o in (offer_from_idealo(r, "") for r in offers)), default=None)
        restock = await research_restock(product_label(product), lowest_current_price=lowest)
        # No idealo price history for new or scarce products, so the normal price is
        # the lowest price idealo lists across all shops.
        restock.normal_price = listed_lowest_price(product)
        if restock.normal_price and lowest:
            restock.premium = price_premium(lowest, restock.normal_price)
    return build_result(query, product, offers, variants=[product_label(p) for p in found],
                        restock=restock, budget=budget)


def replay(path: Path, *, budget: Decimal | None = None) -> ScanResult:
    """Rebuild a result from a saved snapshot (no network), for demo backup and tests."""
    snap = json.loads(path.read_text())
    restock = RestockReport.model_validate(snap["restock"]) if snap.get("restock") else None
    return build_result(snap["query"], snap["product"], snap["offers"], variants=snap.get("variants"),
                        restock=restock, budget=budget, source=f"replay:{path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one VendorScan scan (read-only, no purchases)")
    parser.add_argument("query")
    parser.add_argument("--variant", type=int, default=0)
    parser.add_argument("--budget", type=Decimal)
    parser.add_argument("--no-restock", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(scan(args.query, variant=args.variant, budget=args.budget,
                              with_restock=not args.no_restock))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
