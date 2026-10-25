"""Player profile for criteria D and E: recent ranked games and champion mastery.

Fetched from the Riot API on demand and cached in memory, so repeated recommendations
for the same player do not hit the rate limit. No player score is computed or stored.
"""

import time
from collections.abc import Callable

from model.data import Mastery, PlayerGame, PlayerProfile
from pipeline.riot_client import RiotClient

# Platform -> regional routing value. EUNE is the default.
PLATFORMS = {
    "eun1": {"label": "EUNE", "region": "europe"},
    "euw1": {"label": "EUW", "region": "europe"},
    "na1": {"label": "NA", "region": "americas"},
    "kr": {"label": "KR", "region": "asia"},
}
# Each game is one match-v5 request: 50 games + account + mastery stay under the 100 requests
# per 2 minutes of a development key, and the profile is cached for CACHE_SECONDS.
RECENT_GAMES = 50
CACHE_SECONDS = 15 * 60
DAY_MS = 86_400_000


class RiotIdNotFound(LookupError):
    pass


def parse_riot_id(riot_id: str) -> tuple[str, str]:
    """'Name#TAG' -> ('Name', 'TAG'). Raises ValueError for any other shape."""
    name, sep, tag = riot_id.strip().rpartition("#")
    if not sep or not name.strip() or not tag.strip():
        raise ValueError("Riot ID must look like Name#TAG")
    return name.strip(), tag.strip()


def fetch_profile(client: RiotClient, riot_id: str, now_ms: int,
                  recent_games: int = RECENT_GAMES) -> PlayerProfile:
    name, tag = parse_riot_id(riot_id)
    account = client.account_by_riot_id(name, tag)
    if account is None:
        raise RiotIdNotFound(f"Riot ID {name}#{tag} not found")
    puuid = account["puuid"]

    mastery = {
        int(m["championId"]): Mastery(
            points=int(m["championPoints"]),
            days_since_played=max(0.0, (now_ms - int(m["lastPlayTime"])) / DAY_MS),
        )
        for m in client.mastery_by_puuid(puuid)
    }

    games = []
    for match_id in client.match_ids(puuid, count=recent_games):
        match = client.match(match_id)
        if match is None:
            continue
        info = match["info"]
        me = next((p for p in info["participants"] if p.get("puuid") == puuid), None)
        # Remakes say nothing about form.
        if me is None or me.get("gameEndedInEarlySurrender"):
            continue
        games.append(PlayerGame(
            champion_id=int(me["championId"]),
            win=bool(me["win"]),
            days_ago=max(0.0, (now_ms - int(info["gameCreation"])) / DAY_MS),
        ))
    return PlayerProfile(games=games, mastery=mastery)


class ProfileCache:
    """In-memory cache of profiles keyed by (platform, lower-case Riot ID)."""

    def __init__(self, ttl: float = CACHE_SECONDS, clock: Callable[[], float] = time.time):
        self.ttl = ttl
        self.clock = clock
        self._items: dict[tuple[str, str], tuple[float, PlayerProfile]] = {}

    def get(self, platform: str, riot_id: str,
            fetch: Callable[[], PlayerProfile]) -> tuple[PlayerProfile, bool]:
        """Return (profile, from_cache); calls `fetch` on a miss or after the TTL."""
        key = (platform, riot_id.strip().lower())
        hit = self._items.get(key)
        if hit and self.clock() - hit[0] < self.ttl:
            return hit[1], True
        profile = fetch()
        self._items[key] = (self.clock(), profile)
        return profile, False
