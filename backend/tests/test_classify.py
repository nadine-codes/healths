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


@pytest.mark.parametrize("text,blocked", [
    ("Study links social media use to suicide risk in teens", True),
    ("Suicidal ideation screening in primary care", True),
    ("SUICIDES rose in 2025", True),
    ("FDA clears AI ECG device", False),
    ("", False),
])
def test_blocked_story_terms(text, blocked):
    assert classify.is_blocked_story(text) is blocked
    assert classify.is_blocked_story("Neutral headline", text) is blocked  # description is checked too


def summary_items():
    return [
        {"title": "AI reads ECGs to flag heart attacks", "summary": "A peer-reviewed study tested an ECG model.",
         "label": "Peer-reviewed study", "source_name": "PubMed", "url": "https://pubmed.example/1"},
        {"title": "FDA clears a home blood test", "summary": "The FDA cleared a finger-prick test.",
         "label": "Regulatory action", "source_name": "openFDA Device Clearances", "url": "https://fda.example/2"},
        {"title": "Acme Bio was awarded a $2.5 million NIH SBIR grant", "summary": "Project: Faster sepsis tests.",
         "label": "NIH SBIR grant", "source_name": "NIH RePORTER", "url": "https://nih.example/3"},
    ]


def summary_reply(**overrides):
    base = {"paragraphs": [
        [{"item": 0, "text": "A new peer-reviewed study tested an AI model that reads ECGs to flag heart attacks early, "
                             "which could help emergency rooms sort patients faster when every minute counts for the heart."},
         {"item": 3, "text": "Researchers say the ECG model was tested on thousands of tracings from busy hospitals."},
         {"item": 0, "text": "The study team says the model reads each ECG in seconds, so heart attacks could be flagged "
                             "while a patient is still waiting to be seen by a doctor."},
         {"item": 4, "text": "A second peer-reviewed study looked at how wearables track sleep in older adults at home."}],
        [{"item": None, "text": "Now, the regulators."},
         {"item": 1, "text": "The FDA cleared a home blood test that needs only a finger prick, so some routine lab "
                             "checks could move from the clinic to the kitchen table for a lot of people."},
         {"item": 1, "text": "The cleared test sends its blood results to a phone app within minutes of the finger prick."}],
        [{"item": None, "text": "And finally, the money."},
         {"item": 2, "text": "Acme Bio was awarded a $2.5 million NIH grant to build faster sepsis tests, which matters "
                             "because sepsis moves quickly and early tests help hospitals act sooner."},
         {"item": 2, "text": "The sepsis grant comes through the NIH small business program for faster tests."}],
    ]}
    return {**base, **overrides}


def five_items():
    return summary_items() + [
        {"title": "Busy hospitals test an ECG model", "summary": "It read thousands of tracings.", "label": "Reported news",
         "source_name": "The Conversation", "url": "https://tc.example/4"},
        {"title": "Wearables track sleep in older adults", "summary": "A peer-reviewed study at home.",
         "label": "Peer-reviewed study", "source_name": "PubMed", "url": "https://pubmed.example/5"}]


def test_summary_links_come_from_cited_items_not_the_model():
    out = classify.validate_summary(summary_reply(), five_items())
    assert [s["url"] for s in out["sources"]][:3] == ["https://pubmed.example/1", "https://tc.example/4", "https://pubmed.example/5"]
    assert len(out["paragraphs"]) == 3 and out["dropped"] == 0


@pytest.mark.parametrize("text", [
    "The World Health Organization announced a new initiative on resistance.",  # name not in the item
    "Acme Bio was awarded a $9 million grant for sepsis tests.",                 # number not in the item
    "This sepsis test is a breakthrough for hospitals.",                         # banned hype word
    "Read about the sepsis tests at https://nih.example/3 today.",               # links do not read aloud
])
def test_summary_drops_ungrounded_sentences(text):
    assert not classify.sentence_grounded(text, summary_items()[2])


def test_summary_drops_only_the_bad_sentence_in_an_entry():
    reply = summary_reply()
    reply["paragraphs"][0][0]["text"] += " These ECG tools work well in practice."  # judgment the source never makes
    out = classify.validate_summary(reply, five_items())
    assert "every minute counts for the heart." in out["paragraphs"][0] and "work well" not in out["paragraphs"][0]
    assert out["dropped"] == 1


def test_summary_linking_lines_carry_no_facts():
    assert classify.sentence_grounded("Now, the money.", None)
    assert not classify.sentence_grounded("Now, the WHO weighs in with 3 new rules.", None)
    assert not classify.sentence_grounded("And a few big investments closed this week.", None)
    assert not classify.sentence_grounded("Meanwhile, over at the FDA,", None)  # names a source; no period


