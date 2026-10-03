// HealthSurface front end: fetches JSON from /api/*, filters in the browser.
const CONTRACT_SOURCES = [
  ["Magnit", "https://magnitglobal.com"],
  ["Blink UX", "https://blinkux.com"],
  ["Aquent", "https://aquent.com"],
  ["Creative Circle", "https://www.creativecircle.com"],
  ["Robert Half Creative Group", "https://www.roberthalf.com"],
  ["Toptal", "https://www.toptal.com"],
  ["Braintrust", "https://www.usebraintrust.com"],
  ["Contra", "https://contra.com"],
  ["Medix", "https://www.medixteam.com"],
  ["KForce", "https://www.kforce.com"],
  ["Experis", "https://www.experis.com"],
];
const PAGE = 40;
const LEAD_STORIES = 7;  // the lead story plus three rows of two, then the In focus band
const state = { meta: null, data: {}, shown: { news: PAGE, funding: PAGE, jobs: PAGE } };

const $ = (sel, root = document) => root.querySelector(sel);
// Escapes HTML and swaps em-dashes from source titles for commas (house style: no em-dashes).
const esc = (s) => String(s ?? "").replace(/\s*\u2014\s*/g, ", ").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtDate = (d) => {
  if (!d) return "";
  const dt = new Date(d + "T12:00:00");
  return isNaN(dt) ? d : dt.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
};
const fmtMoney = (n) => {
  if (n == null) return "Amount not disclosed";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(n % 1e9 ? 1 : 0)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(n % 1e6 ? 1 : 0)}M`;
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${n}`;
};

async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function fillSelect(select, values, anyLabel) {
  select.innerHTML = `<option value="">${esc(anyLabel)}</option>` + values.map((v) => `<option>${esc(v)}</option>`).join("");
}

// Source type as a newspaper kicker; the tooltip explains what the label means.
function kicker(label) {
  const tip = state.meta?.taxonomy?.evidence_labels?.[label] || "";
  return `<span class="kicker" data-l="${esc(label)}" title="${esc(tip)}" aria-label="Source type: ${esc(label)}. ${esc(tip)}">${esc(label)}</span>`;
}

function tagLine(item) {
  const tags = [];
  if (item.sector) tags.push(`<span class="sector">${esc(item.sector)}</span>`);
  for (const f of item.focus_areas || []) tags.push(`<span>${esc(f)}</span>`);
  return tags.length ? `<div class="tags">${tags.join("")}</div>` : "";
}

const byline = (...parts) => `<div class="byline">${parts.filter(Boolean).map((p) => `<span>${p}</span>`).join("")}</div>`;
const extLink = (url, text) => `<a href="${esc(url)}" target="_blank" rel="noopener">${text}</a>`;

function formValues(name) {
  return Object.fromEntries(new FormData($(`form[data-for="${name}"]`)).entries());
}

const matchesTags = (item, f) =>
  (!f.sector || item.sector === f.sector) && (!f.focus || (item.focus_areas || []).includes(f.focus));
const matchesQuery = (q, ...fields) => !q || fields.join(" ").toLowerCase().includes(q.toLowerCase());

