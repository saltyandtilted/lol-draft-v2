"""Player profile fetching and caching. TEST DATA ONLY: fake Riot responses, no real API calls."""

import pytest

from app.profile import ProfileCache, RiotIdNotFound, fetch_profile, parse_riot_id
from model.data import PlayerProfile
from tests.test_riot_client import FakeResponse, make_client

NOW_MS = 1_800_000_000_000
DAY_MS = 86_400_000
TEST_PUUID = "TEST-PUUID-ME"


class FakeProfileClient:
    """Stands in for RiotClient with prepared endpoint results."""

    def __init__(self, account=None, mastery=(), matches=None):
        self.account = account
        self.mastery = list(mastery)
        self.matches = matches or {}

    def account_by_riot_id(self, name, tag):
        return self.account

    def mastery_by_puuid(self, puuid):
        return self.mastery

    def match_ids(self, puuid, count=20):
        return list(self.matches)[:count]

    def match(self, match_id):
        return self.matches[match_id]


def make_match(champion_id, win, days_ago, remake=False):
    other = {"puuid": "TEST-PUUID-OTHER", "championId": 999, "win": not win}
    me = {"puuid": TEST_PUUID, "championId": champion_id, "win": win,
          "gameEndedInEarlySurrender": remake}
    return {"info": {"gameCreation": NOW_MS - days_ago * DAY_MS, "participants": [other, me]}}


@pytest.mark.parametrize("raw, expected", [
    ("Name#EUNE", ("Name", "EUNE")),
    ("  Two Words#tag ", ("Two Words", "tag")),
    ("A#B#C", ("A#B", "C")),
])
def test_parse_riot_id(raw, expected):
    assert parse_riot_id(raw) == expected


@pytest.mark.parametrize("raw", ["NoTag", "#TAG", "Name#", "   "])
def test_parse_riot_id_rejects_bad_shape(raw):
    with pytest.raises(ValueError):
        parse_riot_id(raw)


def test_fetch_profile_maps_games_and_mastery_and_skips_remakes():
    client = FakeProfileClient(
        account={"puuid": TEST_PUUID},
        mastery=[{"championId": 1, "championPoints": 50_000, "lastPlayTime": NOW_MS - 3 * DAY_MS}],
        matches={
            "EUN1_1": make_match(1, True, 2),
            "EUN1_2": make_match(2, False, 5),
            "EUN1_3": make_match(3, True, 1, remake=True),
            "EUN1_4": None,  # 404
        },
    )

    profile = fetch_profile(client, "Tester#TEST", NOW_MS)

    assert [(g.champion_id, g.win, g.days_ago) for g in profile.games] == [(1, True, 2), (2, False, 5)]
    assert profile.mastery[1].points == 50_000
    assert profile.mastery[1].days_since_played == pytest.approx(3)


def test_fetch_profile_unknown_riot_id():
    with pytest.raises(RiotIdNotFound):
        fetch_profile(FakeProfileClient(account=None), "Nobody#TEST", NOW_MS)


def test_account_lookup_encodes_riot_id_in_url():
    client, session, _ = make_client([FakeResponse(200, {"puuid": TEST_PUUID})])

    client.account_by_riot_id("Two Words", "EUNE")

    assert session.urls == [
        "https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/Two%20Words/EUNE"
    ]


def test_cache_hits_within_ttl_and_refetches_after():
    now = [0.0]
    cache = ProfileCache(ttl=15 * 60, clock=lambda: now[0])
    fetched = []

    def fetch():
        fetched.append(1)
        return PlayerProfile()

    assert cache.get("eun1", "Tester#TEST", fetch)[1] is False
    now[0] = 10 * 60
    assert cache.get("eun1", "tester#test", fetch)[1] is True  # case-insensitive key
    assert cache.get("euw1", "Tester#TEST", fetch)[1] is False  # other platform
    now[0] = 16 * 60
    assert cache.get("eun1", "Tester#TEST", fetch)[1] is False
    assert len(fetched) == 3
