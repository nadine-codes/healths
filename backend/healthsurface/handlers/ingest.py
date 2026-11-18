"""Scheduled ingest: fetch, dedupe, check free-to-read, classify (capped), store."""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


from .. import classify, config
from ..sources import funding as funding_src
from ..sources import grants as grants_src
from ..sources import jobs as jobs_src
from ..sources import news as news_src
from ..sources import offerings as offerings_src
from . import bedrock, store, voice

log = logging.getLogger()
log.setLevel(logging.INFO)

STORED_NEWS_FIELDS = ("id", "url", "title", "date", "source", "source_name", "label",
                      "journal", "category", "license", "company")


def _model():
    return bedrock.invoke if bedrock.MODEL_ID else None


def ingest_news(report: dict) -> list[dict]:
    fetched, report["sources"] = news_src.fetch_all()
    existing = {r["id"]: r for r in store.scan_all(store.news, "id, classifier")}

    # Dedupe by URL hash within this batch and against the table. Stored items that only got
    # the keyword fallback are retried with the model once the new items are done.
    batch, retry, seen = [], [], set()
    for item in fetched:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        if item["id"] not in existing:
            batch.append(item)
        elif existing[item["id"]].get("classifier") == "rules":
            retry.append(item)

    skipped, kept = [], []
    for item in batch:
        if classify.is_blocked_story(item["title"], item.get("description")):
            skipped.append({"url": item["url"], "reason": "blocked topic"})
            continue
        meta = config.NEWS_SOURCES[item["source"]]
        if not meta["free_to_read"]:
            skipped.append({"url": item["url"], "reason": "source not free to read"})
            continue
        if meta.get("commercial"):
            ok, reason = news_src.free_to_read(item["url"])
            if not ok:
                skipped.append({"url": item["url"], "reason": reason})
                continue
        kept.append(item)

    kept.extend(retry)
    invoke = _model()
    rows, funding_rows, model_calls = [], [], 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for item in kept:
        use_model = invoke if model_calls < config.MAX_NEW_STORIES_PER_RUN else None
        if use_model is None and item["id"] in existing:
            continue  # retry only when model budget remains this run
        result, method = classify.classify_story(item, use_model)
        model_calls += use_model is not None
        row = {k: item[k] for k in STORED_NEWS_FIELDS if item.get(k)}
        row.update(sector=result["sector"], focus_areas=result["focus_areas"], summary=result["summary"],
                   confidence=result["confidence"], classifier=method, is_funding=result["is_funding_announcement"],
                   ingested_at=now, prompt_v=PROMPT_VERSION)
        rows.append(row)
        if result.get("funding") and story_can_be_funding(row):
            funding_rows.append(funding_from_story(row, result["funding"]))

    store.put_many(store.news, rows)
    store.put_many(store.funding, funding_rows)
    report["news"] = {"fetched": len(fetched), "new": len(batch), "stored": len(rows),
                      "retried": len(retry), "skipped": len(skipped), "model_calls": model_calls}
    report["skipped"] = skipped[:50]
    for s in skipped:
        log.info("skipped %s: %s", s["url"], s["reason"])
    return rows


PROMPT_VERSION = 2  # bump when the story prompt changes; the "retag" stage reclassifies older rows


def retag_news(report: dict) -> None:
    """Re-run sector and focus tagging on stored stories classified with an older prompt.

    Feed descriptions are not stored, so a story still in today's feeds is fully reclassified
    (including a fresh summary); older stories are retagged from the headline and keep their
    summary. Capped like a normal run.
    """
    invoke = _model()
    if not invoke:
        return
    stale = [r for r in store.scan_all(store.news) if r.get("prompt_v") != PROMPT_VERSION]
    stale = stale[: config.MAX_NEW_STORIES_PER_RUN]
    live = {i["id"]: i for i in news_src.fetch_all()[0]} if stale else {}
    for row in stale:
        item = live.get(row["id"]) or {"title": row["title"], "label": row["label"], "source_name": row["source_name"],
                                       "description": row.get("journal") or row.get("category") or ""}
        result, method = classify.classify_story(item, invoke)
        row["prompt_v"] = PROMPT_VERSION  # a failed retry keeps its tags and is not retried forever
        if method == "model":
            row.update(sector=result["sector"], focus_areas=result["focus_areas"], classifier="model")
            if row["id"] in live:
                row["summary"] = result["summary"]
    store.put_many(store.news, stale)
    report["retag"] = {"stale": len(stale), "live": sum(r["id"] in live for r in stale)}


