"""Local HTTP API for the VendorScan browser extension.

Runs on 127.0.0.1 only. API keys and the idealo sign-in stay on this machine;
the extension only receives scan results.

Start: python -m vendorscan.api   (then load the extension from ./extension)
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .orchestrator import ScanResult, replay, scan

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
DEMOS = {"redmagic": "live_redmagic_astra2.json", "macbook": "live_macbook_air_m4.json",
         "galaxy": "live_galaxy_s26_ultra.json", "iphone": "live_iphone17_pro_max_1tb.json"}
CACHE_SECONDS = 600

app = FastAPI(title="VendorScan local API", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

_cache: dict[tuple, tuple[float, ScanResult]] = {}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


class ScanRequest(BaseModel):
    name: str = Field(default="", max_length=200)
    title: str | None = Field(default=None, max_length=300)
    slug: str | None = Field(default=None, max_length=300, pattern=r"^[\w-]+$")
    product_id: str | None = Field(default=None, pattern=r"^\d{1,15}$")
    budget: Decimal | None = Field(default=None, gt=0)
    fresh: bool = False
    # Offer key -> offer title, as shown on idealo's page (e.g. "Neu - differenzbesteuert").
    offer_titles: dict[str, str] = Field(default_factory=dict, max_length=80)


@app.post("/api/scan")
async def scan_product(request: ScanRequest) -> dict:
    """Scan the idealo product the user is looking at."""
    titles = {k: v[:200] for k, v in request.offer_titles.items() if re.fullmatch(r"[0-9a-f]{32}", k)}
    key = (request.name, request.title, request.slug, request.product_id, request.budget,
           tuple(sorted(titles.items())))
    cached = _cache.get(key)
    if cached and not request.fresh and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1].model_dump(mode="json")
    try:
        result = await scan(request.name, product_id=request.product_id, slug=request.slug,
                            title=request.title, budget=request.budget, offer_titles=titles)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    _cache[key] = (time.time(), result)
    return result.model_dump(mode="json")


@app.post("/api/scan/stream")
async def scan_stream(request: ScanRequest) -> StreamingResponse:
    """Same scan, streamed as newline-delimited JSON events so the panel can show progress."""
    titles = {k: v[:200] for k, v in request.offer_titles.items() if re.fullmatch(r"[0-9a-f]{32}", k)}
    key = (request.name, request.title, request.slug, request.product_id, request.budget,
           tuple(sorted(titles.items())))
    queue: asyncio.Queue = asyncio.Queue()

    async def run() -> None:
        cached = _cache.get(key)
        try:
            if cached and not request.fresh and time.time() - cached[0] < CACHE_SECONDS:
                result = cached[1]
            else:
                result = await scan(request.name, product_id=request.product_id, slug=request.slug,
                                    title=request.title, budget=request.budget, offer_titles=titles,
                                    on_event=queue.put)
                _cache[key] = (time.time(), result)
            await queue.put({"type": "result", "result": result.model_dump(mode="json")})
        except LookupError as error:
            await queue.put({"type": "error", "message": str(error)})
        except Exception:  # noqa: BLE001 - report to the panel instead of dropping the stream
            await queue.put({"type": "error", "message": "Scan failed. Check the server log."})
            raise
        finally:
            await queue.put(None)

    async def events():
        task = asyncio.create_task(run())
        try:
            while (event := await queue.get()) is not None:
                yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(events(), media_type="application/x-ndjson")


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
