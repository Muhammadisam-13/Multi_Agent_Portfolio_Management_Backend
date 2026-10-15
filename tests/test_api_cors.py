import pytest
from starlette.testclient import TestClient

from api.main import create_app
from mizan.llm.fake import FakeLLM
from tests.test_api import AS_OF, make_settings


def preflight(client, origin, method="POST", path="/ask"):
    return client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": method,
                                         "Access-Control-Request-Headers": "content-type"})


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(make_settings(tmp_path), llm=FakeLLM()))


@pytest.mark.parametrize("origin", ["http://localhost:5555", "http://127.0.0.1:61234", "http://localhost"])
def test_a_preflight_from_localhost_on_any_port_is_allowed(client, origin):
    r = preflight(client, origin)
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
    assert "POST" in r.headers["access-control-allow-methods"] and "content-type" in r.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("origin", ["https://example.com", "http://localhost.example.com", "https://localhost:5555",
                                   "http://192.168.100.20:8080"])
def test_a_preflight_from_another_origin_is_not_allowed(client, origin):
    r = preflight(client, origin)
    assert r.status_code == 400 and "access-control-allow-origin" not in r.headers


def test_only_get_and_post_are_allowed(client):
    assert preflight(client, "http://localhost:5555", method="DELETE").status_code == 400


def test_a_simple_get_from_localhost_carries_the_allow_origin_header(client):
    r = client.get(f"/tickers/AAA/bundle?as_of={AS_OF}", headers={"Origin": "http://localhost:5555"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5555"
    other = client.get("/health", headers={"Origin": "https://example.com"})
    assert other.status_code == 200 and "access-control-allow-origin" not in other.headers      # the browser blocks it


def test_extra_origins_come_from_the_settings(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, cors_origins=("http://192.168.100.20:8080",)), llm=FakeLLM()))
    assert preflight(c, "http://192.168.100.20:8080").headers["access-control-allow-origin"] == "http://192.168.100.20:8080"
    assert preflight(c, "http://localhost:5555").status_code == 200                   # localhost still allowed
    assert preflight(c, "https://example.com").status_code == 400
