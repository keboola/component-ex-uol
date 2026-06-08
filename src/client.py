"""HTTP client for the UOL Účetnictví REST API."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterator

import requests
from keboola.component.exceptions import UserException
from requests.auth import HTTPBasicAuth


class UolClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        token: str,
        *,
        max_per_window: int = 30,
        window_seconds: float = 10.0,
        max_retries: int = 5,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(email, token)
        self.session.headers.update({"Accept": "application/json"})
        self._max_per_window = max_per_window
        self._window_seconds = window_seconds
        self._max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self._calls: deque[float] = deque()

    def ping(self) -> bool:
        resp = self.session.get(f"{self.base_url}/v1/ping")
        return resp.status_code == 200

    def iter_records(self, path: str, params: dict | None = None) -> Iterator[dict]:
        query = dict(params or {})
        query.setdefault("per_page", 250)
        query["page"] = 1
        while True:
            data = self._request("GET", path, params=query)
            items = data.get("items", [])
            yield from items
            has_next = bool(data.get("_meta", {}).get("pagination", {}).get("next"))
            if not has_next or not items:
                break
            query["page"] += 1

    def ping_request(self) -> dict:
        return self._request("GET", "v1/ping")

    def _request(self, method: str, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(self._max_retries + 1):
            self._throttle()
            resp = self.session.request(method, url, params=params)
            self._record_call()
            if resp.status_code == 429 and attempt < self._max_retries:
                self._sleep(self._retry_after(resp))
                continue
            if resp.status_code >= 500 and attempt < self._max_retries:
                self._sleep(min(2 ** attempt, 30))
                continue
            if resp.status_code >= 400:
                self._raise_for_status(resp)
            return resp.json()
        raise UserException(f"UOL API still failing after {self._max_retries} retries: {url}")

    def _throttle(self) -> None:
        now = self._clock()
        while self._calls and now - self._calls[0] >= self._window_seconds:
            self._calls.popleft()
        if len(self._calls) >= self._max_per_window:
            wait = self._window_seconds - (now - self._calls[0])
            if wait > 0:
                self._sleep(wait)

    def _record_call(self) -> None:
        self._calls.append(self._clock())

    @staticmethod
    def _retry_after(resp: requests.Response) -> float:
        try:
            return float(resp.headers.get("Retry-After", 30))
        except (TypeError, ValueError):
            return 30.0

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code in (401, 403):
            raise UserException(
                "UOL authentication failed (check email + API token and that the "
                f"account has the 'REST API' permission). HTTP {resp.status_code}."
            )
        if resp.status_code == 404:
            raise UserException(f"UOL endpoint not found: {resp.url} (HTTP 404).")
        resp.raise_for_status()
