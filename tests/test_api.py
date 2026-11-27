import unittest

from fastapi.testclient import TestClient

from vendorscan.api import app

EXTENSION_ORIGIN = "chrome-extension://" + "a" * 32


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def test_health(self):
        self.assertEqual(self.client.get("/api/health").json(), {"ok": True})

    def test_demo_replays_saved_scan(self):
        data = self.client.get("/api/demo/macbook").json()
        self.assertTrue(data["source"].startswith("replay:"))
        self.assertIn("business_vat", data["verdicts"])

    def test_unknown_demo_is_404(self):
        self.assertEqual(self.client.get("/api/demo/nope").status_code, 404)

    def test_scan_rejects_bad_product_id(self):
        self.assertEqual(self.client.post("/api/scan", json={"name": "x y", "product_id": "abc"}).status_code, 422)

    def test_cors_allows_only_extensions(self):
        ok = self.client.get("/api/health", headers={"Origin": EXTENSION_ORIGIN})
        self.assertEqual(ok.headers.get("access-control-allow-origin"), EXTENSION_ORIGIN)
        blocked = self.client.get("/api/health", headers={"Origin": "https://evil.example"})
        self.assertIsNone(blocked.headers.get("access-control-allow-origin"))


if __name__ == "__main__":
    unittest.main()
