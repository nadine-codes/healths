from healthsurface.sources import funding, jobs, news


def test_item_id_dedupes_url_variants():
    assert news.item_id("https://Example.com/a/") == news.item_id("https://example.com/a")


def test_make_item_label_comes_from_config_not_ai():
    item = news.make_item("medrxiv", "https://www.medrxiv.org/content/1", "<b>Title</b>", "2026-10-01")
    assert item["label"] == "Preprint" and item["title"] == "Title"


def test_fda_links_are_upgraded_to_https():
    item = news.make_item("openfda_drugs", "http://www.fda.gov/news-events/x", "t", "2026-10-01")
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


def test_disabled_sources_are_not_fetched():
    from healthsurface import config
    assert "medcity" not in news.FETCHERS
    assert all(config.NEWS_SOURCES[k].get("enabled", True) for k in news.FETCHERS)


def test_nih_grant_record():
    from healthsurface.sources import grants
    rec = grants.to_record({"appl_id": 11525063, "organization": {"org_name": "KINEA BIO, INC."}, "award_amount": 1021458,
                            "award_notice_date": "2026-09-23T00:00:00", "activity_code": "R42",
                            "agency_ic_admin": {"abbreviation": "NIAMS"}, "project_title": "Gene delivery for neuromuscular disease"})
    assert rec["round_stage"] == "Grant" and rec["source_kind"] == "NIH STTR grant"
    assert rec["company"] == "Kinea Bio, Inc." and rec["date"] == "2026-09-23"
    assert rec["source_url"] == "https://reporter.nih.gov/project-details/11525063"


def test_cms_feed_link_unpacking(monkeypatch):
    from healthsurface.sources import http as h
    feed = (b'<rss><channel><item><title></title><link>https://www.cms.gov/%3Ca%20href%3D%22/newsroom/press-releases/x%22'
            b'%20hreflang%3D%22en%22%3ECMS%20does%20a%20thing%3C/a%3E</link><pubDate>Fri, 10/02/2026 - 09:38</pubDate>'
            b'<description>d</description></item></channel></rss>')
    monkeypatch.setattr(h, "get", lambda url, **kw: (200, feed))
    [item] = news.fetch_cms_newsroom()
    assert item["url"] == "https://www.cms.gov/newsroom/press-releases/x"
    assert item["title"] == "CMS does a thing" and item["date"] == "2026-10-02" and item["label"] == "Press release"


def test_kff_health_news_is_never_a_source():
    # Owner decision (2026-10-02): KFF Health News is not used now or in the future.
    from healthsurface import config
    blob = repr(config.NEWS_SOURCES).lower() + repr(list(news.FETCHERS)).lower()
    assert "kff" not in blob


def test_announced_rounds_are_valid():
    from healthsurface import taxonomy
    t = taxonomy.as_dict()
    rows = funding.announced_rounds()
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        assert r["source_kind"] == "Company announcement"
        assert r["source_url"].startswith("https://") and r["company"] and r["date"][:2] == "20"
        assert isinstance(r["amount_usd"], int) and r["amount_usd"] > 0
        assert r["sector"] in t["sectors"] and r["round_stage"] in t["round_stages"]


# ---------- 8-K offerings (NAD-62) ----------
from healthsurface.sources import grants, offerings

PRICING = """5
d1dex991.htm
EX-99.1
Exhibit 99.1
Acme Bio Announces Pricing of $125 Million
Public Offering
BOSTON, November 12, 2026 -- Acme Bio, Inc. today announced the pricing of its underwritten public offering.
The gross proceeds to Acme Bio from the offering are expected to be approximately $125 million."""

FILING = {"adsh": "0001-26-000002", "doc": "d1dex991.htm", "cik": "0000123", "file_date": "2026-11-12",
          "display_name": "ACME BIO INC  (ACME, ACMEW)  (CIK 0000000123)", "sics": ["2836"], "location": "Boston, MA"}


def test_offering_headline_wraps_and_amount_comes_from_headline():
    rec = offerings.to_record(FILING, PRICING)
    assert rec["headline"] == "Acme Bio Announces Pricing of $125 Million Public Offering"
    assert rec["amount_usd"] == 125e6 and rec["round_stage"] == "Public offering"
    assert rec["company"] == "Acme Bio Inc" and rec["ticker"] == "ACME" and rec["sector"] == "Life Sciences and Biotech"
    assert rec["id"] == "sec8k#0001-26-000002" and rec["source_kind"] == offerings.KIND


def test_offering_amount_falls_back_to_gross_proceeds():
    text = "Exhibit 99.1\nVir Announces Pricing of Public Offering\nSF, November 12, 2026 -- The gross proceeds are expected to be $150 million."
    assert offerings.to_record(FILING, text)["amount_usd"] == 150e6


def test_bullets_and_earnings_are_not_offerings():
    bullet = "Exhibit 99.1\nAcme Reports Pipeline Progress\nCompany completed a private placement with gross proceeds of $40 million"
    earnings = "Exhibit 99.1\nAcme Announces Third Quarter Results and Closing of Offering"
    assert offerings.to_record(FILING, bullet) is None
    assert offerings.to_record(FILING, earnings) is None


def test_non_health_filers_are_skipped_and_devices_are_med_tech():
    assert offerings.to_record({**FILING, "sics": ["6770"]}, PRICING) is None
    assert offerings.to_record({**FILING, "sics": ["3841"]}, PRICING)["sector"] == "Med Tech"


def test_offering_stages():
    assert offerings.stage_for("Acme Announces Pricing of Initial Public Offering") == "IPO"
    assert offerings.stage_for("Acme Announces $30 Million Private Placement") == "Private placement"
    assert offerings.stage_for("Pricing of Registered Direct Offering and Concurrent Private Placement") == "Public offering"
    assert offerings.stage_for("Acme Closes Merger and $490 Million Financing") is None


def test_pricing_and_closing_are_one_raise():
    a = {"company": "Acme", "round_stage": "Public offering", "date": "2026-11-12"}
    assert offerings.same_raise(a, {**a, "date": "2026-11-14"})
    assert not offerings.same_raise(a, {**a, "date": "2026-12-14"})
    assert not offerings.same_raise(a, {**a, "round_stage": "Private placement"})


def test_price_per_share_is_not_an_amount():
    assert offerings._amount(offerings.HEADLINE_AMOUNT.search("at $10.00 per share")) is None


def test_investment_vehicles_are_not_companies():
    for name in ["FRONTIER MEDTECH FUND I, L.P.", "Life Impact Partners 14 LLC", "Apex ER II, LLC",
                 "Endoscopy Center at St. Mary, LP", "HealthVest Fund V LLC"]:
        assert funding.is_investment_vehicle(name), name
    for name in ["Seraxis Holdings, Inc.", "Nanopath Inc", "Island Bio, LLC"]:
        assert not funding.is_investment_vehicle(name), name
    assert funding.is_investment_vehicle("Acme Bio", "Limited Partnership")


def test_grant_sector_from_title():
    assert grants.grant_sector("A Non-invasive Wearable Device for Monitoring Venous Clots") == "Med Tech"
    assert grants.grant_sector("Artificial Intelligence Enhanced Detection of Bladder Cancer") == "Health AI"
    assert grants.grant_sector("Scalable Non-viral Gene Delivery for Neuromuscular Diseases") == "Life Sciences and Biotech"
    assert grants.grant_sector("Medicare policy and regulatory guidance study") != "Policy and Regulation"
