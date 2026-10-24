"""Pydantic models for the parts of Riot API responses the pipeline uses.

Unknown fields are ignored; missing required fields raise ValidationError,
which the collector turns into a quarantine record ("schema_error").
"""

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class LeagueEntry(_Model):
    puuid: str
    tier: str
    rank: str  # division I-IV


class Participant(_Model):
    teamId: int
    championId: int
    teamPosition: str = ""
    win: bool
    gameEndedInEarlySurrender: bool = False
    physicalDamageDealtToChampions: int = 0
    magicDamageDealtToChampions: int = 0
    trueDamageDealtToChampions: int = 0
    totalDamageTaken: int = 0
    damageSelfMitigated: int = 0
    timeCCingOthers: int = 0


class Ban(_Model):
    championId: int
    pickTurn: int


class Team(_Model):
    teamId: int
    win: bool
    bans: list[Ban] = []


class MatchInfo(_Model):
    queueId: int
    gameVersion: str = ""
    gameCreation: int
    gameDuration: int
    gameEndTimestamp: int | None = None
    participants: list[Participant]
    teams: list[Team]

    @property
    def duration_seconds(self) -> int:
        # Before patch 11.20 gameDuration was in milliseconds (no gameEndTimestamp then).
        if self.gameEndTimestamp is None:
            return self.gameDuration // 1000
        return self.gameDuration


class MatchMetadata(_Model):
    matchId: str


class Match(_Model):
    metadata: MatchMetadata
    info: MatchInfo