# Government newsrooms announce payments and grants to providers, not companies raising money, and an
# old story resurfacing in a feed isn't current funding news (NAD-63).
GOVERNMENT_SOURCES = {"openfda_drugs", "openfda_devices", "cms_newsroom", "cdc_newsroom"}
GOVERNMENT_NAMES = {config.NEWS_SOURCES[k]["name"] for k in GOVERNMENT_SOURCES if k in config.NEWS_SOURCES}
NEWS_FUNDING_MAX_AGE = timedelta(days=90)


def story_can_be_funding(story: dict, today=None) -> bool:
    today = today or datetime.now(timezone.utc).date()
    if story.get("source") in GOVERNMENT_SOURCES or story.get("source_name") in GOVERNMENT_NAMES:
        return False
    return (story.get("date") or "") >= str(today - NEWS_FUNDING_MAX_AGE)


def funding_cleanup(rows: list[dict], today=None) -> tuple[list[str], list[dict]]:
    """Stored funding rows to delete (investment vehicles, government or stale news funding) and NIH
    grants whose sector the title-based rule now sorts differently."""
    drop, resort = [], []
    for r in rows:
        kind = r.get("source_kind")
        if kind == "SEC Form D" and funding_src.is_investment_vehicle(r.get("company", "")):
            drop.append(r["id"])
        elif kind == "News story" and not story_can_be_funding(r, today):
            drop.append(r["id"])
        elif r["id"].startswith("nih#"):
            sector = grants_src.grant_sector(r.get("project_title", ""))
            if sector != r.get("sector"):
                resort.append({**r, "sector": sector})
    return drop, resort


def funding_from_story(story: dict, f: dict) -> dict:
    return {
        "id": f"news#{story['id']}",
        "company": f["company"],
        "amount_usd": f.get("amount_usd"),
        "round_stage": f.get("round_stage"),
        "date": f.get("date") or story["date"],
        "investors": f.get("investors") or [],
        "source_url": story["url"],
        "source_name": story["source_name"],
        "source_kind": "News story",
        "sector": story["sector"],
        "focus_areas": story["focus_areas"],
    }


def ingest_funding(report: dict) -> None:
    stored = store.scan_all(store.funding)
    existing = {r["id"] for r in stored}
    rows = funding_src.fetch_new(existing)
    try:
        grants = grants_src.fetch_new(existing)
    except Exception as err:  # noqa: BLE001 - grants are additive; Form D still lands
        log.warning("NIH RePORTER failed: %s", err)
        grants = []
    try:
        offerings = offerings_src.fetch_new([r for r in stored if r.get("source_kind") == offerings_src.KIND])
    except Exception as err:  # noqa: BLE001 - offerings are additive too
        log.warning("8-K offerings failed: %s", err)
        offerings = []
    announced = funding_src.announced_rounds()
    drop, resort = funding_cleanup(stored)
    store.put_many(store.funding, rows + grants + offerings + announced + resort)
    store.delete_many(store.funding, drop)
    report["funding"] = {"form_d_new": len(rows), "nih_grants_new": len(grants), "offerings_new": len(offerings),
                         "announced": len(announced), "removed": len(drop), "resorted": len(resort)}


JOB_FIELDS = ("id", "company", "title", "url", "location", "remote", "posted", "source", "source_name",
              "sector", "focus_areas", "employer_check")


