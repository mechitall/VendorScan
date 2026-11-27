// VendorScan panel on idealo product pages.
// All data is inserted as text (never innerHTML): quotes come from untrusted web pages.
(() => {
  if (document.getElementById("vendorscan-panel")) return;

  // Small businesses under § 19 UStG can't reclaim VAT either, so they see the same as private buyers.
  const BUYERS = [
    ["private", "Private"],
    ["business_vat", "Business (VAT)"],
  ];
  const VERDICT = {
    BUY: ["Buy", "vs-good"],
    WAIT: ["Wait", "vs-warn"],
    VERIFY: ["Check first", "vs-warn"],
    AVOID: ["Skip this offer", "vs-bad"],
  };
  const VAT_TAG = {
    standard_vat: ["VAT back", "vs-tag-good"],
    margin_scheme: ["No VAT back", "vs-tag-bad"],
    small_business: ["No VAT", "vs-tag-bad"],
    private_sale: ["Private seller", "vs-tag-bad"],
    unknown: ["VAT unclear", ""],
  };
  const DEMOS = [["iphone", "iPhone 17 Pro Max"], ["galaxy", "Galaxy S26 Ultra"], ["redmagic", "RedMagic Astra 2"]];

  const state = { buyer: "private", result: null, steps: new Map(), loading: false, error: null, showAll: false };

  // ---------- helpers ----------
  const el = (tag, props = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value == null || value === false) continue;
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
  const link = (url, text, cls) =>
    /^https?:\/\//i.test(url || "")
      ? el("a", { href: url, target: "_blank", rel: "noopener noreferrer", class: cls }, text)
      : el("span", { class: cls }, text);
  const euro = (v) => (v == null ? "–" : `€${Number(v).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
  const shortSeller = (name) => name.split(" (via ")[0];
  const host = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_) { return "source"; } };

  // ---------- page info ----------
  const productId = () => (location.pathname.match(/OffersOfProduct\/(\d+)/) || [])[1];
  const productSlug = () => (location.pathname.match(/OffersOfProduct\/([\w-]+)\.html/) || [])[1];
  const productName = () => (document.querySelector("h1")?.textContent || "").replace(/\s+/g, " ").trim();
  // Offer titles carry condition and VAT hints ("Neu - differenzbesteuert"); the title link
  // has the same offer key the idealo data feed uses, so they match exactly.
  function offerTitles() {
    const titles = {};
    for (const a of document.querySelectorAll('a.productOffers-listItemTitle[href*="offerKey="], .productOffers-listItemTitle a[href*="offerKey="]')) {
      const key = (a.getAttribute("href").match(/offerKey=([0-9a-f]{32})/) || [])[1];
      const text = (a.innerText || "").replace(/\s+/g, " ").trim().slice(0, 200);
      if (key && text && !titles[key]) titles[key] = text;
      if (Object.keys(titles).length >= 80) break;
    }
    return titles;
  }

  // ---------- shell ----------
  const panel = el("aside", { id: "vendorscan-panel", class: "vs-open" });
  const body = el("div", { class: "vs-body" });
  const tab = el("button", { class: "vs-tab-handle", title: "Show or hide VendorScan",
    onclick: () => panel.classList.toggle("vs-open") }, "VendorScan");
  panel.append(tab, el("div", { class: "vs-card" },
    el("header", { class: "vs-head" },
      el("div", { class: "vs-brand" }, el("span", { class: "vs-dot" }), "VendorScan"),
      el("button", { class: "vs-close", title: "Hide", onclick: () => panel.classList.remove("vs-open") }, "×")),
    body));
  document.body.append(panel);

  // ---------- data ----------
  let port = null;
  function scanThisPage(fresh = false) {
    if (port) port.disconnect();
    Object.assign(state, { result: null, steps: new Map(), loading: true, error: null, showAll: false });
    render();
    const query = {
      name: productName().slice(0, 200), title: document.title.slice(0, 300),
      product_id: productId() || null, slug: productSlug()?.slice(0, 300) || null,
      fresh, offer_titles: offerTitles(),
    };
    state.query = query;
    state.decisions = {};
    port = chrome.runtime.connect({ name: "vendorscan:scan" });
    port.onMessage.addListener((event) => {
      if (event.type === "step") state.steps.set(event.id, event);
      else if (event.type === "partial") state.result = event.result;
      else if (event.type === "result") { state.result = event.result; state.loading = false; }
      else if (event.type === "error") { state.error = event.message; state.loading = false; }
      render();
    });
    port.postMessage(query);
  }

  function loadDemo(name) {
    if (port) port.disconnect();
    Object.assign(state, { result: null, steps: new Map(), loading: true, error: null, showAll: false });
    render();
    state.query = { demo: name };
    state.decisions = {};
    chrome.runtime.sendMessage({ type: "vendorscan:fetch", path: `/api/demo/${name}` }, (reply) => {
      state.loading = false;
      if (reply?.ok) state.result = reply.data; else state.error = reply?.error || "Extension error";
      render();
    });
  }

  // Turn seller names in a reason into links to that exact offer on idealo.
  function linkify(text, links) {
    const names = Object.keys(links || {}).sort((a, b) => b.length - a.length);
    if (!names.length) return [text];
    const escaped = names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return text.split(new RegExp(`(${escaped.join("|")})`)).filter(Boolean).map((part) =>
      links[part] ? link(links[part], shortSeller(part), "vs-inline-link") : part);
  }

  // ---------- views ----------
  function progress() {
    const steps = [...state.steps.values()];
    const done = steps.filter((s) => s.done).length;
    const pct = steps.length ? Math.max(8, Math.round((done / steps.length) * 100)) : 8;
    const current = steps.filter((s) => !s.done).map((s) => s.text)[0] || "Starting…";
    return el("div", { class: "vs-progress" },
      el("div", { class: "vs-progress-row" }, el("span", { class: "vs-spinner" }), el("span", {}, current)),
      el("div", { class: "vs-bar" }, el("div", { class: "vs-bar-fill", style: `width:${pct}%` })),
      el("ul", { class: "vs-steps" }, steps.filter((s) => s.done).slice(-4).map((s) =>
        el("li", {}, el("span", { class: "vs-check" }, "✓"), s.text))));
  }

  function verdictCard(r) {
    const verdict = r.verdicts[state.buyer];
    const rows = r.by_buyer[state.buyer] || [];
    const best = rows[0];
    // A rule "Buy" is only a candidate: the headline says Buy once the live model clears it.
    const decision = state.decisions?.[state.buyer];
    const cleared = decision?.data?.action === "PREPARE_PURCHASE";
    let [label, tone] = VERDICT[verdict.recommendation] || [verdict.recommendation, ""];
    if (verdict.recommendation === "BUY" && !cleared) {
      [label, tone] = !decision || decision.pending ? ["Checking…", ""] : ["Check first", "vs-warn"];
    }
    const card = el("section", { class: `vs-verdict ${tone}` }, el("div", { class: "vs-pill" }, label));

    if (verdict.recommendation === "BUY" && best) {
      card.append(
        el("div", { class: "vs-best" }, link(best.offer.offer_url, shortSeller(best.offer.seller.name))),
        el("div", { class: "vs-big" }, euro(best.cost.effective_cost_high)),
        best.cost.recoverable_vat && Number(best.cost.recoverable_vat) > 0
          ? el("div", { class: "vs-sub" }, `You pay ${euro(best.cost.total_gross)} · ${euro(best.cost.recoverable_vat)} VAT back`)
          : el("div", { class: "vs-sub" }, "Lowest real cost for you"));
      const cheapest = rows.reduce((a, b) => (Number(b.cost.total_gross) < Number(a.cost.total_gross) ? b : a), best);
      const saved = Number(cheapest.cost.effective_cost_high) - Number(best.cost.effective_cost_high);
      if (cheapest !== best && saved >= 1) {
        card.append(el("div", { class: "vs-insight" },
          `${euro(saved)} less than the cheapest price on idealo (${shortSeller(cheapest.offer.seller.name)}), after VAT.`));
      }
    } else {
      card.append(el("div", { class: "vs-headline" }, linkify(verdict.reasons[0] || "", verdict.links)));
      const tip = verdict.reasons.find((x) => x.startsWith("Rated alternative"));
      if (tip) card.append(el("div", { class: "vs-insight" }, linkify(tip, verdict.links)));
    }
    const more = verdict.reasons.slice(1).filter((x) => !x.startsWith("Rated alternative"));
    if (more.length) {
      card.append(el("details", { class: "vs-why" }, el("summary", {}, "Why?"),
        el("ul", {}, more.map((x) => el("li", {}, linkify(x, verdict.links))))));
    }
    return card;
  }

  // The next step is chosen by a live Nebius model; the server's rules limit what it may choose.
  const STEP_LABEL = {
    INVESTIGATE: "Research more", COMPARE_ALTERNATIVE: "Compare another offer",
    REQUEST_CLARIFICATION: "Ask the seller first", PREPARE_PURCHASE: "Ready for your approval",
    WAIT: "Wait",
  };
  const STATUS_LABEL = {
    model: "chosen by Nebius", rejected: "model answer blocked by safety rules", error: "model call failed",
  };

  function nextStep(buyer) {
    const entry = state.decisions[buyer];
    if (!entry) {
      const decisions = state.decisions;
      decisions[buyer] = { pending: true };
      chrome.runtime.sendMessage({ type: "vendorscan:decide", body: { ...state.query, fresh: false, buyer } },
        (reply) => {
          decisions[buyer] = reply?.ok ? { data: reply.data } : { error: reply?.error || "Extension error" };
          if (decisions === state.decisions) render();
        });
    }
    const { data: d, error } = state.decisions[buyer] || {};
    const box = (...children) => el("section", { class: "vs-next" },
      el("div", { class: "vs-section-title" }, "Next step"), ...children);
    if (error) return box(el("div", { class: "vs-error" }, `No model decision: ${error}`));
    if (!d) return box(el("div", { class: "vs-hint" }, "Nebius is deciding…"));
    return box(
      el("div", { class: "vs-next-action" }, STEP_LABEL[d.action] || d.action,
        el("span", { class: "vs-hint" }, ` · ${STATUS_LABEL[d.status] || d.status}`)),
      el("p", {}, d.reason),
      d.seller_question && el("blockquote", {}, d.seller_question),
      el("details", {},
        el("summary", {}, `Model calls: ${d.trace.length} · ${d.model} on ${d.provider}`),
        d.trace.map((step) => el("p", {},
          `${step.action || "no answer"} (${step.status}, ${step.latency_ms} ms)`,
          step.search_query ? ` · searched “${step.search_query}”, ${step.sources.length} source(s)` : null)),
        el("ul", {}, d.facts.filter((f) => f.material || d.evidence_ids.includes(f.id))
          .map((f) => el("li", {}, `${f.id}${f.material ? " (open)" : ""}: ${f.text}`)))));
  }

  // idealo's own signals for this product: price level over time and delivery of the top offer.
  function signals(r) {
    const h = r.price_history;
    const top = (r.by_buyer[state.buyer] || [])[0];
    const delivery = top && r.delivery?.[top.offer.offer_id];
    const lines = [
      h && `30 days on idealo: ${euro(h.min_price)}–${euro(h.max_price)}, now ${euro(h.current_price)}`
        + (h.change_percent == null ? "" : ` (${Number(h.change_percent) > 0 ? "+" : ""}${h.change_percent}%)`),
      delivery && `Delivery (${shortSeller(top.offer.seller.name)}): ${delivery}`,
    ].filter(Boolean);
    return lines.length ? el("section", { class: "vs-signals" }, lines.map((t) => el("div", {}, t))) : null;
  }

  function offerRow({ offer, cost }, index, researching) {
    const [tagText, tagCls] = VAT_TAG[offer.tax_status] || VAT_TAG.unknown;
    const pending = researching && offer.tax_status === "unknown";
    const vatMatters = state.buyer === "business_vat";  // private and §19 buyers can't reclaim VAT anyway
    const sameCost = cost.effective_cost_low === cost.effective_cost_high;
    return el("li", { class: index === 0 ? "vs-offer vs-offer-top" : "vs-offer" },
      el("div", { class: "vs-offer-main" },
        link(offer.offer_url, shortSeller(offer.seller.name), "vs-seller"),
        el("div", { class: "vs-tags" },
          vatMatters && el("span", { class: `vs-tag ${pending ? "vs-tag-pending" : tagCls}`, title: offer.tax_basis || null },
            pending ? "checking VAT…" : tagText + (offer.tax_confidence === "likely" ? "*" : "")),
          offer.condition === "used" && el("span", { class: "vs-tag" }, "Used"),
          offer.seller.is_marketplace && el("span", { class: "vs-tag" }, "Marketplace"))),
      el("div", { class: "vs-offer-price" },
        el("div", { class: "vs-cost" }, sameCost ? euro(cost.effective_cost_high)
          : `${euro(cost.effective_cost_low)}–${euro(cost.effective_cost_high)}`),
        cost.total_gross !== cost.effective_cost_high && el("div", { class: "vs-upfront" }, `pay ${euro(cost.total_gross)}`)));
  }

  function offerList(r) {
    const rows = r.by_buyer[state.buyer] || [];
    const shown = state.showAll ? rows : rows.slice(0, 3);
    const researching = state.loading;
    return el("section", { class: "vs-offers" },
      el("div", { class: "vs-section-title" }, state.buyer === "business_vat" ? "Real cost per offer" : "Offers",
        state.buyer !== "business_vat" ? null : el("span", { class: "vs-hint" }, "after VAT")),
      el("ul", {}, shown.map((row, i) => offerRow(row, i, researching))),
      rows.length > 3 && el("button", { class: "vs-more", onclick: () => { state.showAll = !state.showAll; render(); } },
        state.showAll ? "Show less" : `Show all ${rows.length} offers`),
      state.buyer === "business_vat" && rows.some((x) => x.offer.tax_confidence === "likely") &&
        el("div", { class: "vs-foot-note" }, "* expected: new item from a regular shop; ask for an invoice with VAT."));
  }

  function findings(r) {
    const gaps = (r.gaps || []).filter((g) => g.finding);
    if (!gaps.length) return null;
    const VAT_LINE = { standard_vat: "Confirms VAT invoices", margin_scheme: "Margin scheme: no VAT back",
      small_business: "Charges no VAT (§ 19)", private_sale: "Private seller", unknown: "No clear VAT statement found" };
    const line = (g) => {
      const status = (g.finding.match(/^(standard_vat|unknown|margin_scheme|small_business|private_sale):\s*/) || [])[1];
      const detail = g.finding.replace(/^(standard_vat|unknown|margin_scheme|small_business|private_sale):\s*/, "");
      const what = g.gap.replace(/^VAT treatment of\s*/, "").replace(/\s*\(idealo has no VAT field\)/, "");
      const short = status ? VAT_LINE[status] : (detail.length > 90 ? detail.slice(0, 87) + "…" : detail);
      return el("details", { class: "vs-finding" },
        el("summary", {}, el("span", { class: "vs-finding-what" }, status ? shortSeller(what) : what),
          el("span", { class: "vs-finding-text" }, short)),
        status && detail && el("p", { class: "vs-finding-detail" }, detail),
        (g.evidence || []).slice(0, 3).map((ev) =>
          el("blockquote", {}, `“${ev.quote || ""}”`, " ", link(ev.url, host(ev.url), "vs-source"))));
    };
    return el("details", { class: "vs-findings" },
      el("summary", { class: "vs-section-title" }, `What VendorScan figured out (${gaps.length})`),
      gaps.map(line));
  }

  function render() {
    const r = state.result;
    const children = [];
    if (r) {
      children.push(el("div", { class: "vs-product" },
        el("div", { class: "vs-product-name" }, r.product),
        el("div", { class: "vs-meta" },
          r.listed_lowest ? `idealo from ${euro(r.listed_lowest)}` : null,
          r.source.startsWith("replay") ? el("span", { class: "vs-badge" }, "Demo") : null),
        r.exact_match === false && el("div", { class: "vs-note" },
          "This page shows several variants. Showing the closest one; pick a variant for an exact scan.")));
      children.push(el("div", { class: "vs-seg" }, BUYERS.map(([key, label]) =>
        el("button", { class: key === state.buyer ? "vs-seg-on" : null,
          onclick: () => { state.buyer = key; render(); } }, label))));
    }
    if (state.loading && !r?.source?.startsWith("replay")) children.push(progress());
    if (state.error) children.push(el("div", { class: "vs-error" }, state.error));
    if (r) children.push(verdictCard(r), !state.loading && nextStep(state.buyer), signals(r), offerList(r),
      !state.loading && findings(r));
    if (!state.loading) {
      children.push(el("footer", { class: "vs-footer" },
        el("span", {}, "Estimates, not tax advice."),
        el("span", { class: "vs-footer-links" },
          el("button", { class: "vs-link", onclick: () => scanThisPage(true) }, "Rescan"),
          " · Demo: ",
          DEMOS.flatMap(([key, name], i) => [i ? ", " : "", el("button", { class: "vs-link", onclick: () => loadDemo(key) }, name)]))));
    }
    body.replaceChildren(...children.filter(Boolean));
  }

  scanThisPage();

  // Rescan when the user switches product or variant without a full page load.
  let lastPath = location.pathname;
  setInterval(() => {
    if (location.pathname !== lastPath && /OffersOfProduct\//.test(location.pathname)) {
      lastPath = location.pathname;
      setTimeout(() => scanThisPage(), 800);
    }
  }, 1000);
})();
