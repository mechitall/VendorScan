"""idealo's price history and delivery data must reach the result and the model."""
import json
import unittest
from decimal import Decimal
from pathlib import Path

from vendorscan.idealo_signals import delivery_by_offer, price_context
from vendorscan.models import BuyerType
from vendorscan.next_action import build_facts
from vendorscan.orchestrator import build_result

SNAP = json.loads((Path(__file__).resolve().parent.parent / "fixtures" / "live_macbook_air_m4.json")
                  .read_text(encoding="utf-8"))
# Shape of get_product_price_history as returned live on 27 Nov 2026 (German price strings).
HISTORY = {"priceTrend": {"history": [{}] * 31, "periodDays": 30, "statistics": {
    "minPrice": "1.679,00 €", "maxPrice": "1.829,00 €", "avgPrice": "1.733,19 €",
    "currentPrice": "1.829,00 €", "priceChangePercent": 7.651559741024132}}}


class PriceContextTests(unittest.TestCase):
    def test_german_prices_are_read_as_decimals(self):
        context = price_context(HISTORY)
        self.assertEqual((context.min_price, context.avg_price, context.current_price),
                         (Decimal("1679.00"), Decimal("1733.19"), Decimal("1829.00")))
        self.assertEqual(context.change_percent, Decimal("7.7"))
        self.assertEqual(context.points, 31)

    def test_fractional_period_from_the_live_feed_is_accepted(self):
        """idealo returns periodDays as a fraction; this value is from a live response."""
        history = {"priceTrend": {**HISTORY["priceTrend"], "periodDays": 29.7}}
        self.assertEqual(price_context(history).days, round(29.7))

    def test_missing_history_is_none_not_zero(self):
        self.assertIsNone(price_context({"priceTrend": None}))
        self.assertIsNone(price_context(None))


class SignalFactTests(unittest.TestCase):
    def facts(self, history=None):
        result = build_result(SNAP["query"], SNAP["product"], SNAP["offers"],
                              price_history=price_context(history))
        return {f.code: f for f in build_facts(result, BuyerType.PRIVATE)}

    def test_delivery_comes_from_idealo_offers(self):
        delivery = delivery_by_offer(SNAP["offers"])
        self.assertEqual(delivery[SNAP["offers"][0]["key"]], SNAP["offers"][0]["delivery"]["deliveryText"])

    def test_model_sees_price_history(self):
        self.assertIn("1679.00", self.facts(HISTORY)["PRICE_HISTORY"].text)

    def test_model_is_told_when_history_is_missing(self):
        self.assertIn("no price history", self.facts()["PRICE_HISTORY"].text.lower())

    def test_model_sees_availability_and_offer_coverage(self):
        facts = self.facts()
        self.assertIn("IDEALO_DELIVERY", facts)
        self.assertIn(str(SNAP["product"]["totalOfferCount"]), facts["IDEALO_OFFER_COUNT"].text)


if __name__ == "__main__":
    unittest.main()