def _discover_companies(report: dict) -> list[dict]:
    """Verify job boards for companies that appeared in news funding announcements."""
    state = store.get_meta("job_companies") or {"verified": [], "tried": []}
    known = {c["name"].lower() for c in jobs_src.COMPANIES + state["verified"]} | set(state["tried"])
    candidates = {r["company"]: r for r in store.scan_all(store.funding)
                  if r.get("source_kind") in ("News story", funding_src.ANNOUNCED_KIND)}
    added = []
    for name, rec in list(candidates.items())[:20]:
        if name.lower() in known:
            continue
        found = jobs_src.verify_company(name, rec.get("sector"), rec.get("focus_areas") or [])
        state["tried"].append(name.lower())
        if found:
            state["verified"].append(found)
            added.append(name)
    store.put_meta("job_companies", state)
    report["jobs_companies_added"] = added
    return state["verified"]


MAX_JOB_ATTEMPTS = 3  # a job the model keeps failing on keeps its keyword tags instead of costing every run


def ingest_jobs(report: dict) -> None:
    extra = _discover_companies(report)
    fetched, report["job_sources"], boards_ok = jobs_src.fetch_all(extra)
    existing = {r["id"]: r for r in store.scan_all(store.jobs, "id, classifier, job_type, seniority, attempts, employer_check")}
    fetched = list({j["id"]: j for j in fetched}.values())
    # Remote OK rows checked by an older employer check are handled again as new (NAD-64).
    unsorted_remote = {i for i, r in existing.items()
                       if i.startswith("remoteok#") and r.get("employer_check") != classify.EMPLOYER_CHECK}
    new = [j for j in fetched if j["id"] not in existing or j["id"] in unsorted_remote]

    invoke = _model()
    remote = [j for j in new if j.get("source") == "remoteok"]
    with ThreadPoolExecutor(4) as pool:
        sectors = dict(zip([j["id"] for j in remote], pool.map(lambda j: classify.employer_sector(j, invoke), remote)))
    not_health = {i for i, s in sectors.items() if s is None}
    for j in remote:
        j.update(sector=sectors[j["id"]], employer_check=classify.EMPLOYER_CHECK)
    new = [j for j in new if j["id"] not in not_health]
    store.delete_many(store.jobs, [i for i in not_health if i in existing] +
                      [i for i in unsorted_remote if i not in {j["id"] for j in fetched}])

    def needs_retry(row):  # rows tagged by an older job prompt, or keyword-only rows with attempts left
        return row and row.get("classifier") != classify.JOB_CLASSIFIER and row.get("attempts", 0) < MAX_JOB_ATTEMPTS

    retry = [j for j in fetched if needs_retry(existing.get(j["id"])) and j["id"] not in not_health]

    to_model = (new + retry)[: config.MAX_NEW_JOBS_PER_RUN] if invoke else []
    model_ids = {j["id"] for j in to_model}
    with ThreadPoolExecutor(4) as pool:
        modelled = {j["id"]: res for j, res in zip(to_model, pool.map(lambda j: classify.classify_job(j, invoke), to_model))}

    rows = []
    for job in new + [j for j in retry if j["id"] in model_ids]:
        result, method = modelled.get(job["id"]) or classify.classify_job(job)
        row = {k: job[k] for k in JOB_FIELDS if job.get(k) not in (None, "")}
        row.update(result, classifier=method)
        if method != classify.JOB_CLASSIFIER:  # model failed (throttled or bad reply): count it
            row["attempts"] = existing.get(job["id"], {}).get("attempts", 0) + 1
        rows.append(row)
    refreshed = refresh_rule_rows(fetched, existing, model_ids)
    rows += refreshed
    store.put_many(store.jobs, rows)

    configured = jobs_src.board_prefixes(extra)
    failures = board_failures(store.get_meta("board_failures") or {}, configured, boards_ok)
    store.put_meta("board_failures", failures)
    closed = closed_job_ids(existing, {j["id"] for j in fetched}, boards_ok, configured, failures)
    store.delete_many(store.jobs, closed)
    report["jobs"] = {"fetched": len(fetched), "new": len(new), "stored": len(rows), "model": len(to_model),
                      "remote_not_health": len(not_health),
                      "rules_refreshed": len(refreshed), "closed_removed": len(closed)}


