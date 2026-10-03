from healthsurface.sources import funding, jobs, news


def test_item_id_dedupes_url_variants():
    assert news.item_id("https://Example.com/a/") == news.item_id("https://example.com/a")


def test_make_item_label_comes_from_config_not_ai():
    item = news.make_item("medrxiv", "https://www.medrxiv.org/content/1", "<b>Title</b>", "2026-10-01")
    assert item["label"] == "Preprint" and item["title"] == "Title"


def test_fda_links_are_upgraded_to_https():
    item = news.make_item("fda_press", "http://www.fda.gov/news-events/x", "t", "2026-10-01")
    assert item["url"].startswith("https://")


def test_paywall_markers():
    assert news.JSONLD_FREE_FALSE.search('{"isAccessibleForFree": "False"}')
    assert not news.JSONLD_FREE_FALSE.search('{"isAccessibleForFree": true}')


FORM_D = b"""<?xml version="1.0"?><edgarSubmission><primaryIssuer><entityName>Acme Bio, Inc.</entityName></primaryIssuer>
<offeringData><industryGroup><industryGroupType>Biotechnology</industryGroupType></industryGroup>
<typeOfFiling><newOrAmendment><isAmendment>false</isAmendment></newOrAmendment>
<dateOfFirstSale><value>2026-09-02</value></dateOfFirstSale></typeOfFiling>
<offeringSalesAmounts><totalOfferingAmount>10000000</totalOfferingAmount><totalAmountSold>4000000</totalAmountSold></offeringSalesAmounts>
</offeringData></edgarSubmission>"""


def test_parse_form_d_and_record():
    form = funding.parse_form_d(FORM_D)
    assert form["company"] == "Acme Bio, Inc." and form["amount_sold"] == 4_000_000
    rec = funding.to_record({"adsh": "0001-26-000001", "cik": "0000123", "file_date": "2026-10-01"}, form)
    assert rec["sector"] == "Life Sciences and Biotech"
    assert rec["round_stage"] is None and rec["investors"] == []  # Form D does not state these
    assert rec["source_url"].endswith("/123/000126000001/0001-26-000001-index.htm")


def test_amended_form_d_is_skipped():
    form = funding.parse_form_d(FORM_D.replace(b"<isAmendment>false", b"<isAmendment>true"))
    assert funding.to_record({"adsh": "a", "cik": "1", "file_date": "x"}, form) is None


def test_slug_tokens_for_board_lookup():
    assert jobs._slug_tokens("Tiny Health, Inc.") == ["tinyhealth", "tiny-health"]
    assert jobs._slug_tokens("Ro") == []  # too short to verify safely
