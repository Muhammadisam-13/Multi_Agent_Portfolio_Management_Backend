import json
import socket
from datetime import date
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from api import __version__
from api.config import Settings
from api.main import create_app
from mizan.data.snapshot import write_snapshot
from mizan.retrieval.bundle import load_items

FIXTURES = Path(__file__).parent / "fixtures" / "evidence_items.jsonl"
AS_OF = "2025-06-30"


def make_settings(tmp_path, **overrides):
    snap = write_snapshot(load_items(FIXTURES), tmp_path / "snaps" / "fixture-v1")
    names = tmp_path / "ticker_names.json"
    names.write_text(json.dumps({"AAA": ["Alpha Oil & Gas Limited"], "BBB": ["Beta Bank Limited"],
                                 "CCC": ["Gamma Cement Limited", "Old Gamma Ltd"], "DDD": ["Delta Foods Limited"]}), encoding="utf-8")
    base = dict(snapshot=str(snap), snapshots_dir=tmp_path / "snaps", cache_dir=tmp_path / "cache", ticker_names_path=names)
    return Settings(**{**base, **overrides})


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(make_settings(tmp_path)))


# --- 1. /health -------------------------------------------------------------------------

def test_health_reports_status_version_flag_and_snapshot(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["app_version"] == __version__ and body["live_fetching_enabled"] is False
    assert body["snapshot"]["name"] == "fixture-v1" and body["snapshot"]["verified"] is True
    assert body["snapshot"]["item_count"] == 13 and body["snapshot"]["tickers"] == ["AAA", "BBB", "CCC"]
    assert body["snapshot"]["date_range"] == ["2025-03-31", "2025-07-20"]
    assert body["snapshot_error"] is None and body["tickers_error"] is None


def test_health_still_answers_when_the_snapshot_is_missing(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, snapshot=str(tmp_path / "nope"))))
    body = c.get("/health").json()
    assert body["status"] == "degraded" and body["snapshot"] is None and "missing" in body["snapshot_error"]


def test_health_flags_a_tampered_snapshot(tmp_path):
    settings = make_settings(tmp_path)
    path = Path(settings.snapshot) / "items.jsonl"
    path.write_bytes(path.read_bytes().replace(b"AAA closed", b"AAA CLOSED"))
    body = TestClient(create_app(settings)).get("/health").json()
    assert body["status"] == "degraded" and "does not match manifest" in body["snapshot_error"]


def test_health_reports_the_live_fetch_flag_from_config(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, live_fetching_enabled=True)))
    assert c.get("/health").json()["live_fetching_enabled"] is True


# --- 2. /tickers ------------------------------------------------------------------------

def test_tickers_lists_configured_tickers_with_names_and_data_flags(client):
    r = client.get("/tickers")
    assert r.status_code == 200
    by_ticker = {t["ticker"]: t for t in r.json()}
    assert list(by_ticker) == ["AAA", "BBB", "CCC", "DDD"]                       # file order
    assert by_ticker["AAA"]["company_name"] == "Alpha Oil & Gas Limited" and by_ticker["AAA"]["has_data"] is True
    assert by_ticker["CCC"]["names"] == ["Gamma Cement Limited", "Old Gamma Ltd"]
    assert by_ticker["DDD"]["items_in_snapshot"] == 0 and by_ticker["DDD"]["has_data"] is False


def test_tickers_without_a_usable_snapshot_still_lists_names(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, snapshot=str(tmp_path / "nope"))))
    first = c.get("/tickers").json()[0]
    assert first["ticker"] == "AAA" and first["items_in_snapshot"] is None and first["has_data"] is False


def test_unreadable_ticker_file_gives_503_with_the_reason(tmp_path):
    settings = make_settings(tmp_path)
    settings.ticker_names_path.write_text("{not json", encoding="utf-8")
    c = TestClient(create_app(settings))
    r = c.get("/tickers")
    assert r.status_code == 503 and "ticker list not usable" in r.json()["detail"]
    assert c.get("/health").json()["status"] == "degraded"


# --- 3. /tickers/{ticker}/bundle -----------------------------------------------------------

def test_bundle_has_the_contract_fields(client):
    r = client.get(f"/tickers/AAA/bundle?as_of={AS_OF}")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"ticker", "as_of", "items"} and body["ticker"] == "AAA" and body["as_of"] == AS_OF
    assert set(body["items"][0]) == {"id", "ticker", "source", "type", "date", "text"}


