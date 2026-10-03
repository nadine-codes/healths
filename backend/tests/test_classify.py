import json

import pytest

from healthsurface import classify, taxonomy as tx


def story_reply(**overrides):
    base = {
        "sector": "Health AI",
        "focus_areas": ["Cardiovascular"],
        "summary": "An AI model reads ECGs to flag heart attacks. The FDA cleared it this week.",
        "confidence": 0.9,
        "is_funding_announcement": False,
        "funding": None,
    }
    return {**base, **overrides}


def test_taxonomy_sizes_match_brief():
    assert len(tx.SECTORS) == 10
    assert len(tx.FOCUS_AREAS) == 20
    assert list(tx.EVIDENCE_LABELS) == ["Press release", "Preprint", "Peer-reviewed study", "Regulatory action", "Reported news"]
    assert len(tx.JOB_TYPES) == 37  # the 36 listed types plus Other


def test_validate_story_accepts_good_reply():
    out = classify.validate_story(story_reply())
    assert out["sector"] == "Health AI" and out["focus_areas"] == ["Cardiovascular"]


def test_validate_story_rejects_unknown_sector():
    with pytest.raises(ValueError):
        classify.validate_story(story_reply(sector="Crypto"))


def test_validate_story_drops_invented_focus_areas():
    out = classify.validate_story(story_reply(focus_areas=["Cardiovascular", "Value-based care"]))
    assert out["focus_areas"] == ["Cardiovascular"]


@pytest.mark.parametrize("summary", ["This proven therapy works.", "A breakthrough cure.", ""])
def test_summary_rejects_hype_and_empty(summary):
    with pytest.raises(ValueError):
        classify.validate_story(story_reply(summary=summary))


def test_summary_strips_em_dashes_and_limits_to_two_sentences():
    text = classify.clean_summary("One — two. Three. Four.")
    assert "—" not in text and text.count(".") == 2


def test_parse_json_tolerates_code_fences():
    assert classify.parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_model_failure_falls_back_to_rules():
    result, method = classify.classify_story({"title": "FDA clears AI ECG device", "label": "Regulatory action"},
                                             invoke=lambda s, u: "not json")
    assert method == "rules" and result["sector"] in tx.SECTORS


def test_classify_story_uses_model_reply():
    reply = json.dumps(story_reply())
    result, method = classify.classify_story({"title": "x", "label": "Preprint"}, invoke=lambda s, u: reply)
    assert method == "model" and result["sector"] == "Health AI"


class TestVerifyFunding:
    def funding(self, **f):
        base = {"company": "Acme", "amount_usd": 10_000_000, "round_stage": "Series A", "date": None, "investors": ["Canvas Ventures"]}
        return {"is_funding_announcement": True, "funding": {**base, **f}}

    def test_partnership_is_not_funding(self):
        out = classify.verify_funding({"title": "Sanofi Puts Up $1B to Expand Regeneron Alliance"}, self.funding())
        assert out["funding"] is None and not out["is_funding_announcement"]

    def test_keeps_only_stated_facts(self):
        item = {"title": "Acme Secures $10M", "description": "The round was led by Canvas Ventures."}
        f = classify.verify_funding(item, self.funding())["funding"]
        assert f["amount_usd"] == 10_000_000
        assert f["round_stage"] is None  # "Series A" is not in the text
        assert f["investors"] == ["Canvas Ventures"]

    def test_wrong_amount_is_cleared(self):
        item = {"title": "Acme raises $33M Series A"}
        f = classify.verify_funding(item, self.funding(amount_usd=1e9))["funding"]
        assert f["amount_usd"] is None and f["round_stage"] == "Series A"


@pytest.mark.parametrize("title,job_type,emp", [
    ("Senior Software Engineer, Backend", "Software Engineer", "Full-time"),
    ("Product Designer (Contract)", "UX/UI Product Designer", "Contract"),
    ("Registered Nurse, Per Diem", "Clinical Product Specialist", "Part-time"),
    ("Summer Data Science Intern", "Data and Analytics", "Internship"),
    ("Customer Success Manager", "Customer Success Manager", "Full-time"),
])
def test_rule_job_classifier(title, job_type, emp):
    out = classify.rule_classify_job({"title": title})
    assert out["job_type"] == job_type and out["employment_type"] == emp
    assert out["function_group"] == tx.function_group_for(job_type)


def test_validate_job_maps_unknown_type_to_other():
    out = classify.validate_job({"job_type": "Astronaut", "employment_type": "Full-time", "seniority": "Senior"})
    assert out["job_type"] == "Other" and out["function_group"] == "Other"


def test_brief_keeps_each_storys_own_label():
    stories = [{"title": f"t{i}", "summary": f"Summary {i}. More.", "label": lbl, "url": f"https://x/{i}"}
               for i, lbl in enumerate(["Preprint", "Reported news"] * 4)]
    bullets = classify.todays_brief(stories, lambda s, u: '{"picks": [0, 1, 2, 3, 4, 99, 0]}')
    assert [b["label"] for b in bullets] == ["Preprint", "Reported news", "Preprint", "Reported news", "Preprint"]
    assert bullets[0] == {"text": "Summary 0.", "label": "Preprint", "url": "https://x/0", "title": "t0"}
