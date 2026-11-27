"""Timeouts in one place, so they're named, tuned together and easy to review.

Connect timeouts are short and separate from read timeouts: a host that doesn't answer
should fail fast, while a slow LLM or search response may legitimately take longer.
"""
from __future__ import annotations

import httpx

CONNECT_SECONDS = 5.0

IDEALO_TIMEOUT = httpx.Timeout(30.0, connect=CONNECT_SECONDS)       # idealo MCP calls
TOKEN_TIMEOUT = httpx.Timeout(20.0, connect=CONNECT_SECONDS)        # OAuth token refresh
TAVILY_TIMEOUT = httpx.Timeout(20.0, connect=CONNECT_SECONDS)       # one web search
LLM_TIMEOUT = httpx.Timeout(60.0, connect=CONNECT_SECONDS)          # one Nebius completion

SELLER_RESEARCH_SECONDS = 15.0   # whole VAT check for one seller (searches + LLM)
REPUTATION_SECONDS = 20.0        # whole review check for one seller
