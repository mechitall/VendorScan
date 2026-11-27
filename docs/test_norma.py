"""Norma demonstration: this version breaks team policy ON PURPOSE and is fixed in the next commit.

It is not part of the application and nothing imports it. It breaks two rules from NORMA.md:
the banned `requests` package, and float instead of Decimal for money.
"""
import requests


def demo_total(price: float, shipping: float) -> float:
    return price + shipping


def demo_fetch() -> str:
    return requests.get("https://example.com", timeout=5).text


print("Norma check test")