def test_summary_always_says_a_preprint_is_not_peer_reviewed():
    items = five_items()
    items[4] = {**items[4], "label": "Preprint"}
    reply = summary_reply()
    assert not classify.sentence_grounded("A second peer-reviewed study looked at how wearables track sleep in older adults.",
                                          items[4])
    reply["paragraphs"][0][3]["text"] = "A second study looked at how wearables track sleep in older adults at home."
    out = classify.validate_summary(reply, items)
    assert "older adults at home. That's from a preprint, so it hasn't been peer reviewed yet." in out["paragraphs"][0]
    reply["paragraphs"][0][3]["text"] = "A preprint, not yet peer reviewed, looked at how wearables track sleep in older adults."
    out = classify.validate_summary(reply, items)
    assert "That's from a preprint" not in out["paragraphs"][0]


def test_preprint_notes_never_repeat_back_to_back():
    leads = [classify.preprint_note(n) for n in range(8)]
    assert len(set(leads[:4])) == 4
    assert all(a != b for a, b in zip(leads, leads[1:]))
    assert leads.count(leads[0]) == 1


def test_summary_linking_line_moves_to_the_paragraph_it_introduces():
    reply = summary_reply()
    reply["paragraphs"][0].append(reply["paragraphs"][1].pop(0))  # "Now, the regulators." ends paragraph one
    out = classify.validate_summary(reply, five_items())
    assert not out["paragraphs"][0].endswith("regulators.") and out["paragraphs"][1].startswith("Now, the regulators.")


def test_summary_money_words_must_match_the_item():
    press = {"title": "Administration announces $55 million investment in rural care", "summary": "",
             "label": "Press release", "source_name": "CMS Newsroom"}
    assert classify.sentence_grounded("The administration put $55 million into rural care.", press)
    assert not classify.sentence_grounded("The administration awarded a $55 million grant for rural care.", press)


def test_summary_caps_funding_items():
    items = five_items() + [{"title": f"Co{n} reported raising $1{n} million in an SEC Form D filing", "summary": "",
                             "label": "SEC Form D", "source_name": "SEC Form D filing", "url": f"https://sec.example/{n}"}
                            for n in range(4)]
    reply = summary_reply()
    reply["paragraphs"][2] += [{"item": 5 + n, "text": f"Co{n} reported raising $1{n} million in an SEC filing."} for n in range(4)]
    out = classify.validate_summary(reply, items)
    funding = [s for s in out["sources"] if s["label"].startswith(("SEC", "NIH"))]
    assert len(funding) == 3 and "Co3" not in out["paragraphs"][2] and out["dropped"] == 2


def test_summary_needs_a_treatment_or_policy_item_when_one_exists():
    reply = summary_reply()
    del reply["paragraphs"][1]  # the FDA clearance paragraph
    reply["paragraphs"][0].append({"item": 4, "text": "Wearables now track sleep in older adults at home, a study found."})
    with pytest.raises(ValueError, match="TREATMENT OR POLICY"):
        classify.validate_summary(reply, five_items())


def test_summary_funding_gets_one_sentence_and_no_invented_plans():
    form_d = {"title": "LISATA THERAPEUTICS, INC. reported raising $351.9 million in an SEC Form D filing", "summary": "",
              "label": "SEC Form D", "source_name": "SEC Form D filing", "url": "https://sec.example/l"}
    assert not classify.sentence_grounded("Lisata Therapeutics plans to use the funds for new therapies.", form_d)
    assert not classify.sentence_grounded("Investors see potential in Lisata Therapeutics.", form_d)
    items = five_items() + [form_d]
    reply = summary_reply()
    reply["paragraphs"][2] += [{"item": 5, "text": "Lisata Therapeutics reported raising $351.9 million in an SEC filing."},
                               {"item": 5, "text": "That money for Lisata Therapeutics shows up in the SEC filing."}]
    out = classify.validate_summary(reply, items)
    assert out["paragraphs"][2].count("Lisata") == 1 and out["dropped"] == 1


def test_summary_needs_two_research_items_when_available():
    reply = summary_reply()
    reply["paragraphs"][0] = [s for s in reply["paragraphs"][0] if s["item"] != 4]  # only one study left
    reply["paragraphs"][0].append({"item": 3, "text": "Busy hospitals tested the ECG model on thousands of tracings, "
                                                     "which matters because every minute counts for the heart."})
    with pytest.raises(ValueError, match="RESEARCH"):
        classify.validate_summary(reply, five_items())


