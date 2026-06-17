"""Tests for transport-error, 4xx, and non-JSON error handling in UolClient."""

import pytest
import requests
import responses
from keboola.component.exceptions import UserException

from client import UolClient

BASE = "https://test.demo.uol.cz/api"


# ---------------------------------------------------------------------------
# TODO 3 – transport errors
# ---------------------------------------------------------------------------


@responses.activate
def test_connection_error_raises_userexception():
    """After retries are exhausted a ConnectionError must surface as UserException."""
    responses.add(
        responses.GET,
        f"{BASE}/v1/ping",
        body=requests.exceptions.ConnectionError("boom"),
    )
    client = UolClient(BASE, "e@x.cz", "t", max_retries=1, sleep=lambda s: None)
    with pytest.raises(UserException, match="Could not reach the UOL API"):
        client.ping_request()


@responses.activate
def test_connection_error_is_retried_before_giving_up():
    """Transport errors are retried; if the retry succeeds, no exception is raised."""
    responses.add(
        responses.GET,
        f"{BASE}/v1/ping",
        body=requests.exceptions.ConnectionError("transient"),
    )
    responses.add(responses.GET, f"{BASE}/v1/ping", json={"status": "ok"}, status=200)
    slept = []
    client = UolClient(BASE, "e@x.cz", "t", max_retries=2, sleep=lambda s: slept.append(s))
    result = client.ping_request()
    assert result == {"status": "ok"}
    assert len(slept) == 1  # slept once between the two attempts


@responses.activate
def test_iter_records_connection_error_raises_userexception():
    """Consuming iter_records when transport keeps failing → UserException."""
    for _ in range(3):
        responses.add(
            responses.GET,
            f"{BASE}/v1/contacts",
            body=requests.exceptions.ConnectionError("refused"),
        )
    client = UolClient(BASE, "e@x.cz", "t", max_retries=1, sleep=lambda s: None)
    with pytest.raises(UserException, match="Could not reach the UOL API"):
        list(client.iter_records("v1/contacts"))


@responses.activate
def test_ping_connection_error_returns_false():
    """ping() must absorb a connection error and return False (for testConnection action)."""
    responses.add(
        responses.GET,
        f"{BASE}/v1/ping",
        body=requests.exceptions.ConnectionError("no route to host"),
    )
    client = UolClient(BASE, "e@x.cz", "t")
    assert client.ping() is False


# ---------------------------------------------------------------------------
# TODO 4 – non-401/403/404 4xx → UserException
# ---------------------------------------------------------------------------


@responses.activate
def test_400_raises_userexception():
    responses.add(
        responses.GET,
        f"{BASE}/v1/ping",
        body='{"error":"bad request"}',
        status=400,
        content_type="application/json",
    )
    client = UolClient(BASE, "e@x.cz", "t")
    with pytest.raises(UserException, match="400"):
        client.ping_request()


@responses.activate
def test_422_raises_userexception():
    responses.add(
        responses.GET,
        f"{BASE}/v1/ping",
        body='{"error":"unprocessable"}',
        status=422,
        content_type="application/json",
    )
    client = UolClient(BASE, "e@x.cz", "t")
    with pytest.raises(UserException, match="422"):
        client.ping_request()


@responses.activate
def test_400_does_not_raise_raw_http_error():
    """Ensure the exception is a UserException, not a raw requests.HTTPError."""
    responses.add(responses.GET, f"{BASE}/v1/ping", body="bad request", status=400)
    client = UolClient(BASE, "e@x.cz", "t")
    with pytest.raises(UserException):
        client.ping_request()


# ---------------------------------------------------------------------------
# TODO 5 – non-JSON 200 body → UserException
# ---------------------------------------------------------------------------


@responses.activate
def test_non_json_200_raises_userexception():
    """A 200 response with an HTML body must raise UserException, not JSONDecodeError."""
    responses.add(
        responses.GET,
        f"{BASE}/v1/ping",
        body="<html>oops</html>",
        status=200,
        content_type="text/html",
    )
    client = UolClient(BASE, "e@x.cz", "t")
    with pytest.raises(UserException, match="non-JSON"):
        client.ping_request()


@responses.activate
def test_non_json_200_iter_records_raises_userexception():
    """iter_records with a non-JSON 200 body must also raise UserException."""
    responses.add(
        responses.GET,
        f"{BASE}/v1/contacts",
        body="<html>maintenance</html>",
        status=200,
        content_type="text/html",
    )
    client = UolClient(BASE, "e@x.cz", "t")
    with pytest.raises(UserException, match="non-JSON"):
        list(client.iter_records("v1/contacts"))
