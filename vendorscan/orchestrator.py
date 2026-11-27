"""One scan: idealo offers -> costs per buyer type -> restock research -> verdict.

Usage: python -m vendorscan.orchestrator "RedMagic Astra 2" --buyer business_vat
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from .config import load_env
from .cost_engine import price_premium, rank_offers
from .idealo_normalize import listed_lowest_price, offer_from_idealo, product_label
from .models import BuyerType, CostBreakdown, Offer
from .restock import RestockReport, research_restock
from .gaps import Gap, find_hidden_offer
from .vendor_vat import VendorVat, apply_vendor_vat, research_vendors
from .verdict import SCARCITY_PREMIUM, Verdict, decide


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
    vendors: dict[str, VendorVat] = Field(default_factory=dict)  # keyed by seller name
    gaps: list[Gap] = Field(default_factory=list)  # what idealo lacked and how Tavily filled it
    source: str = "live"  # "live" or "replay:<file>"


def build_result(query: str, product: dict, raw_offers: list[dict], *,
                 variants: list[str] | None = None, restock: RestockReport | None = None,
                 vendors: dict[str, VendorVat] | None = None, hidden: Gap | None = None,
                 budget: Decimal | None = None, source: str = "live") -> ScanResult:
    """Pure step after fetching: normalize, apply seller VAT research, cost per buyer, decide."""
    label = product_label(product)
    vendors = vendors or {}
    offers = [offer_from_idealo(raw, label) for raw in raw_offers]
    offers = [apply_vendor_vat(o, vendors[o.seller.name]) if o.seller.name in vendors else o
              for o in offers]
    listed = listed_lowest_price(product)
    result = ScanResult(query=query, product=label, product_url=product.get("url"),
                        listed_lowest=listed, total_offer_count=product.get("totalOfferCount"),
                        variants=variants or [], restock=restock, vendors=vendors, source=source)
    result.gaps = gap_report(offers, vendors, restock, hidden)
    for buyer in BuyerType:
        ranked = rank_offers(offers, buyer)
        result.by_buyer[buyer] = [RankedOffer(offer=o, cost=c) for o, c in ranked]
        result.verdicts[buyer] = decide(ranked, buyer, listed_lowest=listed, budget=budget,
                                        restock_signal=bool(restock and restock.restock_signal))
    return result


def scarcity_signal(product: dict, offers: list[Offer]) -> bool:
    """idealo hints at a shortage: no offers, very few, or all well above the listed lowest price."""
    if len(offers) <= 2:
        return True
    listed = listed_lowest_price(product)
    cheapest = min(o.item_gross for o in offers)
    return bool(listed and cheapest >= listed * (1 + SCARCITY_PREMIUM))


def gap_report(offers: list[Offer], vendors: dict[str, VendorVat],
               restock: RestockReport | None, hidden: Gap | None) -> list[Gap]:
    """List what idealo's data left open, and what (if anything) filled it."""
    gaps: list[Gap] = []
    if hidden:
        gaps.append(hidden)
    for name, vat in vendors.items():
        gaps.append(Gap(gap=f"VAT treatment of {name} (idealo has no VAT field)",
                        filled_by=vat.judged_by and f"tavily+nebius ({vat.judged_by.removeprefix('llm:')})",
                        finding=f"{vat.tax_status.value}: {vat.summary or ''}".strip(),
                        evidence=vat.evidence))
    for offer in offers:
        if not offer.seller.rating_count:
            gaps.append(Gap(gap=f"No idealo ratings for {offer.seller.name}",
                            finding="Left open: treat as an unrated seller."))
    if restock:
        if restock.official_price:
            finding = (f"Official store: {restock.official_price} {restock.official_currency or ''}"
                       f" ({restock.official_store_url or 'no URL'})").strip()
        else:
            finding = "No official price found."
        gaps.append(Gap(gap="Normal price and restock outlook (no idealo price history)",
                        filled_by=restock.judged_by and (f"tavily+nebius ({restock.judged_by.removeprefix('llm:')})"
                                                         if restock.judged_by.startswith("llm:") else "tavily"),
                        finding=finding, evidence=restock.evidence))
    return gaps


