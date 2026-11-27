// VendorScan panel on idealo product pages.
// All data is inserted as text (never innerHTML): quotes come from untrusted web pages.
(() => {
  if (document.getElementById("vendorscan-panel")) return;

  const BUYERS = [
    ["private", "Private"],
    ["small_business", "Small business (§19)"],
    ["business_vat", "Business (VAT)"],
  ];
  const TAX_LABEL = {
    standard_vat: "VAT invoice",
    margin_scheme: "Margin scheme: no VAT reclaim",
    small_business: "Seller charges no VAT",
    private_sale: "Private seller",
    unknown: "VAT treatment unknown",
  };
  const BADGE = { BUY: "BUY", WAIT: "WAIT", VERIFY: "VERIFY FIRST", AVOID: "SKIP THIS OFFER" };
  let state = { buyer: "private", result: null };

  const el = (tag, props = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (key === "class") node.className = value;
      else if (key === "onclick") node.addEventListener("click", value);
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child == null || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  };
  const safeLink = (url, text) =>
    /^https?:\/\//i.test(url || "")
      ? el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, text)
      : el("span", {}, text);
  const euro = (v) => (v == null ? "?" : `€${Number(v).toLocaleString("de-DE", { minimumFractionDigits: 2 })}`);
  const range = (lo, hi) => (lo === hi ? euro(lo) : `${euro(lo)}–${euro(hi)}`);

  const productId = (location.pathname.match(/OffersOfProduct\/(\d+)/) || [])[1];
  // e.g. "214218295_-astra-2-gaming-512gb-silber-redmagic": carries the variant and model number.
  const productSlug = (location.pathname.match(/OffersOfProduct\/([\w-]+)\.html/) || [])[1];
  const productName = () =>
    (document.querySelector("h1")?.textContent || document.title.split(/\s+(ab|\|)\s+/)[0] || "")
      .replace(/\s+/g, " ").trim();

  const panel = el("aside", { id: "vendorscan-panel", class: "vs-open" });
  const body = el("div", { class: "vs-body" });
  const toggle = el("button", { class: "vs-toggle", title: "Show or hide VendorScan",
    onclick: () => panel.classList.toggle("vs-open") }, "VendorScan");
  panel.append(toggle, el("div", { class: "vs-inner" },
    el("header", { class: "vs-header" }, el("strong", {}, "VendorScan"), el("span", {}, "Know the deal before you buy")),
    body));
  document.body.append(panel);

  function request(path, payload) {
    return new Promise((resolve) =>
      chrome.runtime.sendMessage({ type: "vendorscan:fetch", path, body: payload }, (reply) =>
        resolve(reply || { ok: false, error: "Extension error" })));
  }

  // Offer titles on idealo's page carry condition and VAT hints ("Neu - differenzbesteuert").
  // Each offer link has the same offer key the idealo MCP uses, so they match exactly.
  function offerTitles() {
    const titles = {};
    for (const link of document.querySelectorAll('a[href*="offerKey="]')) {
      const key = (link.getAttribute("href").match(/offerKey=([0-9a-f]{32})/) || [])[1];
      if (!key || titles[key]) continue;
      const row = link.closest(".productOffers-listItemTitle, li, tr") || link;
      const text = (row.innerText || "").replace(/\s+/g, " ").trim().slice(0, 200);
      if (text) titles[key] = text;
      if (Object.keys(titles).length >= 80) break;
    }
    return titles;
  }

  async function load(path, label, payload) {
    body.replaceChildren(el("p", { class: "vs-muted" }, label));
    const reply = await request(path, payload);
    if (!reply.ok) {
      body.replaceChildren(el("p", { class: "vs-error" }, reply.error), demoLinks());
      return;
    }
    state.result = reply.data;
    render();
  }

  function scanThisPage(fresh = false) {
    const payload = {
      name: productName().slice(0, 200),
      title: document.title.slice(0, 300),
      product_id: productId || null,
      slug: productSlug ? productSlug.slice(0, 300) : null,
      fresh,
      offer_titles: offerTitles(),
    };
    load("/api/scan", "Checking idealo offers, sellers' VAT and the web… (about 10 s)", payload);
  }

  function demoLinks() {
    return el("p", { class: "vs-muted vs-demos" }, "Offline demo: ",
      el("button", { class: "vs-link", onclick: () => load("/api/demo/redmagic", "Loading demo…") }, "RedMagic Astra 2"),
      " · ",
      el("button", { class: "vs-link", onclick: () => load("/api/demo/macbook", "Loading demo…") }, "MacBook Air M4"),
      " · ",
      el("button", { class: "vs-link", onclick: () => load("/api/demo/galaxy", "Loading demo…") }, "Galaxy S26 Ultra"));
  }

  function render() {
    const r = state.result;
    const verdict = r.verdicts[state.buyer];
    const offers = r.by_buyer[state.buyer] || [];

    const tabs = el("div", { class: "vs-tabs" }, BUYERS.map(([key, label]) =>
      el("button", { class: key === state.buyer ? "vs-tab vs-active" : "vs-tab",
        onclick: () => { state.buyer = key; render(); } }, label)));

    const source = r.source.startsWith("replay")
      ? el("span", { class: "vs-chip vs-chip-warn" }, "Replay of a saved live scan")
      : el("span", { class: "vs-chip" }, "Live");

    const head = el("div", { class: "vs-product" },
      el("div", {}, el("strong", {}, r.product), " ", source),
      r.exact_match === false && el("div", { class: "vs-note" },
        "This exact variant isn't in idealo's data feed; showing the closest match."),
      r.listed_lowest && el("div", { class: "vs-muted" }, `idealo lists from ${euro(r.listed_lowest)}`));

    const verdictBox = el("section", { class: `vs-verdict vs-${verdict.recommendation.toLowerCase()}` },
      el("div", { class: "vs-badge" }, BADGE[verdict.recommendation] || verdict.recommendation),
      el("ul", {}, verdict.reasons.map((reason) => el("li", {}, reason))));

    const table = el("table", { class: "vs-offers" },
      el("thead", {}, el("tr", {}, ["Seller", "You pay", "VAT back", "Real cost"].map((h) => el("th", {}, h)))),
      el("tbody", {}, offers.map(({ offer, cost }, i) => el("tr", { class: i === 0 ? "vs-best" : "" },
        el("td", {},
          safeLink(offer.offer_url, offer.seller.name),
          el("div", { class: "vs-tags" },
            el("span", { class: `vs-tag vs-tax-${offer.tax_status}`, title: offer.tax_basis || "" },
              (TAX_LABEL[offer.tax_status] || offer.tax_status) + (offer.tax_confidence === "likely" ? " (likely)" : "")),
            offer.condition && el("span", { class: "vs-tag" }, offer.condition === "used" ? "Used" : "New"),
            offer.seller.is_marketplace && el("span", { class: "vs-tag" }, "Marketplace"),
            !offer.seller.rating_count && el("span", { class: "vs-tag" }, "No ratings"))),
        el("td", {}, euro(cost.total_gross)),
        el("td", {}, cost.recoverable_vat == null ? "?" : euro(cost.recoverable_vat)),
        el("td", {}, el("strong", {}, range(cost.effective_cost_low, cost.effective_cost_high)))))));

    const quote = (ev) => {
      let host = "source";
      try { host = new URL(ev.url).hostname; } catch (_) { /* keep "source" */ }
      return el("blockquote", {}, `“${ev.quote || ""}”`, el("br"), safeLink(ev.url, host));
    };
    const gapItem = (gap) => el("details", {},
      el("summary", {},
        el("span", {}, gap.gap),
        el("span", { class: "vs-muted" }, gap.filled_by ? ` · ${gap.filled_by.split(" ")[0]}` : " · open")),
      gap.finding && el("p", {}, gap.finding),
      (gap.evidence || []).map(quote));
    const gaps = el("section", { class: "vs-gaps" },
      el("h3", {}, "What VendorScan figured out"),
      (r.gaps || []).map(gapItem));

    body.replaceChildren(head, tabs, verdictBox, table, gaps,
      el("footer", { class: "vs-footer" },
        el("span", { class: "vs-muted" }, "Estimates, not tax advice. No purchases are made."),
        el("button", { class: "vs-link", onclick: () => scanThisPage(true) }, "Rescan"),
        demoLinks()));
  }

  scanThisPage();
})();
