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

function labelBadge(label) {
  const tip = state.meta?.taxonomy?.evidence_labels?.[label] || "";
  return `<span class="label" data-l="${esc(label)}" title="${esc(tip)}" aria-label="Source type: ${esc(label)}. ${esc(tip)}">${esc(label)}</span>`;
}

function tagChips(item) {
  const chips = [];
  if (item.sector) chips.push(`<span class="chip sector">${esc(item.sector)}</span>`);
  for (const f of item.focus_areas || []) chips.push(`<span class="chip">${esc(f)}</span>`);
  return chips.length ? `<div class="tags">${chips.join("")}</div>` : "";
}

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
    card(i) {
      return `<li class="card">
        <div class="meta">${labelBadge(i.label)}<span>${esc(i.source_name)}${i.journal ? " · " + esc(i.journal) : ""}</span><time>${fmtDate(i.date)}</time></div>
        <h3><a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a></h3>
        ${i.summary ? `<p class="summary">${esc(i.summary)}</p>` : ""}
        ${tagChips(i)}</li>`;
    },
    empty: "No stories match these filters yet.",
  },
  funding: {
    filter(items, f) {
      return items.filter((i) => {
        if (!matchesTags(i, f)) return false;
        if (f.stage && i.round_stage !== f.stage) return false;
        if (f.amount === "unknown") return i.amount_usd == null;
        if (f.amount) {
          const [lo, hi] = f.amount.split("-").map((x) => (x ? Number(x) : null));
          if (i.amount_usd == null || i.amount_usd < lo || (hi != null && i.amount_usd >= hi)) return false;
        }
        return true;
      });
    },
    card(i) {
      const facts = [i.round_stage, i.investors?.length ? "Investors: " + i.investors.join(", ") : null].filter(Boolean);
      return `<li class="card">
        <div class="meta"><span>${esc(i.source_kind)}</span><time>${fmtDate(i.date)}</time>${i.state ? `<span>${esc(i.state)}</span>` : ""}</div>
        <h3>${esc(i.company)}</h3>
        <p class="amount">${esc(fmtMoney(i.amount_usd))}${i.source_kind === "SEC Form D" && i.amount_usd != null ? ' <span class="meta">sold so far, as filed</span>' : ""}</p>
        ${i.offering_amount_usd ? `<p class="meta">Total offering: ${esc(fmtMoney(i.offering_amount_usd))}${i.industry ? " · " + esc(i.industry) : ""}</p>` : ""}
        ${facts.length ? `<p>${esc(facts.join(" · "))}</p>` : ""}
        <p class="meta"><a href="${esc(i.source_url)}" target="_blank" rel="noopener">View source: ${esc(i.source_name)}</a></p>
        ${tagChips(i)}</li>`;
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
        return matchesQuery(f.q, i.title, i.company, i.location);
      });
    },
    card(i) {
      const bits = [i.job_type, i.employment_type, i.seniority, i.remote ? "Remote" : null].filter(Boolean);
      return `<li class="card">
        <div class="meta"><span>${esc(i.company)}</span><span>${esc(i.location || "")}</span>${i.posted ? `<time>Posted ${fmtDate(i.posted)}</time>` : ""}</div>
        <h3><a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a></h3>
        <p class="meta">${esc(bits.join(" · "))}</p>
        <p class="meta">Via ${esc(i.source_name)}${i.source === "remoteok" ? ' (<a href="https://remoteok.com" target="_blank" rel="noopener">RemoteOK</a>)' : ""}</p>
        ${tagChips(i)}</li>`;
    },
    empty: "Nothing to show yet. Jobs appear only from verified company job boards.",
  },
};

function render(name) {
  const list = $(`#${name}-list`);
  const items = state.data[name];
  if (!items) return;
  const rows = VIEWS[name].filter(items, formValues(name));
  $(`[data-count="${name}"]`).textContent = `${rows.length} of ${items.length} shown`;
  if (!rows.length) {
    list.innerHTML = `<li class="empty">${esc(items.length ? VIEWS[name].empty.replace(/ yet.*$/, ".") : VIEWS[name].empty)}</li>`;
    return;
  }
  const n = state.shown[name];
  list.innerHTML = rows.slice(0, n).map(VIEWS[name].card).join("") +
    (rows.length > n ? `<li><button class="more" data-more="${name}">Show more (${rows.length - n} left)</button></li>` : "");
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
  render(name);
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

function renderBrief(brief) {
  if (!brief?.bullets?.length) return;
  $("#brief").innerHTML = `<h2>Today's brief</h2><ul>${brief.bullets
    .map((b) => `<li>${labelBadge(b.label)} ${esc(b.text)} <a href="${esc(b.url)}" target="_blank" rel="noopener">Source</a></li>`)
    .join("")}</ul>`;
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
  renderBrief(state.meta.brief);

  document.addEventListener("click", (e) => {
    const more = e.target.closest("[data-more]");
    if (more) { state.shown[more.dataset.more] += PAGE; render(more.dataset.more); }
    const tab = e.target.closest('[role="tab"]');
    if (tab) selectTab(tab.id.replace("tab-", ""));
  });
  const start = location.hash.slice(1);
  selectTab(VIEWS[start] ? start : "news", false);
}

init();
