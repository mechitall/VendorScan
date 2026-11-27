"""One scan: idealo offers -> costs per buyer type -> restock research -> verdict.

Usage: python -m vendorscan.orchestrator "RedMagic Astra 2" --buyer business_vat
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
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
from .gaps import Gap, find_hidden_offer, find_reputations
from . import vat_rules
from .vendor_vat import VendorVat, research_vendors
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
    reputations: dict[str, Gap] = Field(default_factory=dict)  # unrated sellers, keyed by name
    exact_match: bool = True  # False: the page's exact variant isn't in idealo's data feed
    source: str = "live"  # "live" or "replay:<file>"


def build_result(query: str, product: dict, raw_offers: list[dict], *,
                 variants: list[str] | None = None, restock: RestockReport | None = None,
                 vendors: dict[str, VendorVat] | None = None, hidden: Gap | None = None,
                 reputations: dict[str, Gap] | None = None,
                 offer_titles: dict[str, str] | None = None, budget: Decimal | None = None, source: str = "live") -> ScanResult:
    """Pure step after fetching: normalize, apply seller VAT research, cost per buyer, decide."""
    label = product_label(product)
    vendors = vendors or {}
    titles = offer_titles or {}
    offers = [offer_from_idealo(raw, label).model_copy(update={"title": titles.get(raw.get("key"))})
              for raw in raw_offers]
    offers = [vat_rules.decide(o, vendors.get(o.seller.name)) for o in offers]
    listed = listed_lowest_price(product)
    result = ScanResult(query=query, product=label, product_url=product.get("url"),
                        listed_lowest=listed, total_offer_count=product.get("totalOfferCount"),
                        variants=variants or [], restock=restock, vendors=vendors, source=source)
    result.reputations = reputations or {}
    result.gaps = gap_report(offers, vendors, restock, hidden, result.reputations)
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
               restock: RestockReport | None, hidden: Gap | None,
               reputations: dict[str, Gap] | None = None) -> list[Gap]:
    """List what idealo's data left open, and what (if anything) filled it."""
    gaps: list[Gap] = []
    if hidden:
        gaps.append(hidden)
    for name, vat in vendors.items():
        gaps.append(Gap(gap=f"VAT treatment of {name} (idealo has no VAT field)",
                        filled_by=(f"tavily+nebius ({vat.judged_by.removeprefix('llm:')})"
                                   if (vat.judged_by or "").startswith("llm:") else vat.judged_by),
                        finding=f"{vat.tax_status.value}: {vat.summary or ''}".strip(),
                        evidence=vat.evidence))
    seen: set[str] = set()
    for offer in offers:
        name = offer.seller.name
        if not offer.seller.rating_count and name not in seen:
            seen.add(name)
            gaps.append((reputations or {}).get(name) or Gap(
                gap=f"No idealo ratings for {name}", finding="Not searched: treat as an unrated seller."))
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


def product_id_from_url(url: str | None) -> str | None:
    """idealo product id from a product URL: ".../OffersOfProduct/214218295_-astra-2..." -> "214218295"."""
    match = re.search(r"OffersOfProduct/(\d+)", url or "")
    return match.group(1) if match else None


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9äöüß]+", (text or "").lower()) if len(t) > 1}


def closest_product(found: list[dict], wanted: str) -> dict | None:
    """Result whose name and URL share the most words with what the page says."""
    want = _tokens(wanted)
    if not found or not want:
        return None
    def score(p: dict) -> float:
        have = _tokens(f"{product_label(p)} {p.get('url', '')}")
        return len(want & have) / len(want)
    best = max(found, key=score)
    return best if score(best) >= 0.5 else None


async def _find_product(idealo, queries: list[str], product_id: str | None,
                        variant: int) -> tuple[dict | None, list[dict], bool]:
    """Try each query until the exact idealo product id shows up.

    Returns (product, results of the first query, exact match?). Never raises inside
    the MCP session, so errors stay readable instead of being wrapped by anyio.
    """
    first: list[dict] = []
    for query in queries:
        found = (await idealo.search(query)).get("results", [])
        first = first or found
        if not product_id:
            return (found[variant] if 0 <= variant < len(found) else None), found, True
        for p in found:
            if product_id_from_url(p.get("url")) == product_id:
                return p, found, True
    # idealo's data feed may not carry this exact variant: fall back to the closest one.
    pool = first
    return closest_product(pool, " ".join(queries)), first, False


