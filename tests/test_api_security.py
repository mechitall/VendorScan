"""Other web pages must not be able to trigger scans (they cost API credits)."""
import unittest

from fastapi.testclient import TestClient

from vendorscan.api import app

DEMO = "/api/demo/macbook"


class ApiCallerTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def status(self, **headers):
        return self.client.get(DEMO, headers={k.replace("_", "-"): v for k, v in headers.items()}).status_code

    def test_request_from_a_web_page_is_refused(self):
        for site in ("cross-site", "same-site"):
            self.assertEqual(self.status(sec_fetch_site=site), 403, site)

    def test_foreign_origin_is_refused(self):
        self.assertEqual(self.status(origin="https://evil.example"), 403)

    def test_foreign_host_name_is_refused(self):
        self.assertEqual(self.status(host="rebind.evil.example"), 400)

    def test_web_page_cannot_start_a_paid_scan_or_model_call(self):
        for path in ("/api/scan", "/api/scan/stream", "/api/decide"):
            response = self.client.post(path, content='{"name": "x y", "buyer": "private"}',
                                        headers={"origin": "https://evil.example", "content-type": "text/plain"})
            self.assertEqual(response.status_code, 403, path)

    def test_extension_and_command_line_are_allowed(self):
        self.assertEqual(self.status(), 200)
        self.assertEqual(self.status(sec_fetch_site="none"), 200)
        self.assertEqual(self.status(origin="chrome-extension://" + "a" * 32, sec_fetch_site="cross-site"), 200)


if __name__ == "__main__":
    unittest.main()
