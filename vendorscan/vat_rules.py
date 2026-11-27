"""How VendorScan decides an offer's VAT treatment: explicit rules, first match wins.

Evidence comes from three places, most specific first:
  1. the offer's own title on idealo's page (read by the browser extension),
  2. what the seller states on its own website (Tavily + Nebius, verbatim quotes),
  3. German VAT law for regular shops selling new goods.

| # | Evidence                                                   | Result                      |
|---|------------------------------------------------------------|-----------------------------|
| 1 | Offer title says "differenzbesteuert" / § 25a              | margin scheme, confirmed    |
| 1b| Offer title says "inkl. 19 % MwSt."                        | standard VAT, confirmed     |
| 2 | Seller states § 19 UStG (Kleinunternehmer)                 | no VAT, confirmed           |
| 3 | Seller states VAT on invoices / for business customers     | standard VAT, confirmed     |
| 4 | Seller states margin scheme, offer is used/refurbished     | margin scheme, likely       |
| 5 | Seller states margin scheme for part of its range, offer   | unknown: ask the seller     |
|   | title silent                                               |                             |
| 6 | Offer is used / refurbished / B-Ware                       | unknown: double-check       |
| 7 | Offer is new, seller is a regular shop (not a marketplace  | standard VAT, likely        |
|   | reseller), no margin hint anywhere. On idealo's page a     |                             |
|   | title without a used/refurbished marker counts as new:     |                             |
|   | idealo lists used offers under a separate "B-Ware" tab.    |                             |
| 8 | Anything else                                              | unknown                     |

Rule 7: a VAT-registered business selling to another business must issue an
invoice that shows the VAT (§ 14 Abs. 2 and Abs. 4 Nr. 8 UStG), and the margin
scheme only applies to goods bought without VAT (§ 25a Abs. 1 UStG), which new
retail stock normally is not. "Likely" is shown as such; it is not a guarantee.
"""
from __future__ import annotations

import re
from decimal import Decimal

from .models import Evidence, EvidenceStatus, Offer, TaxStatus
from .vendor_vat import VendorVat

STANDARD_RATE = Decimal("0.19")

_MARGIN = re.compile(r"differenz\s*-?\s*besteuer|§\s*25\s*a|margin\s*scheme", re.I)
_USED = re.compile(r"gebraucht|refurbished|generalüberholt|b-ware|wie neu|second hand|used\b|"
                   r"aufbereitet|renewed|zustand:\s*(sehr )?gut", re.I)
_VAT_19 = re.compile(r"(inkl\.?|inklusive|incl\.?)\s*(der\s*)?(gesetzl\.?\s*)?19\s*%\s*(mwst|ust|mehrwertsteuer)", re.I)
_NEW = re.compile(r"\bneu\b|neuware|neugerät|\bovp\b|originalverpackt|\bnew\b", re.I)


def _clean(title: str | None) -> str:
    # idealo inserts soft hyphens: "dif­fe­renz­be­steu­ert"
    return (title or "").replace("\xad", "").replace("­", "")


def condition_from_title(title: str | None) -> str | None:
    """"new", "used" or None (no title) from an offer title on idealo's page.

    idealo shows used and refurbished offers under a separate tab, so an offer title on
    the main list without a used marker is a new item.
    """
    text = _clean(title)
    if not text:
        return None
    if _USED.search(text):
        return "used"
    return "new"


def decide(offer: Offer, vendor: VendorVat | None) -> Offer:
    """Return a copy of the offer with tax status, confidence and the rule that decided it."""
    title = _clean(offer.title)
    condition = offer.condition or condition_from_title(title)
    seller_status = vendor.tax_status if vendor else TaxStatus.UNKNOWN
    seller_evidence = vendor.evidence if vendor else []
    title_evidence = [Evidence(field="tax_status", status=EvidenceStatus.CONFIRMED,
                               url=offer.offer_url, quote=f"idealo offer title: {offer.title}")]

    def result(status: TaxStatus, confidence: str | None, basis: str,
               evidence: list[Evidence]) -> Offer:
        flags = [f for f in offer.risk_flags if f != "TAX_UNVERIFIED"]
        if status is TaxStatus.UNKNOWN or confidence == "likely":
            flags.append("TAX_UNVERIFIED")
        return offer.model_copy(update={
            "tax_status": status, "tax_confidence": confidence, "tax_basis": basis,
            "condition": condition, "risk_flags": flags,
            "vat_rate": STANDARD_RATE if status is TaxStatus.STANDARD_VAT else None,
            "evidence": [e for e in offer.evidence if e.field != "tax_status"] + evidence})

    if _MARGIN.search(title):
        return result(TaxStatus.MARGIN_SCHEME, "confirmed",
                      "The offer title says it is sold under the margin scheme (§ 25a UStG): "
                      "no VAT is shown, so a business can't reclaim any.", title_evidence)
    if _VAT_19.search(title) and condition != "used":
        return result(TaxStatus.STANDARD_VAT, "confirmed",
                      "The offer title states the price includes 19 % VAT: regular taxation, so a "
                      "business buyer is entitled to an invoice showing it (§ 14 UStG).", title_evidence)
    if seller_status is TaxStatus.SMALL_BUSINESS:
        return result(TaxStatus.SMALL_BUSINESS, "confirmed",
                      "The seller states it charges no VAT (§ 19 UStG).", seller_evidence)
    if seller_status is TaxStatus.PRIVATE_SALE:
        return result(TaxStatus.PRIVATE_SALE, "confirmed", "Sold by a private person: no VAT.",
                      seller_evidence)
    if seller_status is TaxStatus.STANDARD_VAT and condition != "used":
        return result(TaxStatus.STANDARD_VAT, "confirmed",
                      "The seller states that its invoices show VAT.", seller_evidence)
    if seller_status is TaxStatus.MARGIN_SCHEME:
        if condition == "used":
            return result(TaxStatus.MARGIN_SCHEME, "likely",
                          "Used item from a seller that states it uses the margin scheme.",
                          seller_evidence)
        return result(TaxStatus.UNKNOWN, None,
                      "The seller uses the margin scheme for part of its range and this offer's "
                      "title doesn't say which applies: ask for an invoice with VAT shown.",
                      seller_evidence)
    if condition == "used":
        return result(TaxStatus.UNKNOWN, None,
                      "Used or refurbished items are often sold under the margin scheme: "
                      "confirm VAT with the seller before buying as a business.", [])
    if condition == "new" and offer.seller.is_marketplace is False:
        return result(TaxStatus.STANDARD_VAT, "likely",
                      "New item from a regular shop with no margin-scheme hint: a VAT-registered "
                      "shop must give business buyers an invoice showing VAT (§ 14 UStG).",
                      seller_evidence)
    return result(TaxStatus.UNKNOWN, None,
                  "No offer title or seller statement settles the VAT treatment.", seller_evidence)
