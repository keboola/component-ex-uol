import base64
import responses
from src.client import UolClient

BASE = "https://test.demo.uol.cz/api"


@responses.activate
def test_ping_true_on_200():
    responses.add(responses.GET, f"{BASE}/v1/ping", json={"status": "ok"}, status=200)
    client = UolClient(BASE, "demo@example.com", "tok")
    assert client.ping() is True


@responses.activate
def test_ping_false_on_401():
    responses.add(responses.GET, f"{BASE}/v1/ping", json={"error_code": "0002"}, status=401)
    client = UolClient(BASE, "demo@example.com", "tok")
    assert client.ping() is False


@responses.activate
def test_sends_basic_auth_and_accept_header():
    responses.add(responses.GET, f"{BASE}/v1/ping", json={}, status=200)
    UolClient(BASE, "demo@example.com", "tok").ping()
    sent = responses.calls[0].request
    expected = "Basic " + base64.b64encode(b"demo@example.com:tok").decode()
    assert sent.headers["Authorization"] == expected
    assert sent.headers["Accept"] == "application/json"
