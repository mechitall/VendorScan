import json
import unittest
from decimal import Decimal
from pathlib import Path

from vendorscan.cost_engine import cost_for, price_premium, rank_offers, vat_included
from vendorscan.models import BuyerType, Offer, Seller, TaxStatus

FIXTURE = Path(__file__).parent.parent / "fixtures" / "demo_a_illustrative.json"
D = Decimal


def offer(item, shipping="0.00", fees="0.00", status=TaxStatus.STANDARD_VAT, rate="0.19"):
    return Offer(offer_id="x", product_name="p", seller=Seller(name="s"), item_gross=D(item),
                 shipping_gross=None if shipping is None else D(shipping),
                 mandatory_fees_gross=None if fees is None else D(fees),
                 tax_status=status, vat_rate=None if rate is None else D(rate))


def demo_offers():
    return [Offer.model_validate(o) for o in json.loads(FIXTURE.read_text())["offers"]]


class VatTests(unittest.TestCase):
    def test_vat_included_matches_plan_example(self):
        self.assertEqual(vat_included(D("999.00"), D("0.19")), D("159.50"))

    def test_reduced_rate(self):
        self.assertEqual(vat_included(D("107.00"), D("0.07")), D("7.00"))

    def test_negative_rate_rejected(self):
        with self.assertRaises(ValueError):
            vat_included(D("100"), D("-0.1"))


class CostForTests(unittest.TestCase):
    def test_business_reclaims_standard_vat_including_shipping(self):
        cost = cost_for(offer("999.00", shipping="11.90"), BuyerType.BUSINESS_VAT)
        self.assertEqual(cost.total_gross, D("1010.90"))
        self.assertEqual(cost.recoverable_vat, D("161.40"))
        self.assertEqual(cost.effective_cost_low, D("849.50"))
        self.assertEqual(cost.effective_cost_high, D("849.50"))
        self.assertTrue(cost.complete)

    def test_no_reclaim_for_margin_small_business_and_private_sellers(self):
        for status in (TaxStatus.MARGIN_SCHEME, TaxStatus.SMALL_BUSINESS, TaxStatus.PRIVATE_SALE):
            cost = cost_for(offer("900.00", status=status, rate=None), BuyerType.BUSINESS_VAT)
            self.assertEqual(cost.recoverable_vat, D("0.00"), status)
            self.assertEqual(cost.effective_cost_high, D("900.00"), status)

    def test_unknown_vat_gives_a_range_not_a_guess(self):
        cost = cost_for(offer("1190.00", status=TaxStatus.UNKNOWN, rate=None), BuyerType.BUSINESS_VAT)
        self.assertIsNone(cost.recoverable_vat)
        self.assertEqual(cost.effective_cost_low, D("1000.00"))
        self.assertEqual(cost.effective_cost_high, D("1190.00"))

    def test_standard_vat_with_unknown_rate_gives_a_range(self):
        cost = cost_for(offer("1190.00", rate=None), BuyerType.BUSINESS_VAT)
        self.assertIsNone(cost.recoverable_vat)
        self.assertLess(cost.effective_cost_low, cost.effective_cost_high)

    def test_private_and_small_business_pay_gross(self):
        for buyer in (BuyerType.PRIVATE, BuyerType.SMALL_BUSINESS):
            cost = cost_for(offer("999.00"), buyer)
            self.assertEqual(cost.recoverable_vat, D("0.00"))
            self.assertEqual(cost.effective_cost_high, D("999.00"))

    def test_unknown_shipping_or_fees_marks_total_incomplete(self):
        for shipping, fees in ((None, "0.00"), ("0.00", None)):
            cost = cost_for(offer("500.00", shipping=shipping, fees=fees), BuyerType.PRIVATE)
            self.assertFalse(cost.complete)
            self.assertEqual(cost.total_gross, D("500.00"))

    def test_money_serializes_as_strings(self):
        dumped = cost_for(offer("999.00"), BuyerType.BUSINESS_VAT).model_dump(mode="json")
        self.assertEqual(dumped["recoverable_vat"], "159.50")
        self.assertEqual(dumped["total_gross"], "999.00")


class RankingTests(unittest.TestCase):
    """Demo A: the same offers rank differently for business and private buyers."""

    def ranked_ids(self, buyer):
        return [o.offer_id for o, _ in rank_offers(demo_offers(), buyer)]

    def test_business_prefers_reclaimable_vat(self):
        ranked = rank_offers(demo_offers(), BuyerType.BUSINESS_VAT)
        self.assertEqual([o.offer_id for o, _ in ranked], ["demo-b", "demo-a", "demo-c"])
        self.assertEqual(ranked[0][1].effective_cost_high, D("839.50"))

    def test_private_buyer_prefers_lower_gross(self):
        self.assertEqual(self.ranked_ids(BuyerType.PRIVATE), ["demo-a", "demo-b", "demo-c"])

    def test_small_business_ranks_like_private(self):
        self.assertEqual(self.ranked_ids(BuyerType.SMALL_BUSINESS), ["demo-a", "demo-b", "demo-c"])

    def test_cheapest_listed_offer_with_unknowns_is_not_ranked_first(self):
        self.assertEqual(self.ranked_ids(BuyerType.BUSINESS_VAT)[-1], "demo-c")


class PremiumTests(unittest.TestCase):
    def test_reseller_premium(self):
        self.assertEqual(price_premium(D("1299.00"), D("999.00")), D("0.3003"))

    def test_below_reference_is_negative(self):
        self.assertEqual(price_premium(D("900"), D("1000")), D("-0.1000"))

    def test_reference_must_be_positive(self):
        with self.assertRaises(ValueError):
            price_premium(D("10"), D("0"))


if __name__ == "__main__":
    unittest.main()