def test_summary_money_line_only_opens_the_funding_paragraph():
    reply = summary_reply()
    reply["paragraphs"][1][0]["text"] = "Now, the money."  # wrongly opens the FDA paragraph
    out = classify.validate_summary(reply, five_items())
    assert not out["paragraphs"][1].startswith("Now, the money.") and out["dropped"] == 1


def test_summary_rejects_too_few_items():
    reply = {"paragraphs": [summary_reply()["paragraphs"][1], summary_reply()["paragraphs"][2]]}
    with pytest.raises(ValueError):
        classify.validate_summary(reply, summary_items())


def stories_reply():
    """summary_reply() for the stories only (no NIH item), numbered as the model sees them."""
    remap = {0: 0, 1: 1, 3: 2, 4: 3, None: None}
    return {"paragraphs": [[{**sent, "item": remap[sent["item"]]} for sent in para]
                           for para in summary_reply()["paragraphs"][:2]]}


def test_summary_retries_once_with_the_reason_and_code_writes_the_money():
    prompts = []
    items = five_items()
    items[2] = {**items[2], "company": "ACME BIO, INC.", "amount": "$2.5 million"}
    items.append({"title": "LISATA THERAPEUTICS, INC. reported raising $351.9 million in an SEC Form D filing",
                  "summary": "", "label": "SEC Form D", "source_name": "SEC Form D filing", "url": "https://sec.example/l",
                  "company": "LISATA THERAPEUTICS, INC.", "amount": "$351.9 million"})

    def invoke(system, user):
        prompts.append(user)
        return json.dumps({"paragraphs": []} if len(prompts) == 1 else stories_reply())

    out = classify.todays_summary(items, invoke)
    assert len(prompts) == 2 and "rejected" in prompts[1] and "Acme" not in prompts[0]
    assert out["paragraphs"][-1] == ("Now, the money. In an SEC filing this past week, Lisata Therapeutics reported "
                                     "raising $351.9 million. And on the research side, Acme Bio won a $2.5 million NIH SBIR grant.")
    assert [s["url"] for s in out["sources"]][-2:] == ["https://nih.example/3", "https://sec.example/l"]


def test_sentence_after_a_comma_link_continues_in_lowercase():
    assert classify.join_sentences(["In treatment news,", "A trial in Brazil tested calls.", "FDA cleared it."]) == \
        "In treatment news, a trial in Brazil tested calls. FDA cleared it."
    assert classify.join_sentences(["Meanwhile,", "FDA cleared a test."]) == "Meanwhile, FDA cleared a test."


def test_money_paragraph_joins_several_raises():
    funding = [{"label": "SEC Form D", "company": c, "amount": a} for c, a in
               [("LISATA THERAPEUTICS, INC.", "$351.9 million"), ("Precision Neuroscience Corp", "$250 million"),
                ("Alpfa Medical, Inc.", "$80.3 million")]]
    assert classify.funding_paragraph(funding) == (
        "Now, the money. In SEC filings this past week, Lisata Therapeutics reported raising $351.9 million, "
        "Precision Neuroscience $250 million, and Alpfa Medical $80.3 million.")


def test_spoken_summary_has_intro_and_disclaimer():
    text = classify.spoken_summary({"paragraphs": ["One.", "Two."]}, "Friday, October 2")
    assert text.startswith("Here's your HealthSurface summary for Friday, October 2. One. Two.")
    assert text.endswith("not medical advice.")


def test_sector_guide_covers_every_sector():
    assert list(classify.SECTOR_GUIDE) == tx.SECTORS


@pytest.mark.parametrize("title,job_type", [
    ("Fulfillment Pharmacist - Boynton Beach, FL", "Clinical Product Specialist"),  # "fuLLMent" is not an LLM job
    ("Senior Battery Cell Engineer", "Other"),
    ("Technical Recruiting Lead", "People and Recruiting"),
    ("Senior Analyst, SIU Investigator", "Legal and Compliance"),
    ("Engineering Program Manager, New Product Development", "Project or Program Manager"),
])
def test_rule_job_classifier_edge_cases(title, job_type):
    assert classify.rule_classify_job({"title": title})["job_type"] == job_type


def test_job_prompt_says_seniority_does_not_decide_the_type():
    prompt = classify.job_prompt({"title": "VP of Engineering", "company": "x"})
    assert "not by seniority" in prompt and "Clinical Product Specialist: licensed clinicians" in prompt


def test_validate_job_unwraps_single_item_lists():
    out = classify.validate_job({"job_type": ["Product Marketing", "Sales"], "employment_type": ["Full-time"],
                                 "seniority": ["Director"]})
    assert out["job_type"] == "Product Marketing" and out["employment_type"] == "Full-time"