const VIEWS = {
  news: {
    filter(items, f) {
      return items.filter((i) => matchesTags(i, f) && (!f.label || i.label === f.label) && matchesQuery(f.q, i.title, i.source_name));
    },
    card(i, index) {
      const body = `<p class="summary">${esc(i.summary || "")}</p>
        ${byline(esc(i.source_name), i.journal ? esc(i.journal) : "", `<time>${fmtDate(i.date)}</time>`)}
        ${tagLine(i)}`;
      const head = `${kicker(i.label)}<h3>${extLink(i.url, esc(i.title))}</h3>`;
      return index === 0
        ? `<li class="story lead"><div>${head}</div><div>${body}</div></li>`
        : `<li class="story">${head}${body}</li>`;
    },
    empty: "No stories match these filters yet.",
  },
  funding: {
    filter(items, f) {
      return items.filter((i) => {
        if (!matchesTags(i, f)) return false;
        if (f.stage === "none" ? i.round_stage : f.stage && i.round_stage !== f.stage) return false;
        if (f.kind && i.source_kind !== f.kind) return false;
        if (f.amount === "unknown") return i.amount_usd == null;
        if (f.amount) {
          const [lo, hi] = f.amount.split("-").map((x) => (x ? Number(x) : null));
          if (i.amount_usd == null || i.amount_usd < lo || (hi != null && i.amount_usd >= hi)) return false;
        }
        return true;
      });
    },
    card(i) {
      const facts = [i.project_title ? `Project: ${i.project_title}` : null, i.round_stage,
        i.investors?.length ? (i.round_stage === "Grant" ? "Funder: " : "Investors: ") + i.investors.join(", ") : null,
        i.offering_amount_usd ? `Total offering ${fmtMoney(i.offering_amount_usd)}` : null].filter(Boolean);
      const formD = i.source_kind === "SEC Form D";
      return `<li class="row">
        <div>
          <div class="eyebrow">${esc(i.source_kind)}${i.industry ? " · " + esc(i.industry) : ""}</div>
          <h3>${esc(i.company)}</h3>
          ${facts.length ? `<p class="facts">${esc(facts.join(" · "))}</p>` : ""}
          ${byline(`<time>${fmtDate(i.date)}</time>`, esc(i.state || ""), `<span class="src">${extLink(i.source_url, "View source: " + esc(i.source_name))}</span>`)}
          ${tagLine(i)}
        </div>
        <div class="side"><div class="amount">${esc(fmtMoney(i.amount_usd))}</div>
          ${formD && i.amount_usd != null ? '<span class="amount-note">sold so far, as filed</span>' : ""}</div>
      </li>`;
    },
    empty: "Nothing to show yet. Funding records appear after the next refresh.",
  },
  jobs: {
    filter(items, f) {
      return items.filter((i) => {
        if (!matchesTags(i, f)) return false;
        if (f.group && i.function_group !== f.group) return false;
        if (f.type && i.job_type !== f.type) return false;
        if (f.employment && i.employment_type !== f.employment) return false;
        if (f.remote === "remote" && !i.remote) return false;
        if (f.remote === "onsite" && i.remote) return false;
        const countries = i.countries || [];
        if (f.country === "none" ? countries.length : f.country && !countries.includes(f.country)) return false;
        return matchesQuery(f.q, i.title, i.company, i.location, ...countries);
      });
    },
    card(i) {
      const bits = [i.job_type, i.employment_type, i.seniority, i.remote ? "Remote" : null].filter(Boolean);
      // Remote OK's API terms: name "Remote OK" and link (no nofollow) to the posting on remoteok.com.
      const via = i.source === "remoteok" ? `Via ${extLink(i.url, "Remote OK")}` : `Via ${esc(i.source_name)}`;
      return `<li class="row">
        <div>
          <div class="eyebrow">${esc(i.company)}</div>
          <h3>${extLink(i.url, esc(i.title))}</h3>
          <p class="facts">${esc(bits.join(" · "))}</p>
          ${byline(esc(i.location || ""), i.posted ? `<time>Posted ${fmtDate(i.posted)}</time>` : "", via)}
          ${tagLine(i)}
        </div>
        <div class="side">${extLink(i.url, "Apply").replace("<a ", '<a class="pill" ')}</div>
      </li>`;
    },
    empty: "Nothing to show yet. Jobs appear only from verified company job boards.",
  },
};

function render(name) {
  const list = $(`#${name}-list`);
  const rest = $(`#${name}-list-more`);  // News only: stories after the In focus band
  const items = state.data[name];
  if (!items) return;
  const rows = VIEWS[name].filter(items, formValues(name));
  $(`[data-count="${name}"]`).textContent = `${rows.length} of ${items.length} shown`;
  if (rest) rest.innerHTML = "";
  if (!rows.length) {
    list.innerHTML = `<li class="empty">${esc(items.length ? VIEWS[name].empty.replace(/ yet.*$/, ".") : VIEWS[name].empty)}</li>`;
    return;
  }
  const n = state.shown[name];
  const cards = rows.slice(0, n).map((row, idx) => VIEWS[name].card(row, idx));
  const more = rows.length > n ? `<li><button class="more" data-more="${name}">Show more (${rows.length - n} left)</button></li>` : "";
  if (rest) {
    list.innerHTML = cards.slice(0, LEAD_STORIES).join("");
    rest.innerHTML = cards.slice(LEAD_STORIES).join("") + more;
  } else {
    list.innerHTML = cards.join("") + more;
  }
}

async function load(name) {
  if (state.data[name]) return render(name);
  $(`#${name}-list`).innerHTML = `<li class="empty">Loading…</li>`;
  try {
    state.data[name] = (await getJSON(`/api/${name}`)).items || [];
  } catch (err) {
    $(`#${name}-list`).innerHTML = `<li class="empty">Could not load right now. Please try again in a minute.</li>`;
    return;
  }
  if (name === "jobs") fillCountries(state.data.jobs);
  if (name === "funding") fillFundingFilters(state.data.funding);
  if (name === "news") renderFocus();
  render(name);
}

