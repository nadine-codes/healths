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
