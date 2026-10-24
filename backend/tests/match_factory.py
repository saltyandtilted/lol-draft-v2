"""TEST DATA ONLY: builders for fake match-v5 responses. Nothing here comes from the real API."""

import copy

POSITIONS = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
# Real Data Dragon numeric keys, so tests read naturally (Annie, Olaf, Galio, ...).
TEST_CHAMPION_IDS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}


def make_match(match_id: str = "EUN1_TEST_1", blue_win: bool = True, **info_overrides) -> dict:
    participants = []
    for team_index, team_id in enumerate((100, 200)):
        for i, position in enumerate(POSITIONS):
            participants.append(
                {
                    "teamId": team_id,
                    "championId": 1 + team_index * 5 + i,
                    "teamPosition": position,
                    "win": blue_win if team_id == 100 else not blue_win,
                    "gameEndedInEarlySurrender": False,
                    "puuid": f"TEST-PUUID-{team_id}-{i}",
                    # Fake stats: even positions deal physical damage, odd ones magic damage.
                    "physicalDamageDealtToChampions": 20000 if i % 2 == 0 else 2000,
                    "magicDamageDealtToChampions": 2000 if i % 2 == 0 else 20000,
                    "trueDamageDealtToChampions": 1000,
                    "totalDamageTaken": 30000 if position == "TOP" else 15000,
                    "damageSelfMitigated": 25000 if position == "TOP" else 8000,
                    "timeCCingOthers": 40 if position == "UTILITY" else 10,
                }
            )
    info = {
        "queueId": 420,
        "gameVersion": "15.20.712.3456",
        "gameCreation": 1_760_000_000_000,
        "gameDuration": 1800,
        "gameEndTimestamp": 1_760_001_800_000,
        "participants": participants,
        "teams": [
            {"teamId": 100, "win": blue_win, "bans": [{"championId": 11, "pickTurn": 1}]},
            {"teamId": 200, "win": not blue_win, "bans": [{"championId": -1, "pickTurn": 6}]},
        ],
    }
    info.update(info_overrides)
    return {"metadata": {"matchId": match_id}, "info": info}


def with_participant(match: dict, index: int, **fields) -> dict:
    match = copy.deepcopy(match)
    match["info"]["participants"][index].update(fields)
    return match
