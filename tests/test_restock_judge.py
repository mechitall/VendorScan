import unittest
from decimal import Decimal
from unittest import mock

import httpx

from vendorscan import llm
from vendorscan.restock import RestockReport, _judge

SOURCES = [
    {"url": "https://eu.example-store.test/tablet", "title": "Tablet X",
     "content": "Regular price €699.00. Sold out. Back in stock on 10 December."},
    {"url": "https://news.example.test/x2", "title": "Tablet X2 announced",
     "content": "The maker confirmed Tablet X2 will replace Tablet X next spring."},
]


def judge_with(answer):
    report = RestockReport(product_name="Tablet X", lowest_current_price=Decimal("1300"))

    async def run():
        with mock.patch.object(llm, "chat_json", mock.AsyncMock(return_value=answer)):
            async with httpx.AsyncClient() as client:
                await _judge(report, SOURCES, client)

    import asyncio
    asyncio.run(run())
    return report


class JudgeTests(unittest.TestCase):
    def test_verbatim_quotes_are_kept(self):
        report = judge_with({
            "restock_expected": True, "official_price": "699.00", "official_currency": "EUR",
            "official_store_url": SOURCES[0]["url"], "successor_announced": True, "summary": "Wait.",
            "evidence": [
                {"field": "restock", "source": 1, "quote": "Back in stock on 10 December."},
                {"field": "official_price", "source": 1, "quote": "regular PRICE   €699.00"},
                {"field": "successor", "source": 2, "quote": "Tablet X2 will replace Tablet X"},
            ]})
        self.assertTrue(report.restock_signal)
        self.assertTrue(report.successor_signal)
        self.assertEqual(report.official_price, Decimal("699.00"))
        self.assertEqual(report.official_currency, "EUR")
        self.assertEqual(len(report.evidence), 3)

    def test_invented_quotes_are_dropped_and_claims_rejected(self):
        report = judge_with({
            "restock_expected": True, "official_price": "499.00", "official_currency": "EUR",
            "successor_announced": True, "summary": "Restock next week!",
            "evidence": [
                {"field": "restock", "source": 1, "quote": "Restock guaranteed next week"},
                {"field": "official_price", "source": 2, "quote": "Regular price €699.00"},
                {"field": "successor", "source": 9, "quote": "Tablet X2"},
            ]})
        self.assertFalse(report.restock_signal)
        self.assertFalse(report.successor_signal)
        self.assertIsNone(report.official_price)
        self.assertEqual(report.evidence, [])

    def test_malformed_evidence_is_ignored(self):
        report = judge_with({"restock_expected": None, "evidence": [{"source": "x"}, "junk", {}]})
        self.assertFalse(report.restock_signal)
        self.assertEqual(report.evidence, [])


if __name__ == "__main__":
    unittest.main()