// Round stage keeps the taxonomy order but shows counts and disables stages with no records,
// since SEC Form D filings never state a round. Source options come from the data.
function fillFundingFilters(rows) {
  const form = $('form[data-for="funding"]');
  const stages = {}, kinds = {};
  for (const r of rows) {
    stages[r.round_stage || "none"] = (stages[r.round_stage || "none"] || 0) + 1;
    kinds[r.source_kind] = (kinds[r.source_kind] || 0) + 1;
  }
  form.stage.innerHTML = `<option value="">All stages</option>` +
    state.meta.taxonomy.round_stages.map((st) => `<option value="${esc(st)}"${stages[st] ? "" : " disabled"}>${esc(st)} (${stages[st] || 0})</option>`).join("") +
    `<option value="none"${stages.none ? "" : " disabled"}>Not stated (${stages.none || 0})</option>`;
  form.kind.innerHTML = `<option value="">All sources</option>` +
    Object.entries(kinds).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<option value="${esc(k)}">${esc(k)} (${n})</option>`).join("");
}

// Country options come from the data, most common first, plus jobs with no stated country.
function fillCountries(jobs) {
  const counts = {};
  for (const j of jobs) for (const c of j.countries || []) counts[c] = (counts[c] || 0) + 1;
  $('form[data-for="jobs"] select[name="country"]').innerHTML =
    `<option value="">All countries</option>` +
    Object.entries(counts).sort((a, b) => b[1] - a[1])
      .map(([c, n]) => `<option value="${esc(c)}">${esc(c)} (${n})</option>`).join("") +
    `<option value="none">Not stated (for example "Remote")</option>`;
}

function selectTab(name, push = true) {
  for (const tab of document.querySelectorAll('[role="tab"]')) {
    const on = tab.id === `tab-${name}`;
    tab.setAttribute("aria-selected", on);
    $(`#${tab.getAttribute("aria-controls")}`).hidden = !on;
  }
  if (push) history.replaceState(null, "", `#${name}`);
  load(name);
}

// ---------- "In focus" band: a featured story plus a scrolling playlist that advances on its own ----------
const focus = { items: [], index: 0, timer: null, paused: false, dwell: 9000 };
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function focusItems() {
  const stories = state.data.news || [];
  const byUrl = new Map(stories.map((s) => [s.url, s]));
  const picks = (state.meta?.brief?.bullets || []).map((b) => byUrl.get(b.url) || { ...b, summary: b.text }).filter(Boolean);
  for (const s of stories) {  // top up to 8 with the newest summarized stories
    if (picks.length >= 8) break;
    if (s.summary && !picks.some((p) => p.url === s.url)) picks.push(s);
  }
  return picks;
}

function renderFocus() {
  focus.items = focusItems();
  const el = $("#focus");
  if (!focus.items.length) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `<div class="wrap">
    <div class="focus-head"><h2>In focus</h2><p>A closer look at today's picks.</p></div>
    <div class="focus-grid">
      <article class="feature" aria-live="polite"></article>
      <div class="playlist"><p class="playlist-label">Up next</p><ol>${focus.items.map((it, i) => `
        <li><button type="button" data-focus="${i}">
          <span class="num">${String(i + 1).padStart(2, "0")}</span>
          <span>${kicker(it.label)}<span class="t">${esc(it.title)}</span></span>
        </button></li>`).join("")}</ol></div>
    </div></div>`;
  const pause = () => { focus.paused = true; $("#focus .progress span").style.animationPlayState = "paused"; };
  const resume = () => { if (focus.paused) { focus.paused = false; showFocus(focus.index); } };
  el.addEventListener("mouseenter", pause);
  el.addEventListener("mouseleave", resume);
  el.addEventListener("focusin", pause);
  el.addEventListener("focusout", (e) => { if (!el.contains(e.relatedTarget)) resume(); });
  showFocus(0);
}

// Scroll only the "Up next" list. scrollIntoView would also scroll the page and pull
// readers back up to the band every time it advances.
function revealInPlaylist(item) {
  const list = item.parentElement;
  const top = item.offsetTop;
  const bottom = top + item.offsetHeight;
  let target = null;
  if (top < list.scrollTop) target = top;
  else if (bottom > list.scrollTop + list.clientHeight) target = bottom - list.clientHeight;
  if (target !== null) list.scrollTo({ top: target, behavior: reducedMotion ? "auto" : "smooth" });
}

