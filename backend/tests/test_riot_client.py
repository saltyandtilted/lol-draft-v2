import pytest

from pipeline.riot_client import RateLimiter, RiotApiError, RiotClient, RiotKeyError

FAKE_TEST_KEY = "TEST-not-a-real-key"


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_limiter_allows_burst_of_20_then_waits():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock, sleep=clock.sleep)

    for _ in range(20):
        limiter.acquire()
    assert clock.slept == []

    limiter.acquire()
    assert clock.slept and clock.now >= 1.0


def test_limiter_respects_100_per_two_minutes():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock, sleep=clock.sleep)

    for _ in range(101):
        limiter.acquire()

    # The 101st call has to wait until the first one leaves the 120 s window.
    assert clock.now >= 120.0
    timestamps = list(limiter._calls)
    for i in range(len(timestamps)):
        window = [t for t in timestamps if timestamps[i] <= t < timestamps[i] + 1.0]
        assert len(window) <= 20


class FakeResponse:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeSession:
    """Returns prepared responses in order and records requested URLs."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.urls = []

    def get(self, url, params=None, timeout=None):
        self.urls.append(url)
        return self.responses.pop(0)


def make_client(responses):
    clock = FakeClock()
    session = FakeSession(responses)
    client = RiotClient(
        FAKE_TEST_KEY,
        session=session,
        limiter_factory=lambda: RateLimiter(clock=clock, sleep=clock.sleep),
        sleep=clock.sleep,
    )
    return client, session, clock


def test_429_waits_for_retry_after_and_retries():
    client, _, clock = make_client(
        [FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200, ["EUN1_1"])]
    )

    assert client.match_ids("TEST-PUUID") == ["EUN1_1"]
    assert 7 in clock.slept
    assert client.rate_limited_count == 1


@pytest.mark.parametrize("status", [401, 403])
def test_expired_key_raises_without_leaking_key(status):
    client, _, _ = make_client([FakeResponse(status)])

    with pytest.raises(RiotKeyError) as exc:
        client.match("EUN1_1")
    assert "expired" in str(exc.value)
    assert FAKE_TEST_KEY not in str(exc.value)


def test_404_returns_none():
    client, _, _ = make_client([FakeResponse(404)])

    assert client.match("EUN1_404") is None


def test_server_errors_are_retried_then_raise():
    client, _, _ = make_client([FakeResponse(503)] * 4)

    with pytest.raises(RiotApiError):
        client.match("EUN1_1")


def test_key_is_sent_only_as_header():
    client, session, _ = make_client([FakeResponse(200, {})])
    client.match("EUN1_1")

    assert session.headers["X-Riot-Token"] == FAKE_TEST_KEY
    assert all(FAKE_TEST_KEY not in url for url in session.urls)


def test_platform_and_region_routing():
    client, session, _ = make_client([FakeResponse(200, []), FakeResponse(200, [])])
    client.league_entries("GOLD", "II")
    client.match_ids("TEST-PUUID")

    assert session.urls[0].startswith("https://eun1.api.riotgames.com/lol/league-exp/v4/")
    assert session.urls[1].startswith("https://europe.api.riotgames.com/lol/match/v5/")


def test_missing_key_is_rejected():
    with pytest.raises(RiotKeyError):
        RiotClient("")
