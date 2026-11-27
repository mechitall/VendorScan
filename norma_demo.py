"""Norma demonstration, fixed version.

The previous commit broke rules on purpose (banned `requests` package, float for money,
print() in production code, unnamed timeout). Nothing in the application imports this file.
"""
from __future__ import annotations

import logging
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

CONNECT_SECONDS = 5.0
READ_SECONDS = 20.0
PAGE_TIMEOUT = httpx.Timeout(READ_SECONDS, connect=CONNECT_SECONDS)


def total_cost(price: Decimal, shipping: Decimal) -> Decimal:
    return price + shipping


def fetch_page(url: str) -> str:
    return httpx.get(url, timeout=PAGE_TIMEOUT).text


def report(price: Decimal, shipping: Decimal) -> None:
    logger.info("Total cost: %s", total_cost(price, shipping))
