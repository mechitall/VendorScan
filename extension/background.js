// Talks to the local VendorScan API. Content scripts can't call localhost
// directly from idealo's page, so requests go through this service worker.
const API = "http://127.0.0.1:8765";
const OFFLINE = "Local VendorScan server is not running (python -m vendorscan.api).";

// One-shot requests (offline demos).
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "vendorscan:fetch") return false;
  if (!/^\/api\/demo\/[a-z]+$/.test(message.path)) {
    sendResponse({ ok: false, error: "Blocked path" });
    return false;
  }
  fetch(API + message.path)
    .then(async (response) => {
      const body = await response.json().catch(() => ({}));
      sendResponse(response.ok ? { ok: true, data: body } : { ok: false, error: body.detail || `HTTP ${response.status}` });
    })
    .catch(() => sendResponse({ ok: false, error: OFFLINE }));
  return true;
});

// Live scans: stream newline-delimited JSON events back to the panel as they arrive.
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "vendorscan:scan") return;
  const controller = new AbortController();
  port.onDisconnect.addListener(() => controller.abort());
  port.onMessage.addListener(async (payload) => {
    try {
      const response = await fetch(API + "/api/scan/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        const body = await response.json().catch(() => ({}));
        port.postMessage({ type: "error", message: typeof body.detail === "string" ? body.detail : `HTTP ${response.status}` });
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let newline;
        while ((newline = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, newline).trim();
          buffer = buffer.slice(newline + 1);
          if (line) port.postMessage(JSON.parse(line));
        }
      }
    } catch (error) {
      if (error.name !== "AbortError") port.postMessage({ type: "error", message: OFFLINE });
    }
  });
});