MAX_BOARD_FAILURES = 6  # three days of twice-daily runs


def board_failures(previous: dict, configured: set, boards_ok: set) -> dict:
    """Consecutive failed runs per configured board; a board that loads resets to 0."""
    return {p: 0 if p in boards_ok else int(previous.get(p, 0)) + 1 for p in configured if p != "id"}


def closed_job_ids(existing: dict, live: set, boards_ok: set, configured: set, failures: dict) -> list:
    """Stored jobs to remove: gone from a board that loaded, from a board that has failed
    MAX_BOARD_FAILURES runs in a row, or from a board we no longer read (a company that moved boards)."""
    dead = {p for p, n in failures.items() if n >= MAX_BOARD_FAILURES}
    def board(i):
        return next((p for p in configured if i.startswith(p)), None)
    return [i for i in existing if i not in live and (board(i) is None or board(i) in boards_ok | dead)]


def refresh_rule_rows(fetched: list, existing: dict, skip: set) -> list:
    """Keyword-only rows the model gave up on follow the current keyword rules.
    Free (no model calls); a row is rewritten only when its tags change."""
    rows = []
    for job in fetched:
        old = existing.get(job["id"])
        if (not old or job["id"] in skip or old.get("classifier") != "rules"
                or old.get("attempts", 0) < MAX_JOB_ATTEMPTS):
            continue
        result = classify.rule_classify_job(job)
        if result["job_type"] != old.get("job_type") or result["seniority"] != old.get("seniority"):
            row = {k: job[k] for k in JOB_FIELDS if job.get(k) not in (None, "")}
            row.update(result, classifier="rules", attempts=old["attempts"])
            rows.append(row)
    return rows


def ingest_brief(report: dict) -> None:
    """Today's brief: one model call per day from stories already stored."""
    today = datetime.now(timezone.utc).date().isoformat()
    current = store.get_meta("brief")
    if current and current.get("date") == today:
        report["brief"] = "already built today"
        return
    invoke = _model()
    if not invoke:
        return
    recent = [s for s in sorted(store.scan_all(store.news), key=lambda s: s.get("date") or "", reverse=True)
              if s.get("classifier") == "model" and not classify.is_blocked_story(s.get("title"), s.get("summary"))][:25]
    bullets = classify.todays_brief(recent, invoke)
    store.put_meta("brief", {"date": today, "bullets": bullets})
    report["brief"] = len(bullets)


SUMMARY_TZ = ZoneInfo("America/New_York")  # the summary is dated for US morning listeners


def _spoken_money(n: float) -> str:
    for size, word in ((1e9, "billion"), (1e6, "million")):
        if n >= size:
            return f"${n / size:.1f}".removesuffix(".0") + f" {word}"
    return f"${n:,.0f}"


def _funding_title(r: dict) -> str:
    money = _spoken_money(r["amount_usd"])
    if r["source_kind"].startswith("NIH"):
        return f"{r['company']} was awarded a {money} {r['source_kind']}"
    if r["source_kind"] == offerings_src.KIND:
        what = {"IPO": "initial public offering", "Public offering": "public stock offering",
                "Private placement": "private placement"}.get(r.get("round_stage"), "financing")
        return f"{r['company']} announced a {money} {what} in an SEC filing"
    return f"{r['company']} reported raising {money} in an SEC Form D filing"


