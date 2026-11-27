import asyncio
import unittest
from decimal import Decimal
from unittest import mock

import httpx

from vendorscan import vendor_vat
from vendorscan.models import Offer, Seller, TaxStatus


def run(answer, sources, seller=Seller(name="shop.de", domain="shop.de", is_marketplace=False)):
    offer = Offer(offer_id="o", product_name="p", seller=seller, item_gross=Decimal("100"))
    tavily = {"results": [{"url": u, "title": t, "content": c} for u, t, c in sources]}

    async def go():
        with mock.patch.object(vendor_vat, "tavily_search", mock.AsyncMock(return_value=tavily)), \
             mock.patch.object(vendor_vat.llm, "chat_json", mock.AsyncMock(return_value=answer)), \
             mock.patch.object(vendor_vat.llm, "available", return_value=True):
            async with httpx.AsyncClient() as client:
                return await vendor_vat.research_vendor(offer, client)
    return asyncio.run(go())


SHOP_PAGE = ("https://shop.de/hilfe", "Hilfe", "Die Mehrwertsteuer wird auf der Rechnung ausgewiesen. "
             "Alle Preise inkl. MwSt.")


class VendorVatTests(unittest.TestCase):
    def test_explicit_invoice_statement_confirms_standard_vat(self):
        result = run({"tax_status": "standard_vat", "summary": "ok",
                      "evidence": [{"source": 1, "quote": "Die Mehrwertsteuer wird auf der Rechnung ausgewiesen."}]},
                     [SHOP_PAGE])
        self.assertEqual(result.tax_status, TaxStatus.STANDARD_VAT)

    def test_generic_inkl_mwst_is_not_enough(self):
        result = run({"tax_status": "standard_vat", "summary": "VAT invoices available!",
                      "evidence": [{"source": 1, "quote": "Alle Preise inkl. MwSt."}]}, [SHOP_PAGE])
        self.assertEqual(result.tax_status, TaxStatus.UNKNOWN)
        self.assertNotIn("available", result.summary)

    def test_marketplace_operator_pages_do_not_count_for_the_seller(self):
        seller = Seller(name="Insta24 (via kaufland.de)", domain="kaufland.de", is_marketplace=True)
        page = ("https://kaufland.de/impressum", "Impressum Kaufland",
                "Die Mehrwertsteuer wird auf der Rechnung ausgewiesen.")
        result = run({"tax_status": "standard_vat", "summary": "ok",
                      "evidence": [{"source": 1, "quote": "Die Mehrwertsteuer wird auf der Rechnung ausgewiesen."}]},
                     [page], seller=seller)
        self.assertEqual(result.tax_status, TaxStatus.UNKNOWN)

    def test_apply_sets_standard_rate(self):
        offer = Offer(offer_id="o", product_name="p", seller=Seller(name="s"), item_gross=Decimal("119"),
                      risk_flags=["TAX_UNVERIFIED"])
        vat = vendor_vat.VendorVat(seller="s", tax_status=TaxStatus.STANDARD_VAT)
        updated = vendor_vat.apply_vendor_vat(offer, vat)
        self.assertEqual(updated.vat_rate, Decimal("0.19"))
        self.assertNotIn("TAX_UNVERIFIED", updated.risk_flags)


if __name__ == "__main__":
    unittest.main()
