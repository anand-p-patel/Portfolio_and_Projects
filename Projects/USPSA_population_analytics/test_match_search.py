"""Unit tests for match_search pure helpers (no browser/network)."""
from datetime import date

import match_search as ms


def test_monthly_windows_spans_partial_months():
    ws = ms.monthly_windows("2025-01-15", "2025-03-10")
    assert ws == [
        (date(2025, 1, 15), date(2025, 1, 31)),
        (date(2025, 2, 1), date(2025, 2, 28)),
        (date(2025, 3, 1), date(2025, 3, 10)),
    ]


def test_monthly_windows_single_day():
    assert ms.monthly_windows("2025-07-04", "2025-07-04") == [
        (date(2025, 7, 4), date(2025, 7, 4))]


def test_monthly_windows_full_year_has_12():
    assert len(ms.monthly_windows("2025-01-01", "2025-12-31")) == 12


def test_monthly_windows_reversed_is_empty():
    assert ms.monthly_windows("2025-03-01", "2025-01-01") == []


def test_monthly_windows_leap_february():
    ws = ms.monthly_windows("2024-02-01", "2024-02-29")
    assert ws == [(date(2024, 2, 1), date(2024, 2, 29))]


def test_updated_bounds_are_padded_and_ordered():
    lo, hi = ms.updated_bounds("2025-06-01", "2025-06-30")
    assert lo < hi
    # lo is >=30 days before the window start; hi is >=7 days after the end
    from datetime import datetime, timezone, timedelta
    start = datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert lo <= int((start - timedelta(days=30)).timestamp())


def test_in_range_inclusive_bounds():
    assert ms.in_range("2025-01-15", "2025-01-15", "2025-03-10")
    assert ms.in_range("2025-03-10", "2025-01-15", "2025-03-10")
    assert not ms.in_range("2025-01-14", "2025-01-15", "2025-03-10")
    assert not ms.in_range("2025-03-11", "2025-01-15", "2025-03-10")


def test_in_range_bad_input():
    assert not ms.in_range("", "2025-01-01", "2025-12-31")
    assert not ms.in_range(None, "2025-01-01", "2025-12-31")
    assert not ms.in_range("not-a-date", "2025-01-01", "2025-12-31")


def test_results_url():
    assert ms.results_url("abc-123") == \
        "https://practiscore.com/results/new/abc-123"


def test_build_query_params_uspsa_and_state():
    from urllib.parse import parse_qs
    p = parse_qs(ms.build_query_params("2025-06-01", "2025-06-30", 0, "tx"))
    assert '"match_subtype:uspsa"' in p["facetFilters"][0]
    assert '"front_club_state:TX"' in p["facetFilters"][0]
    assert p["page"] == ["0"]
    assert "timestamp_utc_updated>=" in p["numericFilters"][0]


def test_build_query_params_no_state_omits_state_facet():
    p = ms.build_query_params("2025-06-01", "2025-06-30", 1)
    assert "front_club_state" not in p


def test_hits_to_matches_filters_out_of_range_and_missing_id():
    hits = [
        {"match_id": "a", "match_date": "2025-06-10", "match_name": "In",
         "front_club_state": "TX"},
        {"match_id": "b", "match_date": "2025-05-01", "match_name": "Before"},
        {"match_id": "", "match_date": "2025-06-10", "match_name": "No id"},
        {"match_date": "2025-06-10", "match_name": "No id key"},
    ]
    out = ms.hits_to_matches(hits, "2025-06-01", "2025-06-30")
    assert [m["match_id"] for m in out] == ["a"]
    assert out[0]["state"] == "TX"
    assert out[0]["name"] == "In"


def test_dedupe_and_sort_newest_first_and_cap():
    matches = [
        {"match_id": "a", "match_date": "2025-01-01"},
        {"match_id": "b", "match_date": "2025-03-01"},
        {"match_id": "a", "match_date": "2025-01-01"},  # dup
        {"match_id": "c", "match_date": "2025-02-01"},
    ]
    out = ms.dedupe_and_sort(matches)
    assert [m["match_id"] for m in out] == ["b", "c", "a"]
    assert [m["match_id"] for m in ms.dedupe_and_sort(matches, cap=2)] == ["b", "c"]


def test_key_from_request_url():
    url = ("https://x-dsn.algolia.net/1/indexes/*/queries?"
           "x-algolia-application-id=APP123&x-algolia-api-key=KEY456&z=1")
    assert ms.key_from_request_url(url) == ("APP123", "KEY456")
    assert ms.key_from_request_url("") == (None, None)