def summary_items(today) -> list[dict]:
    """Stories from the last three days plus the week's biggest SEC and NIH funding, newest first."""
    stories = sorted((s for s in store.scan_all(store.news) if s.get("classifier") == "model" and s.get("summary")
                      and not classify.is_blocked_story(s.get("title"), s.get("summary"))),
                     key=lambda s: s.get("date") or "", reverse=True)
    cutoff = (today - timedelta(days=3)).isoformat()
    picked = [s for s in stories if (s.get("date") or "") >= cutoff][:30]
    picked += [s for s in stories if s not in picked][: max(0, 15 - len(picked))]
    week = (today - timedelta(days=7)).isoformat()
    money = sorted((r for r in store.scan_all(store.funding) if r.get("amount_usd") and (r.get("date") or "") >= week
                    and r.get("source_kind") != "News story"),  # news funding is already in the stories
                   key=lambda r: r["amount_usd"], reverse=True)[:classify.SUMMARY_MAX_FUNDING + 1]
    funding = [{"title": _funding_title(r),
                "summary": f"Project: {r['project_title']}." if r.get("project_title") else "",
                "company": r["company"], "amount": _spoken_money(r["amount_usd"]),
                "label": r["source_kind"], "source_name": r["source_name"], "url": r["source_url"]} for r in money]
    return [{k: s.get(k) for k in ("title", "summary", "label", "source_name", "url")} for s in picked] + funding


def ingest_summary(report: dict) -> None:
    """The daily summary: usually one model call per run, at most four."""
    invoke = _model()
    if not invoke:
        return
    now = datetime.now(SUMMARY_TZ)
    items = summary_items(now.date())
    # Nova 2 Lite writes it; if its replies fail the checks twice (or the model is unavailable), Nova Pro tries.
    for model in (bedrock.SUMMARY_MODEL_ID, bedrock.SUMMARY_FALLBACK_MODEL_ID):
        try:
            summary = classify.todays_summary(items, lambda system, user: bedrock.invoke(system, user, 1500, model, 0.5))
            report["summary_model"] = model
            break
        except Exception as err:  # noqa: BLE001 - the stored summary stays if every writer fails
            log.warning("summary with %s failed: %s", model, err)
            last_err = err
    else:
        raise last_err
    day, dropped = f"{now:%A}, {now:%B} {now.day}", summary.pop("dropped")
    generated = datetime.now(timezone.utc)
    spoken = classify.spoken_summary(summary, day)
    try:  # a natural recorded voice; without it, Listen falls back to the browser's voice
        audio = voice.record(spoken, f"audio/summary-{generated:%Y%m%dT%H%M%S}.mp3")
    except Exception as err:  # noqa: BLE001 - the summary text still publishes
        log.warning("summary recording failed: %s", err)
        audio = None
    store.put_meta("summary", {**summary, "date": now.date().isoformat(), "day": day, "spoken": spoken,
                               "generated_at": generated.isoformat(timespec="seconds"), "audio": audio})
    report["summary"] = {"items": len(items), "cited": len(summary["sources"]), "dropped": dropped,
                         "audio": audio, "voice": voice.VOICE}


TICKER_EACH = 8
TICKER_MIN_AMOUNT = 1e6  # leaves out placeholder Form D amounts such as $1
TICKER_LABELS = {"Reported news", "Press release", "Regulatory action"}  # titles that read as headlines


def ticker_items(news: list, funding: list) -> dict:
    """The few fields the top ticker needs, newest first, so the page can show it without the full lists."""
    newest = lambda rows: sorted(rows, key=lambda r: r.get("date") or "", reverse=True)  # noqa: E731
    seen, rounds = set(), []
    for r in newest(funding):
        if (r.get("amount_usd") or 0) >= TICKER_MIN_AMOUNT and r.get("company") not in seen:
            seen.add(r.get("company"))
            rounds.append({k: r.get(k) for k in ("company", "amount_usd", "source_kind", "source_url")})
    heads = [{k: r.get(k) for k in ("label", "title", "url")} for r in newest(news)
             if r.get("label") in TICKER_LABELS and not classify.is_blocked_story(r.get("title"), r.get("summary"))]
    return {"funding": rounds[:TICKER_EACH], "news": heads[:TICKER_EACH]}


