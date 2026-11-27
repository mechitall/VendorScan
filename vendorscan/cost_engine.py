"""Deterministic purchase-cost engine (German domestic purchases, EUR).

Estimates what an offer costs a given buyer type. It is not tax advice: input
VAT deduction still needs a compliant invoice and other legal conditions.
Unknown values stay unknown; they widen the cost range instead of becoming zero.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .models import BuyerType, CostBreakdown, Offer, TaxStatus

CENT = Decimal("0.01")
# Highest German VAT rate. Used only for the optimistic bound when the rate is unknown.
DEFAULT_STANDARD_RATE = Decimal("0.19")

_NO_VAT_STATUSES = {TaxStatus.MARGIN_SCHEME, TaxStatus.SMALL_BUSINESS, TaxStatus.PRIVATE_SALE}


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def vat_included(gross: Decimal, rate: Decimal) -> Decimal:
    """VAT contained in a gross amount at ``rate`` (e.g. 999.00 at 0.19 -> 159.50)."""
    if rate < 0:
        raise ValueError("VAT rate must not be negative")
    return _cents(gross - gross / (Decimal(1) + rate))


def cost_for(offer: Offer, buyer: BuyerType) -> CostBreakdown:
    """Cost one offer for one buyer type."""
    notes: list[str] = []
    total = offer.item_gross
    complete = True
    for label, amount in (("shipping", offer.shipping_gross),
                          ("mandatory fees", offer.mandatory_fees_gross)):
        if amount is None:
            complete = False
            notes.append(f"{label.capitalize()} unknown: total is a lower bound.")
        else:
            total += amount
    total = _cents(total)

    if buyer is not BuyerType.BUSINESS_VAT:
        if buyer is BuyerType.SMALL_BUSINESS:
            notes.append("Small business under § 19 UStG: input VAT is not deductible.")
        return CostBreakdown(offer_id=offer.offer_id, buyer_type=buyer, total_gross=total,
                             complete=complete, recoverable_vat=Decimal("0.00"),
                             effective_cost_low=total, effective_cost_high=total, notes=notes)

    status = offer.tax_status
    if status in _NO_VAT_STATUSES:
        notes.append(f"No separately stated VAT ({status.value}): nothing to reclaim.")
        recoverable: Decimal | None = Decimal("0.00")
        low = high = total
    elif status is TaxStatus.STANDARD_VAT and offer.vat_rate is not None:
        recoverable = vat_included(total, offer.vat_rate)
        notes.append("Reclaimable only with a compliant invoice showing VAT.")
        low = high = total - recoverable
    else:
        # Unknown treatment, or standard VAT at an unknown rate: give a range.
        reason = "VAT rate unknown" if status is TaxStatus.STANDARD_VAT else "VAT treatment unknown"
        notes.append(f"{reason}: cost lies between full reclaim at 19% and no reclaim.")
        recoverable = None
        low = total - vat_included(total, DEFAULT_STANDARD_RATE)
        high = total

    return CostBreakdown(offer_id=offer.offer_id, buyer_type=buyer, total_gross=total,
                         complete=complete, recoverable_vat=recoverable,
                         effective_cost_low=_cents(low), effective_cost_high=_cents(high),
                         notes=notes)


def rank_offers(offers: list[Offer], buyer: BuyerType) -> list[tuple[Offer, CostBreakdown]]:
    """Order offers for a buyer: complete costs first, then by worst-case cost.

    Ranking on the high bound means an offer with unknown VAT never outranks one
    whose cost is confirmed just because its optimistic estimate looks cheaper.
    """
    costed = [(offer, cost_for(offer, buyer)) for offer in offers]
    return sorted(costed, key=lambda pair: (not pair[1].complete,
                                            pair[1].effective_cost_high,
                                            pair[1].effective_cost_low))


def price_premium(price: Decimal, reference: Decimal) -> Decimal:
    """How far ``price`` sits above ``reference`` as a fraction (0.25 = 25% more).

    Use it to compare a reseller price with the official list price or the
    product's normal price from idealo's price history.
    """
    if reference <= 0:
        raise ValueError("reference price must be positive")
    return ((price - reference) / reference).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
