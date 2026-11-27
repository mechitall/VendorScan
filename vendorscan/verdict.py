"""Explainable BUY / WAIT / VERIFY / AVOID rules (PLAN.md section 8).

Rules, not a fraud score: every reason names the signal it came from.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from .cost_engine import price_premium
from .models import BuyerType, CostBreakdown, Offer, Recommendation, TaxStatus

# A marketplace price this far above idealo's lowest listed price counts as a scarcity premium.
SCARCITY_PREMIUM = Decimal("0.20")


class Verdict(BaseModel):
    recommendation: Recommendation
    best_offer_id: str | None = None
    premium: Decimal | None = None
    reasons: list[str] = Field(default_factory=list)
    # Seller name -> link to that offer, for every seller the reasons mention, so the
    # panel can turn names into links the buyer can check.
    links: dict[str, str] = Field(default_factory=dict)


def _decide(ranked: list[tuple[Offer, CostBreakdown]], buyer: BuyerType, *,
           listed_lowest: Decimal | None = None, restock_signal: bool = False,
           budget: Decimal | None = None) -> Verdict:
    if not ranked:
        return Verdict(recommendation=Recommendation.WAIT,
                       reasons=["No offers available right now."])

    offer, cost = ranked[0]
    reasons: list[str] = []
    premium = None
    if listed_lowest:
        premium = price_premium(cost.total_gross, listed_lowest)

    if premium is not None and premium >= SCARCITY_PREMIUM:
        # idealo's "from" price is normally a live offer on the same page, just from a shop
        # the idealo MCP does not share (Amazon, eBay, Otto). So the advice is: skip this one.
        reasons.append(f"Don't buy at €{cost.total_gross}: idealo lists this product from "
                       f"€{listed_lowest}, {premium:.0%} less.")
        reasons.append("That cheaper listing comes from a shop the idealo data feed doesn't share "
                       "(Amazon, eBay or Otto). Check it in idealo's offer list on this page.")
        if offer.seller.is_marketplace:
            reasons.append(f"The offer we can see is from a marketplace reseller ({offer.seller.name}).")
        if buyer is BuyerType.BUSINESS_VAT and offer.tax_status is TaxStatus.UNKNOWN:
            reasons.append("If you buy it anyway: the seller's VAT treatment is unknown, so it costs your "
                           f"business €{cost.effective_cost_low}–€{cost.effective_cost_high} after VAT.")
        if restock_signal:
            reasons.append("Web sources also point to a restock or pre-order at the normal price.")
        return Verdict(recommendation=Recommendation.AVOID, best_offer_id=offer.offer_id,
                       premium=premium, reasons=reasons)

    if budget is not None and cost.effective_cost_low > budget:
        return Verdict(recommendation=Recommendation.WAIT, best_offer_id=offer.offer_id, premium=premium,
                       reasons=[f"Even the best case (€{cost.effective_cost_low}) is over your budget (€{budget})."])

    if buyer is BuyerType.BUSINESS_VAT and offer.tax_status is TaxStatus.UNKNOWN:
        reasons.append(f"{offer.tax_basis or 'VAT treatment unknown.'} "
                       f"Cost €{cost.effective_cost_low}–€{cost.effective_cost_high}.")
    if not cost.complete:
        reasons.append("Shipping or fees unknown: confirm the final price at checkout.")
    if not offer.seller.rating_count:
        reasons.append(f"{offer.seller.name} has no ratings on idealo.")
        rated = [(o, c) for o, c in ranked[1:] if o.seller.rating_count]
        if rated:
            alt, alt_cost = rated[0]
            extra = alt_cost.effective_cost_high - cost.effective_cost_high
            reasons.append(f"Rated alternative: {alt.seller.name} at €{alt_cost.effective_cost_high}"
                           + (f" (+€{extra})." if extra > 0 else "."))
    if reasons:
        return Verdict(recommendation=Recommendation.VERIFY, best_offer_id=offer.offer_id,
                       premium=premium, reasons=reasons)

    reasons = [f"Best offer for you: {offer.seller.name} at €{cost.effective_cost_high}."]
    if cost.recoverable_vat:
        how = ("the seller confirms VAT on its invoices" if offer.tax_confidence == "confirmed"
               else "expected, not confirmed: ask for an invoice with VAT shown")
        reasons.append(f"You pay €{cost.total_gross} upfront and can reclaim €{cost.recoverable_vat} VAT ({how}).")
        if offer.tax_confidence == "likely" and offer.tax_basis:
            reasons.append(offer.tax_basis)
    cheaper_gross = [(o, c) for o, c in ranked[1:] if c.total_gross < cost.total_gross]
    if cheaper_gross:
        other_offer, other = min(cheaper_gross, key=lambda pair: pair[1].total_gross)
        why = ("sells it under the margin scheme, so there is no VAT to reclaim"
               if other_offer.tax_status is TaxStatus.MARGIN_SCHEME
               else f"doesn't confirm VAT invoices: €{other.effective_cost_low} if it issues one, "
                    f"€{other.effective_cost_high} if not")
        reasons.append(f"{other_offer.seller.name} is cheaper upfront (€{other.total_gross}) but {why}.")
    return Verdict(recommendation=Recommendation.BUY, best_offer_id=offer.offer_id, premium=premium,
                   reasons=reasons)


def decide(ranked: list[tuple[Offer, CostBreakdown]], buyer: BuyerType, **kwargs) -> Verdict:
    verdict = _decide(ranked, buyer, **kwargs)
    text = " ".join(verdict.reasons)
    for offer, _ in ranked:
        name = offer.seller.name
        if name in text and offer.offer_url and name not in verdict.links:
            verdict.links[name] = offer.offer_url
    return verdict
