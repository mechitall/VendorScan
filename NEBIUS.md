# VendorScan on Nebius Token Factory

## Model and use note (paste into the submission form)

VendorScan calls `Qwen/Qwen3-30B-A3B-Instruct-2507` on Nebius Token Factory in two places.
**The decision:** a live call chooses the next step for each scanned product and buyer
(`vendorscan/next_action.py`): INVESTIGATE, COMPARE_ALTERNATIVE, REQUEST_CLARIFICATION,
PREPARE_PURCHASE or WAIT. INVESTIGATE lets the model write a search query; the search runs
through Tavily and the model is asked again (at most two rounds). **Evidence:** calls read
Tavily sources about seller VAT, reputation, restocks and missing cheaper offers, and must
quote them word for word (`vendor_vat.py`, `gaps.py`, `restock.py`).

## What limits the model

- It sees numbered facts and a list of allowed actions, and must cite fact ids that exist.
- PREPARE_PURCHASE is allowed only if the rule check says BUY and no material fact is open
  (for a business buyer: nothing on the offer itself confirms a VAT invoice; also unknown
  VAT, incomplete price, unrated marketplace seller).
- Web text is untrusted and never closes an open fact.
- A disallowed answer, invented evidence, a timeout or an error ends in
  REQUEST_CLARIFICATION, shown as blocked or failed, not as a model choice.
- Nothing is ever purchased. In the panel, a rule "Buy" is shown as **Buy** only after the
  model returns PREPARE_PURCHASE.

## Who can trigger a call

The local server answers only the extension and local tools. Requests from web pages and
foreign host names are refused, so another site cannot spend API credits.

## idealo data the model sees

30-day price history (lowest, average, highest, current, change), delivery text of the best
offer, and idealo's offer count against the offers its data feed returned, plus the rule
reasons built from prices, shipping, seller ratings and the marketplace flag.
Price history informs the model; no rule changes a verdict because of it.

## Showing the calls

- Panel: **Next step → Model calls** lists every call with action, status, latency, search
  query, model id and provider.
- Server terminal: one `nebius call model=... asked=... status=... latency_ms=...` line per call.
  This covers the decision calls, not the evidence calls.

## Observed on 27 November 2026 (live calls)

| Case | Buyer | Model actions | Open facts |
|---|---|---|---|
| Routine: MacBook Air M4 (live scan) | private | PREPARE_PURCHASE | none |
| Conflicting: MacBook Air M4 (live scan) | business | INVESTIGATE, INVESTIGATE, REQUEST_CLARIFICATION | VAT not confirmed on the offer |
| Incomplete: RTX 5090 Founders Edition (live scan) | business | INVESTIGATE, INVESTIGATE, REQUEST_CLARIFICATION | unrated seller, VAT unknown |

The model's path is not fixed: the same kind of case sometimes asks the seller at once
without researching first. Rehearse the demo case before presenting.

**Demo links in the panel replay saved scans.** The offers are not live; the decision call
still is, so it needs a network connection and the local server.
