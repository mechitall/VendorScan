# VendorScan browser extension

Adds a VendorScan panel to idealo product pages
(`https://www.idealo.de/preisvergleich/OffersOfProduct/...`): a verdict per buyer
type, the real cost of each offer after VAT, and what idealo's data didn't say,
filled in by Tavily + Nebius with quoted sources.

## Run it

1. Start the local API (keeps API keys and the idealo sign-in on your machine):
   ```bash
   python -m vendorscan.api
   ```
   It listens on `http://127.0.0.1:8765` only. First time: `python -m vendorscan.idealo_auth` to sign in to idealo.
2. In Chrome open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick this `extension/` folder.
3. Open any idealo product page. The panel appears on the right; a live scan takes about 15 seconds.

No server or no network? Use the **Offline demo** links in the panel: they replay saved live scans.

## Security
- The extension only talks to `127.0.0.1:8765`, through its service worker, and only to `/api/scan` and `/api/demo/*`.
- The API accepts cross-origin requests only from Chrome extensions.
- Web quotes are inserted as text, never as HTML, and only `http(s)` links are rendered.