def queries_for(name: str, slug: str | None = None, title: str | None = None) -> list[str]:
    """Search texts from what the page shows, most specific first, without duplicates."""
    candidates = []
    if title:
        candidates.append(re.split(r"\s+ab\s+[\d.,]+\s*€|\s+\|\s+", title)[0])
    if slug:
        words = [w for w in re.split(r"[-_]+", slug) if w]
        if words and words[0].isdigit() and len(words[0]) >= 6:
            words = words[1:]  # leading idealo product id, not part of the name
        candidates.append(" ".join(words))
    candidates.append(name)
    seen, result = set(), []
    for c in (c.strip() for c in candidates):
        if len(c) >= 2 and c.lower() not in seen:
            seen.add(c.lower())
            result.append(c)
    return result


async def scan(query: str, *, variant: int = 0, budget: Decimal | None = None,
               with_restock: bool = True, with_vendors: bool = True,
               save: Path | None = None, product_id: str | None = None,
               slug: str | None = None, title: str | None = None,
               offer_titles: dict[str, str] | None = None) -> ScanResult:
    from idealo_client import connect

    load_env()
    queries = queries_for(query, slug, title)
    if not queries:
        raise LookupError("No product name on this page to search for.")
    offers: list[dict] = []
    async with connect() as idealo:
        product, found, exact = await _find_product(idealo, queries, product_id, variant)
        if product:
            offers = (await idealo.offers(product))["offers"]
    if not product:
        raise LookupError(f"idealo's data feed has no product matching {queries[0]!r}.")

    # Restock research and seller VAT research are independent: run them together.
    normalized = [offer_from_idealo(r, product_label(product)) for r in offers]
    offer_titles = {k: v for k, v in (offer_titles or {}).items() if k in {o.offer_id for o in normalized}}
    # Restock research only fills a gap when idealo's own data signals scarcity.
    with_restock = with_restock and scarcity_signal(product, normalized)
    unrated = list(dict.fromkeys(o.seller.name for o in sorted(normalized, key=lambda o: o.item_gross)
                                 if not o.seller.rating_count))
    restock, vendors, hidden, reputations = await asyncio.gather(
        _restock_for(product, offers) if with_restock else _none(),
        research_vendors(normalized) if with_vendors and normalized else _none(),
        _hidden_offer_for(product, offers) if with_restock else _none(),
        find_reputations(unrated) if with_vendors and unrated else _none())
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
            "reputations": {k: v.model_dump(mode="json") for k, v in (reputations or {}).items()},
            "offer_titles": offer_titles,
        }
        save.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1))
    result = build_result(query, product, offers, variants=variants, restock=restock,
                          vendors=vendors, hidden=hidden, reputations=reputations,
                          offer_titles=offer_titles, budget=budget)
    result.exact_match = exact
    return result


def replay(path: Path, *, budget: Decimal | None = None) -> ScanResult:
    """Rebuild a result from a saved snapshot (no network), for demo backup and tests."""
    snap = json.loads(path.read_text())
    restock = RestockReport.model_validate(snap["restock"]) if snap.get("restock") else None
    vendors = {k: VendorVat.model_validate(v) for k, v in (snap.get("vendors") or {}).items()}
    hidden = Gap.model_validate(snap["hidden_offer"]) if snap.get("hidden_offer") else None
    reputations = {k: Gap.model_validate(v) for k, v in (snap.get("reputations") or {}).items()}
    return build_result(snap["query"], snap["product"], snap["offers"], variants=snap.get("variants"),
                        restock=restock, vendors=vendors, hidden=hidden, reputations=reputations,
                        offer_titles=snap.get("offer_titles"), budget=budget, source=f"replay:{path.name}")


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
