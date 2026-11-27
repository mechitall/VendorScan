import unittest
from decimal import Decimal

from vendorscan import vat_rules
from vendorscan.models import Evidence, EvidenceStatus, Offer, Seller, TaxStatus
from vendorscan.vendor_vat import VendorVat


def offer(title=None, marketplace=False):
    return Offer(offer_id="k", product_name="Phone", item_gross=Decimal("1190"), title=title,
                 seller=Seller(name="shop.de", domain="shop.de", is_marketplace=marketplace),
                 risk_flags=["TAX_UNVERIFIED"])


def vendor(status):
    quote = Evidence(field="tax_status", status=EvidenceStatus.CONFIRMED, url="https://shop.de", quote="q")
    return VendorVat(seller="shop.de", tax_status=status, evidence=[quote])


class VatRuleTests(unittest.TestCase):
    def check(self, o, v, status, confidence):
        decided = vat_rules.decide(o, v)
        self.assertEqual((decided.tax_status, decided.tax_confidence), (status, confidence), decided.tax_basis)
        return decided

    def test_1_title_margin_scheme_beats_seller_claims(self):
        self.check(offer("Galaxy S26 256GB Neu - dif\xadfe\xadrenz\xadbe\xadsteu\xadert"),
                   vendor(TaxStatus.STANDARD_VAT), TaxStatus.MARGIN_SCHEME, "confirmed")

    def test_1b_title_with_19_percent_vat(self):
        d = self.check(offer("S26 Ultra 256GB Black inkl. 19% MwSt."), None, TaxStatus.STANDARD_VAT, "confirmed")
        self.assertEqual(d.vat_rate, Decimal("0.19"))

    def test_2_seller_kleinunternehmer(self):
        self.check(offer("Phone"), vendor(TaxStatus.SMALL_BUSINESS), TaxStatus.SMALL_BUSINESS, "confirmed")

    def test_3_seller_confirms_vat_invoices(self):
        self.check(offer(None), vendor(TaxStatus.STANDARD_VAT), TaxStatus.STANDARD_VAT, "confirmed")

    def test_4_used_item_from_margin_seller(self):
        self.check(offer("Phone gebraucht, sehr gut"), vendor(TaxStatus.MARGIN_SCHEME),
                   TaxStatus.MARGIN_SCHEME, "likely")

    def test_5_partial_margin_seller_new_item_needs_asking(self):
        self.check(offer("Phone 256GB"), vendor(TaxStatus.MARGIN_SCHEME), TaxStatus.UNKNOWN, None)

    def test_6_used_item_needs_double_check(self):
        self.check(offer("Phone refurbished"), None, TaxStatus.UNKNOWN, None)

    def test_7_new_item_from_regular_shop_is_likely_standard(self):
        self.check(offer("Galaxy S26 Ultra, 256 GB Black"), None, TaxStatus.STANDARD_VAT, "likely")

    def test_7_not_for_marketplace_resellers(self):
        self.check(offer("Galaxy S26 Ultra, 256 GB Black", marketplace=True), None, TaxStatus.UNKNOWN, None)

    def test_8_no_title_no_evidence(self):
        self.check(offer(None), None, TaxStatus.UNKNOWN, None)


if __name__ == "__main__":
    unittest.main()
