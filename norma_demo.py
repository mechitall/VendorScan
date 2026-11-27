"""Norma demonstration: this version breaks team policy ON PURPOSE and is fixed in a follow-up commit.

Nothing in the application imports this file. It uses the banned `requests` package,
float instead of Decimal for money, and print() in production code.
"""
import requests


def total_cost(price: float, shipping: float) -> float:
    return price + shipping


def fetch_page(url: str) -> str:
    return requests.get(url, timeout=30).text


def report(price: float, shipping: float) -> None:
    print(total_cost(price, shipping))
