// Talks to the local VendorScan API. Content scripts can't call localhost
// directly from idealo's page, so requests go through this service worker.
const API = "http://127.0.0.1:8765";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "vendorscan:fetch") return false;
  const allowed = /^\/api\/(scan|demo\/[a-z]+)(\?.*)?$/;
  if (!allowed.test(message.path)) {
    sendResponse({ ok: false, error: "Blocked path" });
    return false;
  }
  const init = message.body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(message.body) }
    : { method: "GET" };
  fetch(API + message.path, init)
    .then(async (response) => {
      const body = await response.json().catch(() => ({}));
      const detail = typeof body.detail === "string" ? body.detail : `HTTP ${response.status}`;
      sendResponse(response.ok ? { ok: true, data: body } : { ok: false, error: detail });
    })
    .catch(() => sendResponse({ ok: false, error: "Local VendorScan server is not running (python -m vendorscan.api)." }));
  return true; // keep the channel open for the async response
});
