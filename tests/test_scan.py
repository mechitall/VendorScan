import unittest
from decimal import Decimal
from pathlib import Path

from vendorscan.cost_engine import rank_offers
from vendorscan.idealo_normalize import offer_from_idealo, parse_euro
from vendorscan.models import BuyerType, Recommendation, TaxStatus
from vendorscan.orchestrator import replay
from vendorscan.restock import normal_price_from_history
from vendorscan.verdict import decide

D = Decimal
SNAPSHOT = Path(__file__).parent.parent / "fixtures" / "live_redmagic_astra2.json"


def raw_offer(price="999,00\xa0€", shipping="0,00\xa0€", marketplace=False, count=120):
    return {"key": "k1", "price": price, "minShippingCost": shipping,
            "relocatorUrl": "https://www.idealo.de/relocator/relocate?offerKey=k1",
            "shop": {"shopId": "1", "name": "shop.de", "merchantName": "Shop GmbH",
                     "rating": {"count": count, "avg": 4.6}, "isMarketplace": marketplace}}


class ParseEuroTests(unittest.TestCase):
    def test_german_format(self):
        self.assertEqual(parse_euro("1.307,98\xa0€"), D("1307.98"))
        self.assertEqual(parse_euro("899,00 €"), D("899.00"))
        self.assertEqual(parse_euro("0,00 €"), D("0.00"))

    def test_unknown_values(self):
        self.assertIsNone(parse_euro(None))
        self.assertIsNone(parse_euro("auf Anfrage"))


class NormalizeTests(unittest.TestCase):
    def test_marketplace_offer(self):
        offer = offer_from_idealo(raw_offer(marketplace=True, count=None), "Tablet")
        self.assertEqual(offer.item_gross, D("999.00"))
        self.assertEqual(offer.seller.name, "Shop GmbH (via shop.de)")
        self.assertEqual(offer.tax_status, TaxStatus.UNKNOWN)
        self.assertIn("MARKETPLACE_SELLER", offer.risk_flags)
        self.assertIn("NO_SELLER_RATINGS", offer.risk_flags)


class VerdictTests(unittest.TestCase):
    def decide_for(self, raw, buyer=BuyerType.PRIVATE, **kwargs):
        return decide(rank_offers([offer_from_idealo(raw, "Tablet")], buyer), buyer, **kwargs)

    def test_no_offers_means_wait(self):
        self.assertEqual(decide([], BuyerType.PRIVATE).recommendation, Recommendation.WAIT)

    def test_scarcity_premium_means_wait(self):
        verdict = self.decide_for(raw_offer("1.300,00 €", marketplace=True), listed_lowest=D("900"))
        self.assertEqual(verdict.recommendation, Recommendation.WAIT)
        self.assertEqual(verdict.premium, D("0.4444"))

    def test_normal_price_from_rated_shop_means_buy_for_private(self):
        verdict = self.decide_for(raw_offer("905,00 €"), listed_lowest=D("900"))
        self.assertEqual(verdict.recommendation, Recommendation.BUY)

    def test_business_must_verify_unknown_vat(self):
        verdict = self.decide_for(raw_offer("905,00 €"), BuyerType.BUSINESS_VAT, listed_lowest=D("900"))
        self.assertEqual(verdict.recommendation, Recommendation.VERIFY)

    def test_over_budget_means_wait(self):
        verdict = self.decide_for(raw_offer("905,00 €"), budget=D("800"))
        self.assertEqual(verdict.recommendation, Recommendation.WAIT)


class HistoryTests(unittest.TestCase):
    def test_median_of_history_points(self):
        history = {"priceTrend": {"points": [{"price": 900}, {"price": "950.5"}, {"price": 1000}]}}
        self.assertEqual(normal_price_from_history(history), D("950.50"))

    def test_no_history(self):
        self.assertIsNone(normal_price_from_history({"priceTrend": None}))


class LiveSnapshotTests(unittest.TestCase):
    """Replays the real RedMagic Astra 2 capture from 27 Nov 2026."""

    def test_every_buyer_is_told_to_wait(self):
        result = replay(SNAPSHOT)
        for buyer in BuyerType:
            self.assertEqual(result.verdicts[buyer].recommendation, Recommendation.WAIT, buyer)

    def test_business_sees_vat_range(self):
        cost = replay(SNAPSHOT).by_buyer[BuyerType.BUSINESS_VAT][0].cost
        self.assertEqual(cost.effective_cost_high, D("1307.98"))
        self.assertEqual(cost.effective_cost_low, D("1099.14"))


if __name__ == "__main__":
    unittest.main()
