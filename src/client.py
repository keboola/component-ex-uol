"""HTTP client for the UOL Účetnictví REST API."""

from __future__ import annotations

import time
from collections import deque

import requests
from keboola.component.exceptions import UserException  # noqa: F401
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
