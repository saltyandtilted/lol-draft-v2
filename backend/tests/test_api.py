"""Recommendation API. TEST DATA ONLY: synthetic aggregates and fake Riot responses."""

import pytest

from app import db
from pipeline import ddragon
from pipeline.riot_client import RiotKeyError
from tests.model_factory import AD_CARRY, AD_TANK, AP_TANK, FLEX, make_aggregates
from tests.test_profile import NOW_MS, TEST_PUUID, FakeProfileClient, make_match

TEST_CHAMPIONS = [
    {"champion_id": cid, "champion_key": f"Test{cid}", "name": f"Test Champion {cid}", "tags": ["Fighter"]}
    for cid in [1, 2, 3, 4, 5, 6, 50, 51, 52, 53, 54]
]


class ExpiredKeyClient:
    def account_by_riot_id(self, name, tag):
        raise RiotKeyError("Riot API returned 401")


@pytest.fixture
def api(make_client, tmp_path):
    """Factory for a client with test champions in SQLite and synthetic aggregates."""

    def _make(riot_client=None, aggregates=True):
        path = str(tmp_path / "test.db")
        db.init_db(path)
        with db.connect(path) as conn:
            ddragon.store_champions(conn, TEST_CHAMPIONS, "0.0.TEST")
        overrides = {"DATABASE_PATH": path, "RIOT_API_KEY": "TEST-not-a-real-key"}
        if aggregates:
            overrides["AGGREGATES"] = make_aggregates(matchups=[(AP_TANK, "TOP", 54, 1, 0.15, 40)])
        if riot_client is not None:
            overrides["RIOT_CLIENT_FACTORY"] = lambda platform: riot_client
        return make_client(**overrides)

    return _make


def post(client, **body):
    return client.post("/api/recommend", json={"position": "TOP", **body})


def test_champions_have_icons_and_viable_positions(api):
    body = api().get("/api/champions").get_json()

    flex = next(c for c in body["champions"] if c["id"] == FLEX)
    assert flex["icon"] == "https://ddragon.leagueoflegends.com/cdn/0.0.TEST/img/champion/Test6.png"
    assert flex["positions"] == ["MIDDLE"]  # 3 % share in TOP is below the threshold
    assert body["ddragon_version"] == "0.0.TEST"


def test_meta_lists_platforms_and_patch(api):
    body = api().get("/api/meta").get_json()

    assert body["patch"] == "TEST"
    assert {"id": "eun1", "label": "EUNE"} in body["platforms"]


def test_recommend_without_riot_id_returns_explained_top5(api):
    response = post(api(), enemies=[{"champion_id": 54, "position": "TOP"}], bans=[AD_CARRY])

    assert response.status_code == 200
    body = response.get_json()
    ids = [c["champion_id"] for c in body["candidates"]]
    assert AD_CARRY not in ids and FLEX not in ids
    first = body["candidates"][0]
    for key in ["icon", "why", "contributions", "criteria_pp", "games", "interval_pp",
                "top5_probability", "low_data"]:
        assert key in first
    assert body["profile"] == {"used": False}
    assert "neutral" in body["warnings"][0]
    assert body["meta"]["patch"] == "TEST"


def test_recommend_uses_player_profile(api):
    client = FakeProfileClient(
        account={"puuid": TEST_PUUID},
        mastery=[{"championId": AD_TANK, "championPoints": 300_000, "lastPlayTime": NOW_MS}],
        matches={f"EUN1_{i}": make_match(AD_TANK, True, 1) for i in range(5)},
    )

    body = post(api(riot_client=client), riot_id="Tester#TEST").get_json()

    assert body["profile"]["used"] is True and body["profile"]["games"] == 5
    tank = next(c for c in body["candidates"] if c["champion_id"] == AD_TANK)
    assert tank["criteria"]["D"] > 0 and tank["criteria"]["E"] > 0


def test_profile_is_cached_between_requests(api):
    client = FakeProfileClient(account={"puuid": TEST_PUUID})
    app_client = api(riot_client=client)

    post(app_client, riot_id="Tester#TEST")
    client.account = None  # a second fetch would now fail with 404
    response = post(app_client, riot_id="tester#test")

    assert response.status_code == 200
    assert response.get_json()["profile"]["cached"] is True


def test_unknown_riot_id_is_404(api):
    response = post(api(riot_client=FakeProfileClient(account=None)), riot_id="Nobody#TEST")

    assert response.status_code == 404
    assert response.get_json()["error"] == "riot_id_not_found"


def test_bad_riot_id_format_is_400(api):
    response = post(api(), riot_id="NoTag")

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_riot_id"


def test_expired_key_still_recommends_with_warning(api):
    response = post(api(riot_client=ExpiredKeyClient()), riot_id="Tester#TEST")

    assert response.status_code == 200
    body = response.get_json()
    assert body["candidates"]
    assert "expired" in body["warnings"][0]
    assert "TEST-not-a-real-key" not in response.get_data(as_text=True)


@pytest.mark.parametrize("body, fragment", [
    ({"position": "SUPPORT"}, "position"),
    ({"enemies": [{"champion_id": 50, "position": "TOP"}, {"champion_id": 51, "position": "TOP"}]},
     "share a role"),
    ({"allies": [{"champion_id": 50, "position": "JUNGLE"}],
      "enemies": [{"champion_id": 50, "position": "JUNGLE"}]}, "picked twice"),
    ({"allies": [{"champion_id": 50, "position": "TOP"}]}, "already plays TOP"),
    ({"bans": [50], "enemies": [{"champion_id": 50, "position": "JUNGLE"}]}, "banned"),
    ({"bans": list(range(11))}, "bans"),
    ({"platform": "xx1"}, "platform"),
])
def test_invalid_draft_is_400(api, body, fragment):
    response = post(api(), **body)

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_draft"
    assert fragment in response.get_json()["message"]


def test_unknown_champion_is_400(api):
    response = post(api(), bans=[9999])

    assert response.status_code == 400
    assert response.get_json()["error"] == "unknown_champion"


def test_missing_aggregates_is_503(api):
    response = post(api(aggregates=False))

    assert response.status_code == 503
    assert "pipeline.aggregate" in response.get_json()["message"]