def test_no_look_ahead_through_the_api(client):
    ids = {i["id"] for i in client.get(f"/tickers/AAA/bundle?as_of={AS_OF}").json()["items"]}
    assert "AAA-ANN-2025-07-15" not in ids and "MACRO-POLICY-2025-07-20" not in ids       # both dated after as_of
    assert "AAA-ANN-2025-06-30" in ids                                                      # dated exactly as_of is included
    items = client.get(f"/tickers/AAA/bundle?as_of={AS_OF}").json()["items"]
    assert all(i["date"] <= AS_OF for i in items)


def test_moving_the_date_earlier_removes_newer_items(client):
    later = {i["id"] for i in client.get("/tickers/AAA/bundle?as_of=2025-06-30").json()["items"]}
    earlier = {i["id"] for i in client.get("/tickers/AAA/bundle?as_of=2025-05-01").json()["items"]}
    assert earlier < later and "AAA-PRICE-2025-06-27" in later - earlier


def test_ticker_isolation_through_the_api(client):
    items = client.get(f"/tickers/AAA/bundle?as_of={AS_OF}").json()["items"]
    assert {i["ticker"] for i in items} == {"AAA", "MACRO"}
    assert not any(i["id"].startswith(("BBB", "CCC")) for i in items)


def test_ticker_is_case_insensitive_and_echoed_in_upper_case(client):
    assert client.get(f"/tickers/bbb/bundle?as_of={AS_OF}").json()["ticker"] == "BBB"


def test_default_as_of_is_the_newest_date_in_the_snapshot(client):
    body = client.get("/tickers/AAA/bundle").json()
    assert body["as_of"] == "2025-07-20" and "AAA-ANN-2025-07-15" in {i["id"] for i in body["items"]}


def test_known_ticker_without_data_gives_an_empty_bundle_not_an_error(client):
    r = client.get(f"/tickers/DDD/bundle?as_of={AS_OF}")
    body = r.json()
    assert r.status_code == 200 and body["ticker"] == "DDD" and all(i["ticker"] == "MACRO" for i in body["items"])


def test_date_before_everything_gives_an_empty_bundle(client):
    assert client.get("/tickers/AAA/bundle?as_of=2020-01-01").json()["items"] == []


def test_unknown_ticker_is_404_with_a_message(client):
    r = client.get(f"/tickers/ZZZZ/bundle?as_of={AS_OF}")
    assert r.status_code == 404
    assert "Unknown ticker 'ZZZZ'" in r.json()["detail"] and "AAA" in r.json()["detail"]


@pytest.mark.parametrize("bad", ["banana", "2025-13-45", "30/06/2025", ""])
def test_bad_date_is_422_with_a_readable_message(client, bad):
    r = client.get(f"/tickers/AAA/bundle?as_of={bad}")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str) and "as_of" in detail and "YYYY-MM-DD" in detail


def test_bundle_without_a_usable_snapshot_is_503_with_the_reason(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, snapshot=str(tmp_path / "nope"))))
    r = c.get(f"/tickers/AAA/bundle?as_of={AS_OF}")
    assert r.status_code == 503 and "snapshot is not usable" in r.json()["detail"]


# --- the API never goes to the network -------------------------------------------------------

LOCAL = {"127.0.0.1", "::1", "localhost"}


def test_no_endpoint_talks_to_a_non_local_host_even_with_live_fetching_enabled(tmp_path, monkeypatch):
    """The test client itself uses loopback sockets; anything else (PSX, any website) must fail the test."""
    attempts = []
    real_connect, real_getaddrinfo = socket.socket.connect, socket.getaddrinfo

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in LOCAL:
            attempts.append(host)
            raise AssertionError(f"an API request tried to connect to {host}")
        return real_connect(self, address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in LOCAL and host is not None:
            attempts.append(host)
            raise AssertionError(f"an API request tried to resolve {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    c = TestClient(create_app(make_settings(tmp_path, live_fetching_enabled=True)))
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    for path in ("/health", "/tickers", f"/tickers/AAA/bundle?as_of={AS_OF}", "/tickers/AAA/bundle", "/tickers/ZZZ/bundle"):
        assert c.get(path).status_code in (200, 404)
    assert attempts == []


def test_openapi_contract_lists_the_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/tickers", "/tickers/{ticker}/bundle"} <= set(paths)
