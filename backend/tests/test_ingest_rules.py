from healthsurface.handlers import ingest


def test_exhausted_rule_rows_follow_current_rules():
    fetched = [{"id": "a", "title": "Director of International Product", "company": "X"},
               {"id": "b", "title": "Staff Software Engineer", "company": "X"},
               {"id": "c", "title": "Senior Software Engineer", "company": "X"}]
    existing = {
        "a": {"id": "a", "classifier": "rules", "attempts": 3, "job_type": "Other", "seniority": "Intern"},
        "b": {"id": "b", "classifier": "rules", "attempts": 1, "job_type": "Other", "seniority": "Mid"},  # model still retries
        "c": {"id": "c", "classifier": "rules", "attempts": 3, "job_type": "Software Engineer", "seniority": "Senior"},  # unchanged
    }
    rows = ingest.refresh_rule_rows(fetched, existing, skip=set())
    assert [r["id"] for r in rows] == ["a"]
    assert rows[0]["seniority"] == "Director" and rows[0]["attempts"] == 3 and rows[0]["classifier"] == "rules"


def test_closed_jobs_include_moved_and_long_dead_boards():
    configured = {"ashby#pomelo-care#", "greenhouse#oura#", "lever#flaky#", "remoteok#"}
    existing = {i: {} for i in ["greenhouse#pomelocare#1", "greenhouse#oura#1", "greenhouse#oura#2",
                                "lever#flaky#1", "ashby#pomelo-care#9", "remoteok#5"]}
    live = {"greenhouse#oura#1", "ashby#pomelo-care#9"}
    ok = {"ashby#pomelo-care#", "greenhouse#oura#", "remoteok#"}
    # flaky board failed once: its jobs stay
    closed = ingest.closed_job_ids(existing, live, ok, configured, {"lever#flaky#": 1})
    assert sorted(closed) == ["greenhouse#oura#2", "greenhouse#pomelocare#1", "remoteok#5"]
    # flaky board failed MAX runs in a row: its jobs go too
    closed = ingest.closed_job_ids(existing, live, ok, configured, {"lever#flaky#": ingest.MAX_BOARD_FAILURES})
    assert "lever#flaky#1" in closed


def test_board_failures_count_and_reset():
    configured = {"a#x#", "b#y#"}
    f = ingest.board_failures({"a#x#": 2, "b#y#": 5, "c#gone#": 9}, configured, boards_ok={"b#y#"})
    assert f == {"a#x#": 3, "b#y#": 0}


def test_ticker_items_newest_big_rounds_and_headlines():
    funding = [{"company": "A", "amount_usd": 5e6, "date": "2026-11-01", "source_kind": "SEC Form D", "source_url": "u1"},
               {"company": "A", "amount_usd": 9e6, "date": "2026-11-03", "source_kind": "SEC Form D", "source_url": "u2"},
               {"company": "B", "amount_usd": 1, "date": "2026-11-05", "source_kind": "SEC Form D", "source_url": "u3"}]
    news = [{"label": "Preprint", "title": "p", "url": "n1", "date": "2026-11-05"},
            {"label": "Reported news", "title": "old", "url": "n2", "date": "2026-11-01"},
            {"label": "Regulatory action", "title": "new", "url": "n3", "date": "2026-11-04"}]
    t = ingest.ticker_items(news, funding)
    assert [r["source_url"] for r in t["funding"]] == ["u2"]  # newest A only; $1 placeholder left out
    assert [r["title"] for r in t["news"]] == ["new", "old"]
    assert set(t["funding"][0]) == {"company", "amount_usd", "source_kind", "source_url"}