function showFocus(i) {
  focus.index = (i + focus.items.length) % focus.items.length;
  const it = focus.items[focus.index];
  const feature = $("#focus .feature");
  feature.classList.remove("playing");
  feature.innerHTML = `${kicker(it.label)}
    <h3>${extLink(it.url, esc(it.title))}</h3>
    ${it.summary ? `<p class="summary">${esc(it.summary)}</p>` : ""}
    <div class="feature-actions">
      ${extLink(it.url, "Read at the source &rarr;").replace("<a ", '<a class="btn" ')}
      <span class="feature-meta">${[esc(it.source_name || ""), fmtDate(it.date)].filter(Boolean).join(" · ")}</span>
    </div>
    <div class="progress" aria-hidden="true"><span></span></div>`;
  for (const b of document.querySelectorAll("#focus [data-focus]")) {
    const on = Number(b.dataset.focus) === focus.index;
    b.setAttribute("aria-current", on);
    if (on) revealInPlaylist(b.parentElement);
  }
  clearTimeout(focus.timer);
  if (reducedMotion) return;
  feature.style.setProperty("--dwell", `${focus.dwell / 1000}s`);
  void feature.offsetWidth;  // restart the progress animation
  feature.classList.add("playing");
  const tick = () => {
    if (focus.paused) return;  // resume() restarts the timer
    if (document.hidden || $("#panel-news").hidden) { focus.timer = setTimeout(tick, 1000); return; }
    showFocus(focus.index + 1);
  };
  focus.timer = setTimeout(tick, focus.dwell);
}

