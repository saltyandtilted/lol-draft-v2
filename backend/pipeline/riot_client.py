"""Riot API client with client-side rate limiting.

Riot counts limits per routing value (eun1, europe, ...), so every host gets its own limiter.
A development key allows 20 requests per 1 s and 100 requests per 120 s.
"""

import logging
import time
from collections import deque
from collections.abc import Callable

import requests

log = logging.getLogger(__name__)

DEV_KEY_LIMITS = ((20, 1.0), (100, 120.0))

# Retry transient server errors a few times; 429 is retried for as long as Riot asks us to wait.
MAX_SERVER_ERROR_RETRIES = 3


class RiotKeyError(RuntimeError):
    """401/403: the key is missing, expired or not allowed. Renew it in .env."""


class RiotApiError(RuntimeError):
    pass


class RateLimiter:
    """Sliding-window limiter that satisfies several (max_calls, seconds) windows at once.

    `clock` and `sleep` are injectable so tests run without real waiting.
    """

    def __init__(
        self,
        limits=DEV_KEY_LIMITS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.limits = limits
        self.clock = clock
        self.sleep = sleep
        longest = max(seconds for _, seconds in limits)
        self._longest = longest
        self._calls: deque[float] = deque()

    def wait_time(self) -> float:
        now = self.clock()
        while self._calls and now - self._calls[0] >= self._longest:
            self._calls.popleft()
        wait = 0.0
        for max_calls, seconds in self.limits:
            in_window = [t for t in self._calls if now - t < seconds]
            if len(in_window) >= max_calls:
                # The oldest call inside the window must leave it before we may call again.
                oldest = in_window[-max_calls]
                wait = max(wait, oldest + seconds - now)
        return wait

    def acquire(self) -> None:
        while (wait := self.wait_time()) > 0:
            self.sleep(wait + 0.05)
        self._calls.append(self.clock())

    def penalize(self, seconds: float) -> None:
        """After a 429, block this host for `seconds` (Riot's Retry-After)."""
        self.sleep(seconds)


class RiotClient:
    def __init__(
        self,
        api_key: str,
        platform: str = "eun1",
        region: str = "europe",
        session: requests.Session | None = None,
        limiter_factory: Callable[[], RateLimiter] = RateLimiter,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key:
            raise RiotKeyError("RIOT_API_KEY is not set in .env")
        self.platform = platform
        self.region = region
        self.session = session or requests.Session()
        # The key travels only in this header, never in URLs or logs.
        self.session.headers["X-Riot-Token"] = api_key
        self._limiter_factory = limiter_factory
        self._limiters: dict[str, RateLimiter] = {}
        self._sleep = sleep
        self.request_count = 0
        self.rate_limited_count = 0

    def _limiter(self, host: str) -> RateLimiter:
        if host not in self._limiters:
            self._limiters[host] = self._limiter_factory()
        return self._limiters[host]

    def get(self, routing: str, path: str, params: dict | None = None):
        """GET https://{routing}.api.riotgames.com{path}. Returns parsed JSON, or None on 404."""
        host = f"{routing}.api.riotgames.com"
        url = f"https://{host}{path}"
        limiter = self._limiter(host)
        server_errors = 0
        while True:
            limiter.acquire()
            self.request_count += 1
            try:
                response = self.session.get(url, params=params, timeout=15)
            except requests.RequestException as exc:
                server_errors += 1
                if server_errors > MAX_SERVER_ERROR_RETRIES:
                    raise RiotApiError(f"network error on {path}: {type(exc).__name__}") from None
                self._sleep(2**server_errors)
                continue

            status = response.status_code
            if status == 200:
                return response.json()
            if status == 404:
                return None
            if status in (401, 403):
                raise RiotKeyError(
                    f"Riot API returned {status}: the development key has probably expired. "
                    "Renew it at developer.riotgames.com and update .env."
                )
            if status == 429:
                self.rate_limited_count += 1
                retry_after = float(response.headers.get("Retry-After", 10))
                log.warning(
                    "429 from %s (%s limit), waiting %.0f s",
                    host,
                    response.headers.get("X-Rate-Limit-Type", "unknown"),
                    retry_after,
                )
                limiter.penalize(retry_after)
                continue
            if status >= 500:
                server_errors += 1
                if server_errors > MAX_SERVER_ERROR_RETRIES:
                    raise RiotApiError(f"{status} on {path} after {server_errors} attempts")
                self._sleep(2**server_errors)
                continue
            raise RiotApiError(f"unexpected status {status} on {path}")

    # --- Endpoints used by the pipeline -------------------------------------------------------

    def league_entries(self, tier: str, division: str, page: int = 1) -> list[dict]:
        path = f"/lol/league-exp/v4/entries/RANKED_SOLO_5x5/{tier}/{division}"
        return self.get(self.platform, path, {"page": page}) or []

    def match_ids(self, puuid: str, count: int = 20, start_time: int | None = None) -> list[str]:
        params = {"queue": 420, "type": "ranked", "start": 0, "count": count}
        if start_time is not None:
            params["startTime"] = start_time
        path = f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
        return self.get(self.region, path, params) or []

    def match(self, match_id: str) -> dict | None:
        return self.get(self.region, f"/lol/match/v5/matches/{match_id}")
