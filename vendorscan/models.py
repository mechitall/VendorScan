"""Shared data contract for VendorScan (see PLAN.md section 5).

Money is always ``Decimal`` and serializes as a string. ``None`` means
"unknown", never zero. Change these models only after telling the other author.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, Field, PlainSerializer

Money = Annotated[Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str)]


class TaxStatus(str, Enum):
    STANDARD_VAT = "standard_vat"      # Regular VAT, shown on the invoice
    MARGIN_SCHEME = "margin_scheme"    # Differenzbesteuerung, § 25a UStG
    SMALL_BUSINESS = "small_business"  # Seller under § 19 UStG, charges no VAT
    PRIVATE_SALE = "private_sale"      # Private seller, no VAT
    UNKNOWN = "unknown"


class BuyerType(str, Enum):
    PRIVATE = "private"
    BUSINESS_VAT = "business_vat"      # Can deduct input VAT (Vorsteuerabzug)
    SMALL_BUSINESS = "small_business"  # Kleinunternehmer: cannot deduct input VAT


class EvidenceStatus(str, Enum):
    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    CONFLICTING = "conflicting"


class Recommendation(str, Enum):
    BUY = "BUY"
    WAIT = "WAIT"
    VERIFY = "VERIFY"
    AVOID = "AVOID"


class Evidence(BaseModel):
    field: str
    status: EvidenceStatus
    url: Optional[str] = None
    quote: Optional[str] = None
    retrieved_at: Optional[datetime] = None


class Seller(BaseModel):
    name: str
    shop_id: Optional[str] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    is_marketplace: Optional[bool] = None


class Offer(BaseModel):
    """One normalized offer. Fields mirror PLAN.md; costs are filled by the cost engine."""

    offer_id: str
    product_name: str
    seller: Seller
    condition: Optional[str] = None
    currency: str = "EUR"
    offer_url: Optional[str] = None
    item_gross: Money
    shipping_gross: Optional[Money] = None
    mandatory_fees_gross: Optional[Money] = None
    tax_status: TaxStatus = TaxStatus.UNKNOWN
    vat_rate: Optional[Money] = None  # e.g. Decimal("0.19"); None if unknown
    risk_flags: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class CostBreakdown(BaseModel):
    """Result of costing one offer for one buyer type.

    ``total_gross`` is what the buyer pays upfront. When ``complete`` is False,
    shipping or fees are unknown and ``total_gross`` is only a lower bound.
    ``effective_cost_low``/``_high`` bracket the net cost after any VAT the
    buyer can reclaim; they differ only when the VAT treatment is unknown.
    """

    offer_id: str
    buyer_type: BuyerType
    total_gross: Money
    complete: bool
    recoverable_vat: Optional[Money]
    effective_cost_low: Money
    effective_cost_high: Money
    notes: list[str] = Field(default_factory=list)