// ---------- Summary band: the AI-written daily summary, with links to every source it mentions ----------
function renderSummary() {
  const sum = state.meta?.summary;
  const el = $("#summary");
  if (!sum?.paragraphs?.length) { el.hidden = true; return; }
  const canSpeak = sum.audio || ("speechSynthesis" in window && sum.spoken);
  el.hidden = false;
  el.innerHTML = `<div class="wrap">
    <div class="focus-head"><h2>Summary</h2><p>Today's top health news in a couple of minutes.</p></div>
    <div class="focus-grid">
      <article class="feature summary-card">
        <p class="summary-eyebrow">${esc(sum.day || fmtDate(sum.date))} · Written by AI</p>
        <h3>Today's ${esc(state.meta.app || "HealthSurface")} summary</h3>
        <div class="summary-text">${sum.paragraphs.map((p) => `<p>${esc(p)}</p>`).join("")}</div>
        <div class="feature-actions">
          ${canSpeak ? `<button type="button" class="btn" data-listen aria-pressed="false">&#9654; Listen</button>` : ""}
          <span class="feature-meta">Written by an AI model from the ${sum.sources.length} sources listed${sum.audio ? " and read by an Amazon Polly voice" : ""}. It can make mistakes, so check the source.</span>
        </div>
      </article>
      <div class="playlist"><p class="playlist-label">Sources in this summary</p><ol>${sum.sources.map((src, i) => `
        <li>${extLink(src.url, `
          <span class="num">${String(i + 1).padStart(2, "0")}</span>
          <span>${kicker(src.label)}<span class="t">${esc(src.title)}</span><span class="src-name">${esc(src.source_name)} &#8599;</span></span>`)}</li>`).join("")}</ol></div>
    </div></div>`;
}

// Plays the summary's Amazon Polly recording, the same audio voice assistants play. Without one,
// the browser reads the text with its own voice.
let player = null;
function toggleListen(btn) {
  const set = (on) => { btn.setAttribute("aria-pressed", on); btn.innerHTML = on ? "&#9632; Stop" : "&#9654; Listen"; };
  const sum = state.meta.summary;
  if (sum.audio) {
    if (player && !player.paused) { player.pause(); player.currentTime = 0; set(false); return; }
    player = player || new Audio(sum.audio);
    player.onended = player.onerror = () => set(false);
    set(true);
    player.play().catch(() => set(false));
    return;
  }
  const synth = window.speechSynthesis;
  if (synth.speaking) { synth.cancel(); set(false); return; }
  const say = new SpeechSynthesisUtterance(sum.spoken);
  say.lang = "en-US";
  say.onend = say.onerror = () => set(false);
  set(true);
  synth.speak(say);
}

// ---------- Ask what's new: answers only from stored items, with sources ----------
function renderAsk() {
  if (!state.meta?.ask_enabled) return;  // kill switch: the launcher stays hidden
  const panel = $("#ask"), fab = $(".ask-fab");
  fab.hidden = false;
  const setOpen = (open) => {
    panel.hidden = !open;
    fab.setAttribute("aria-expanded", String(open));
    fab.classList.toggle("is-open", open);
    if (open) input.focus(); else fab.focus();
  };
  fab.addEventListener("click", () => setOpen(panel.hidden));
  $(".ask-close").addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panel.hidden) setOpen(false); });
  const form = $(".ask-form"), out = $(".ask-out"), input = $("#ask-q");
  const show = (html, cls = "") => { out.className = `ask-out ${cls}`; out.innerHTML = html; out.scrollIntoView({ block: "nearest" }); };
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) { show(`<p>Type a question first.</p>`, "is-note"); return; }
    form.querySelector("button").disabled = true;
    show(`<p>Looking through stored stories…</p>`, "is-loading");
    let data;
    try {
      const res = await fetch("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }) });
      data = await res.json();
    } catch {
      data = { state: "error", answer: "Something went wrong. Please try again in a minute.", sources: [] };
    }
    form.querySelector("button").disabled = false;
    const sources = (data.sources || []).map((s) => `<li>${kicker(s.label)} ${extLink(s.url, esc(s.title))} <span class="ask-src">${esc(s.source_name)}</span></li>`).join("");
    const left = data.remaining != null && data.remaining <= 3 && data.state !== "limited" ? `<p class="ask-left">${data.remaining} question${data.remaining === 1 ? "" : "s"} left today</p>` : "";
    show(`<p>${esc(data.answer)}</p>${sources ? `<p class="ask-sources-label">Sources</p><ul class="ask-sources">${sources}</ul>` : ""}${left}`, `is-${data.state}`);
  });
  document.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-chip]");
    if (chip) { input.value = chip.textContent; form.requestSubmit(); }
  });
}

async function init() {
  try {
    state.meta = await getJSON("/api/meta");
  } catch {
    state.meta = { taxonomy: { sectors: [], focus_areas: [], evidence_labels: {}, round_stages: [], function_groups: {}, employment_types: [] } };
  }
  const t = state.meta.taxonomy;
  if (state.meta.app) {
    document.title = state.meta.app;
    $("[data-app-name]").textContent = state.meta.app;
    $("[data-tagline]").textContent = state.meta.tagline;
    $("[data-disclaimer]").textContent = state.meta.disclaimer;
  }
  for (const form of document.querySelectorAll("form.filters")) {
    if (form.sector) fillSelect(form.sector, t.sectors, "All sectors");
    if (form.focus) fillSelect(form.focus, t.focus_areas, "All focus areas");
    if (form.label) fillSelect(form.label, Object.keys(t.evidence_labels), "All source types");
    if (form.stage) fillSelect(form.stage, t.round_stages, "All stages");
    if (form.group) fillSelect(form.group, Object.keys(t.function_groups), "All functions");
    if (form.type) fillSelect(form.type, [...Object.values(t.function_groups).flat(), "Other"], "All job types");
    if (form.employment) fillSelect(form.employment, t.employment_types, "Any type");
    const name = form.dataset.for;
    form.addEventListener("input", () => { state.shown[name] = PAGE; render(name); });
    form.addEventListener("submit", (e) => e.preventDefault());
  }
  $("#contract-links").innerHTML = CONTRACT_SOURCES
    .map(([n, u]) => `<li><a href="${u}" target="_blank" rel="noopener">${esc(n)}</a></li>`).join("");
  if (state.meta.last_run) {
    $("[data-last-run]").textContent = `Last refreshed ${new Date(state.meta.last_run).toLocaleString()}.`;
  }
  renderSummary();
  renderAsk();
  $("[data-dateline]").textContent = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  document.addEventListener("click", (e) => {
    const more = e.target.closest("[data-more]");
    if (more) { state.shown[more.dataset.more] += PAGE; render(more.dataset.more); }
    const listen = e.target.closest("[data-listen]");
    if (listen) toggleListen(listen);
    const pick = e.target.closest("[data-focus]");
    if (pick) showFocus(Number(pick.dataset.focus));
    const tab = e.target.closest('[role="tab"]');
    if (tab) selectTab(tab.id.replace("tab-", ""));
  });
  const start = location.hash.slice(1);
  selectTab(VIEWS[start] ? start : "news", false);
}

init();
