import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from vendorscan import api
from vendorscan.next_action import choose_next_action


async def offline_decision(result, buyer):
    """The real decision logic with a scripted model, so the test needs no network."""
    async def chat(system, user):
        return {"action": "WAIT", "evidence_ids": ["F1"], "reason": "test"}

    return await choose_next_action(result, buyer, chat=chat)


class DecideApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app, base_url="http://127.0.0.1:8765")
        api._cache.clear()
        self.addCleanup(api._cache.clear)

    def decide(self, **body):
        with patch.object(api, "choose_next_action", offline_decision):
            return self.client.post("/api/decide", json=body)

    def test_decides_on_a_demo_snapshot(self):
        response = self.decide(buyer="business_vat", demo="macbook")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "WAIT")
        self.assertEqual(len(response.json()["trace"]), 1)

    def test_decides_on_the_scan_the_panel_just_ran(self):
        """The panel sends decide the same body it sent to the streaming scan, plus the buyer."""
        saved = api.replay(api.FIXTURES / api.DEMOS["macbook"])

        async def offline_scan(*args, **kwargs):
            return saved

        query = {"name": "MacBook Air", "title": "MacBook Air | idealo", "slug": "1_-macbook-air",
                 "product_id": "1", "offer_titles": {"a" * 32: "Neu"}}
        with patch.object(api, "scan", offline_scan):
            self.assertEqual(self.client.post("/api/scan/stream", json=query).status_code, 200)
        self.assertEqual(self.decide(buyer="private", **query).status_code, 200)

    def test_unknown_buyer_is_rejected(self):
        self.assertEqual(self.decide(buyer="company", demo="macbook").status_code, 422)

    def test_unknown_demo_is_404(self):
        self.assertEqual(self.decide(buyer="private", demo="nope").status_code, 404)

    def test_live_decision_needs_a_scan_first(self):
        self.assertEqual(self.decide(buyer="private", name="never scanned").status_code, 409)


if __name__ == "__main__":
    unittest.main()