def ingest_ticker(report: dict) -> None:
    ticker = ticker_items(store.scan_all(store.news), store.scan_all(store.funding))
    store.put_meta("ticker", ticker)
    report["ticker"] = {k: len(v) for k, v in ticker.items()}


# Sectors retired on 2026-11-16 (NAD-64): almost nothing used them. They live on as focus areas.
RETIRED_SECTORS = {"Peptides": ("Pharma", "Peptides and GLP-1s"),
                   "Supplements and Nutraceuticals": ("Life Sciences and Biotech", "Supplements")}


def retire_sectors(rows: list[dict]) -> list[dict]:
    moved = []
    for r in rows:
        if r.get("sector") in RETIRED_SECTORS:
            sector, focus = RETIRED_SECTORS[r["sector"]]
            areas = r.get("focus_areas") or []
            moved.append({**r, "sector": sector, "focus_areas": areas if focus in areas else areas[:2] + [focus]})
    return moved


def ingest_retire_sectors(report: dict) -> None:
    counts = {}
    for name, table in (("news", store.news), ("funding", store.funding), ("jobs", store.jobs)):
        moved = retire_sectors(store.scan_all(table))
        store.put_many(table, moved)
        counts[name] = len(moved)
    report["retired_sectors"] = counts


def ingest_news_cleanup(report: dict) -> None:
    """Applies the topic rules to stored stories (NAD-68): blocked headlines and stories from sources we
    no longer read (NAD-69) are deleted, race sentences come out of summaries, and today's In Focus picks
    are rebuilt if one of them broke a rule."""
    rows = store.scan_all(store.news)
    gone = {r["id"]: r.get("url") for r in rows if r.get("source") not in config.NEWS_SOURCES}
    gone_urls = set(gone.values())
    drop = [r["id"] for r in rows if r["id"] in gone or classify.is_blocked_story(r.get("title"))]
    trimmed = [{**r, "summary": classify.without_race(r["summary"])} for r in rows
               if r["id"] not in drop and r.get("summary") and classify.without_race(r["summary"]) != r["summary"]]
    store.delete_many(store.news, drop)
    store.put_many(store.news, trimmed)
    brief = store.get_meta("brief") or {}
    stale = any(classify.is_blocked_story(b.get("title"), b.get("text")) or classify.RACE_RE.search(b.get("text") or "")
                or b.get("url") in gone_urls
                for b in brief.get("bullets", []))
    if stale:
        store.put_meta("brief", {**brief, "date": "rebuild"})  # ingest_brief builds a fresh one
    report["news_cleanup"] = {"removed": len(drop), "trimmed": len(trimmed), "brief_rebuilt": stale}


STAGES = {"retire_sectors": ingest_retire_sectors, "news_cleanup": ingest_news_cleanup, "news": ingest_news, "retag": retag_news, "funding": ingest_funding, "jobs": ingest_jobs, "brief": ingest_brief,
          "summary": ingest_summary, "ticker": ingest_ticker}


def handler(event, context):
    stages = (event or {}).get("stages") or list(STAGES)
    for key in bedrock.usage:  # warm containers keep module state; report per run
        bedrock.usage[key] = 0
    if not store.acquire_lock("ingest"):
        log.warning("another ingest run holds the lock; exiting")
        return {"ok": False, "reason": "locked"}
    started = time.time()
    report = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        for name in stages:
            try:
                STAGES[name](report)
            except Exception as err:  # noqa: BLE001 - one failing stage must not stop the others
                log.exception("stage %s failed", name)
                report[f"{name}_error"] = str(err)[:300]
    finally:
        report["seconds"] = round(time.time() - started, 1)
        report["bedrock"] = dict(bedrock.usage)
        store.put_meta("last_run", report)
        store.release_lock("ingest")
    log.info("report %s", report)
    return report
