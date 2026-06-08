import responses
from src.client import UolClient

BASE = "https://test.demo.uol.cz/api"


class FakeClock:
    def __init__(self):
        self.t = 0.0
    def __call__(self):
        return self.t


@responses.activate
def test_retries_after_429_then_succeeds():
    responses.add(responses.GET, f"{BASE}/v1/ping",
                  json={"error_code": "0010"}, status=429, headers={"Retry-After": "1"})
    responses.add(responses.GET, f"{BASE}/v1/ping", json={"status": "ok"}, status=200)
    slept = []
    client = UolClient(BASE, "e@x.cz", "t", sleep=lambda s: slept.append(s))
    assert client.ping_request() == {"status": "ok"}
    assert slept == [1.0]


@responses.activate
def test_throttles_when_window_exceeded():
    for _ in range(3):
        responses.add(responses.GET, f"{BASE}/v1/ping", json={}, status=200)
    clock = FakeClock()
    slept = []
    client = UolClient(BASE, "e@x.cz", "t",
                       max_per_window=2, window_seconds=10.0,
                       sleep=lambda s: slept.append(s), clock=clock)
    client.ping_request()
    client.ping_request()
    client.ping_request()  # 3rd within window -> must throttle
    assert slept and slept[0] > 0
