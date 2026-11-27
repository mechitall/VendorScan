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


def decide(ranked: list[tuple[Offer, CostBreakdown]], buyer: BuyerType, *,
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
        reasons.append(f"Best available offer is {premium:.0%} above idealo's lowest listed "
                       f"price (€{listed_lowest}); that cheaper offer is not available here.")
        if offer.seller.is_marketplace:
            reasons.append(f"Only a marketplace seller ({offer.seller.name}) is left.")
        if restock_signal:
            reasons.append("Web sources point to a restock or pre-order at the normal price.")
        if buyer is BuyerType.BUSINESS_VAT and offer.tax_status is TaxStatus.UNKNOWN:
            reasons.append("If you buy anyway: the seller's VAT treatment is unknown, so it costs your "
                           f"business €{cost.effective_cost_low}–€{cost.effective_cost_high} after VAT.")
        return Verdict(recommendation=Recommendation.WAIT, best_offer_id=offer.offer_id,
                       premium=premium, reasons=reasons)

    if budget is not None and cost.effective_cost_low > budget:
        return Verdict(recommendation=Recommendation.WAIT, best_offer_id=offer.offer_id, premium=premium,
                       reasons=[f"Even the best case (€{cost.effective_cost_low}) is over your budget (€{budget})."])

    if buyer is BuyerType.BUSINESS_VAT and offer.tax_status is TaxStatus.UNKNOWN:
        reasons.append("VAT treatment unknown: ask the seller for an invoice with VAT shown "
                       f"before buying (cost €{cost.effective_cost_low}–€{cost.effective_cost_high}).")
    if not cost.complete:
        reasons.append("Shipping or fees unknown: confirm the final price at checkout.")
    if not offer.seller.rating_count:
        reasons.append(f"{offer.seller.name} has no ratings on idealo.")
    if reasons:
        return Verdict(recommendation=Recommendation.VERIFY, best_offer_id=offer.offer_id,
                       premium=premium, reasons=reasons)

    reasons = [f"Best offer for you: {offer.seller.name} at €{cost.effective_cost_high}."]
    if cost.recoverable_vat:
        reasons.append(f"You pay €{cost.total_gross} upfront and can reclaim €{cost.recoverable_vat} VAT "
                       "(the seller confirms VAT on its invoices).")
    cheaper_gross = [(o, c) for o, c in ranked[1:] if c.total_gross < cost.total_gross]
    if cheaper_gross:
        other_offer, other = min(cheaper_gross, key=lambda pair: pair[1].total_gross)
        reasons.append(f"{other_offer.seller.name} is cheaper upfront (€{other.total_gross}) but does not "
                       f"confirm VAT invoices: €{other.effective_cost_low} if it issues one, "
                       f"€{other.effective_cost_high} if not. Ask them before choosing it.")
    return Verdict(recommendation=Recommendation.BUY, best_offer_id=offer.offer_id, premium=premium,
                   reasons=reasons)
