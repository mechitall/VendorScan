# VendorScan Chrome side panel: short design

Status: approved. Branch: `feature/chrome-extension`, now based on `origin/feature/extension` (869acb4), which already provides the local API and the content-script panel on idealo pages. Those replace goals 1 and 2 below (no side panel, port 8765, GET endpoints). Done on this branch: goal 3 (shop-level part) and goal 5. Delivered via pull request.

## Intent

A freelancer who can deduct input VAT wants to know which offer is cheapest for their business, including whether buying used pays off. Second story: the marketplace / scalper check. The result is shown directly in a Chrome side panel.

## Data order (decided by the team)

1. idealo MCP always comes first: offers, seller data, delivery, price history.
2. Tavily only supports: fills what idealo leaves open.
3. Results are shown directly in the extension.

## Already built on the base branch (do not duplicate)

Seller VAT research on the shop's own domain with verbatim quotes judged by Nebius, hidden-cheaper-offer search, gap report, scarcity-gated restock research, cost engine, rule verdicts, replay snapshots. 38 tests pass.

## Goals, in build order

1. `backend/main.py` (FastAPI on 127.0.0.1): `GET /health`, `POST /api/scan` calling `orchestrator.scan()` / `replay()`. Response is the existing `ScanResult` plus `mode` and `warnings`. Buyer types are the existing `private`, `business_vat`, `small_business`.
2. `extension/` (Manifest V3, vanilla JS): query field, "Scan this page" button (title, canonical URL, product JSON-LD only), buyer profile, budget. Shows verdict, offers with gross and effective cost, VAT status with quotes and links, gap report, mode.
3. VAT confidence tiers (change in `vendor_vat.py` / `verdict.py`, agree with its author first):
   - confirmed: statement for this very offer. May lead to BUY.
   - likely: shop-level statement. Shows "if the invoice shows VAT", verdict VERIFY with a question to send to the seller. Cost engine keeps the range.
   - unknown: range, VERIFY.
   - A statement taken from another product's page is at most shop-level.
4. Price history: call `history()` in `scan()`, parse German price strings, show 30-day min / current, and the used-purchase threshold (comparable new price minus reclaimable VAT, labeled conditional unless confirmed).
5. Nebius selects the next action (INVESTIGATE, COMPARE_ALTERNATIVE, REQUEST_CLARIFICATION, PREPARE_PURCHASE, WAIT), at most 2 research rounds. Python gates block PREPARE_PURCHASE while material facts are open. Model, calls and actions appear in a trace. Error or timeout gives VERIFY.
6. Marketplace check: a single or only-marketplace offer counts as a signal even below the 20% premium.
7. Offers outside idealo (eBay, Amazon Marketplace, Otto): Tavily search per shop, shown in their own section as "outside idealo, unverified" with link and any price found. Never ranked, never the winner.
8. Optional: scan an open shop page to turn such a link into a comparable offer.

Cut order when time runs out: 8, 7, 6, then 4. Items 1, 2 and 5 are required.

## Non-goals

Checkout, payment, accounts, Web Store publication, condition-adjusted valuation of used goods.

## Anti-goals

- No provider keys in the extension, no wildcard CORS.
- No simulated live trace; `mode` says what ran.
- Never call VAT reclaimable for an offer on shop-level or third-party evidence.
- Remote text is rendered with `textContent`; links are HTTP(S) only and opened by the user.

## Approaches considered

1. Build on `feature/vendor-vat` (chosen): research pipeline exists and is tested.
2. Write our own tax research module: rejected, duplicates that branch.
3. Extension against mock data first: rejected, delays integration; replay mode covers offline work.

For offers outside idealo: Tavily alone did not return reliable prices in a small test (2026-11-27), so those results are shown as unverified. The eBay Browse API needs a developer key and is only used if the team already has one.

## Constraints

Feature freeze 18:30, submission 19:45 CET. Permissions: `sidePanel`, `activeTab`, `scripting`, `storage`, host `http://127.0.0.1:8000/*`. idealo Trial: 10 offers per product. idealo offers carry no condition or VAT field.

## Left to the builder

File layout inside `extension/`, side panel layout, API error format, tests for API validation and gates.
