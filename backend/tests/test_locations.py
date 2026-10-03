import pytest

from healthsurface.locations import countries_for


@pytest.mark.parametrize("location,expected", [
    ("Boston, MA", ["United States"]),
    ("New York City, New York", ["United States"]),
    ("Ohio", ["United States"]),
    ("Remote - USA", ["United States"]),
    ("US- Remote", ["United States"]),
    ("SF Office", ["United States"]),
    ("Austin, TX (Remote)", ["United States"]),
    ("Remote - CA", ["United States"]),
    ("New Mexico", ["United States"]),
    ("Mexico City, Mexico - Remote", ["Mexico"]),
    ("Pune, Maharashtra, India", ["India"]),
    ("Hybrid - London, England", ["United Kingdom"]),
    ("US or Canada - Remote", ["United States", "Canada"]),
    ("Remote - Europe; Remote - US", ["United States", "Europe"]),
    ("Remote", []),
    ("", []),
    (None, []),
])
def test_countries_for(location, expected):
    assert countries_for(location) == expected
