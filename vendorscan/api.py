"""Local HTTP API for the VendorScan browser extension.

Runs on 127.0.0.1 only. API keys and the idealo sign-in stay on this machine;
the extension only receives scan results.

Start: python -m vendorscan.api   (then load the extension from ./extension)
"""
from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .orchestrator import ScanResult, replay, scan

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
DEMOS = {"redmagic": "live_redmagic_astra2.json", "macbook": "live_macbook_air_m4.json",
         "galaxy": "live_galaxy_s26_ultra.json"}
CACHE_SECONDS = 600

app = FastAPI(title="VendorScan local API", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
                   allow_methods=["GET"], allow_headers=[])

_cache: dict[tuple, tuple[float, ScanResult]] = {}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/scan")
async def scan_product(name: str = Query(default="", max_length=200),
                       product_id: str | None = Query(default=None, pattern=r"^\d{1,15}$"),
                       slug: str | None = Query(default=None, max_length=300, pattern=r"^[\w-]+$"),
                       title: str | None = Query(default=None, max_length=300),
                       budget: Decimal | None = Query(default=None, gt=0),
                       fresh: bool = False) -> dict:
    """Scan the idealo product the user is looking at."""
    key = (name, product_id, slug, title, budget)
    cached = _cache.get(key)
    if cached and not fresh and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1].model_dump(mode="json")
    try:
        result = await scan(name, product_id=product_id, slug=slug, title=title, budget=budget)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    _cache[key] = (time.time(), result)
    return result.model_dump(mode="json")


@app.get("/api/demo/{demo}")
def demo(demo: str, budget: Decimal | None = Query(default=None, gt=0)) -> dict:
    """Replay a saved live snapshot (works offline)."""
    if demo not in DEMOS:
        raise HTTPException(status_code=404, detail=f"Unknown demo. Choose from: {', '.join(DEMOS)}")
    return replay(FIXTURES / DEMOS[demo], budget=budget).model_dump(mode="json")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")


if __name__ == "__main__":
    main()
