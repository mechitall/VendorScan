# VendorScan: idealo MCP

Read-only product discovery and offer retrieval. No purchase execution.

## Quickest live test (Claude Code)

The included `.mcp.json` follows [idealo's official setup](https://github.com/idealo/mcp-server-guide). Open Claude Code at the repository root, approve the project MCP configuration, run `/mcp`, select idealo, and complete browser OAuth. Alternatively run `claude mcp add --transport http idealo https://mcp.idealo.com/mcp --callback-port 6274` if not using the project config.

Prompt: Search for an Apple MacBook Air M2 in Germany using idealo. Select a matching product variant, fetch offers and 30-day price history, and show shop name, merchant name, price, shipping, rating and review count, and relocator URL. Do not infer VAT or claim an unverified merchant is unsafe.

## Python backend

Install `python -m pip install -r requirements-idealo.txt`. The Python adapter requires a valid idealo OAuth bearer access token supplied as `IDEALO_ACCESS_TOKEN` at runtime. Obtain it via an authorized OAuth client or ask the idealo mentor for programmatic OAuth setup; the adapter does not implement browser OAuth or refresh tokens. Never commit tokens. Claude Code's authenticated session is separate from this Python adapter.

Run `python idealo_client.py 'Apple MacBook Air M2' --index 0` for a live test. The first matching result is selected for this smoke test only, not for purchasing decisions. Change the index to compare the correct variant.

Application API:

```python
from idealo_client import connect

async def scan(query):
    async with connect() as idealo:
        matches = await idealo.search(query)
        # In production, let the user/agent verify the exact product variant.
        product = matches['results'][0]
        return await idealo.offers(product)
```

The client preserves the raw MCP result and follows `nextOffset` for two pages by default (up to 10 offers on Trial). Keep `productRef` opaque and use it immediately. `price`, `basePrice` and `minShippingCost` must not be blindly added; verify their semantics before calculating total cost. VAT treatment, used/refurbished condition and final checkout fees are not documented offer fields; mark unknown pending independent evidence. Amazon, eBay and Otto offers are excluded by idealo's documented compliance filter.

## Verification

`python -m unittest -v test_idealo_client` runs offline mock tests. The live test requires internet and OAuth; it was not run successfully in the authoring environment (DNS resolution failed). Documentation: https://github.com/idealo/mcp-server-guide/blob/main/docs/tools.md