async def _hidden_offer_for(product: dict, offers: list[dict]) -> Gap | None:
    """Only when idealo's listed lowest price is below every offer the MCP returned."""
    listed = listed_lowest_price(product)
    prices = [o.item_gross for o in (offer_from_idealo(r, "") for r in offers)]
    if not listed or (prices and min(prices) <= listed):
        return None
    async with httpx.AsyncClient() as client:
        try:
            return await find_hidden_offer(product_label(product), listed, client)
        except (httpx.HTTPError, RuntimeError, ValueError) as error:
            return Gap(gap=f"idealo lists €{listed}, but no returned offer is that cheap",
                       finding=f"Search failed ({type(error).__name__}).")


async def _restock_for(product: dict, offers: list[dict]) -> RestockReport:
    lowest = min((o.item_gross for o in (offer_from_idealo(r, "") for r in offers)), default=None)
    restock = await research_restock(product_label(product), lowest_current_price=lowest)
    # No idealo price history for new or scarce products, so the normal price is
    # the lowest price idealo lists across all shops.
    restock.normal_price = listed_lowest_price(product)
    if restock.normal_price and lowest:
        restock.premium = price_premium(lowest, restock.normal_price)
    return restock


async def _none():
    return None


async def scan(query: str, *, variant: int = 0, budget: Decimal | None = None,
               with_restock: bool = True, with_vendors: bool = True,
               save: Path | None = None) -> ScanResult:
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

    # Restock research and seller VAT research are independent: run them together.
    normalized = [offer_from_idealo(r, product_label(product)) for r in offers]
    # Restock research only fills a gap when idealo's own data signals scarcity.
    with_restock = with_restock and scarcity_signal(product, normalized)
    restock, vendors, hidden = await asyncio.gather(
        _restock_for(product, offers) if with_restock else _none(),
        research_vendors(normalized) if with_vendors and normalized else _none(),
        _hidden_offer_for(product, offers) if with_restock else _none())
    variants = [product_label(p) for p in found]
    if save:
        snapshot = {
            "_label": "LIVE SNAPSHOT for demo replay. Captured from the idealo MCP, Tavily and Nebius; not edited.",
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "query": query, "variants": variants,
            "product": {k: v for k, v in product.items() if k != "productRef"},  # opaque, short-lived
            "offers": offers,
            "restock": restock.model_dump(mode="json") if restock else None,
            "vendors": {k: v.model_dump(mode="json") for k, v in (vendors or {}).items()},
            "hidden_offer": hidden.model_dump(mode="json") if hidden else None,
        }
        save.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1))
    return build_result(query, product, offers, variants=variants, restock=restock,
                        vendors=vendors, hidden=hidden, budget=budget)


def replay(path: Path, *, budget: Decimal | None = None) -> ScanResult:
    """Rebuild a result from a saved snapshot (no network), for demo backup and tests."""
    snap = json.loads(path.read_text())
    restock = RestockReport.model_validate(snap["restock"]) if snap.get("restock") else None
    vendors = {k: VendorVat.model_validate(v) for k, v in (snap.get("vendors") or {}).items()}
    hidden = Gap.model_validate(snap["hidden_offer"]) if snap.get("hidden_offer") else None
    return build_result(snap["query"], snap["product"], snap["offers"], variants=snap.get("variants"),
                        restock=restock, vendors=vendors, hidden=hidden, budget=budget, source=f"replay:{path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one VendorScan scan (read-only, no purchases)")
    parser.add_argument("query")
    parser.add_argument("--variant", type=int, default=0)
    parser.add_argument("--budget", type=Decimal)
    parser.add_argument("--no-restock", action="store_true")
    parser.add_argument("--no-vendors", action="store_true", help="skip seller VAT research")
    parser.add_argument("--save", type=Path, help="write a replayable snapshot to this file")
    args = parser.parse_args()
    result = asyncio.run(scan(args.query, variant=args.variant, budget=args.budget,
                              with_restock=not args.no_restock, with_vendors=not args.no_vendors,
                              save=args.save))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
