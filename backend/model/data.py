"""Model inputs: the draft, the player profile and the precomputed aggregates."""

import json
from dataclasses import dataclass, field

import pandas as pd

POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


@dataclass(frozen=True)
class Pick:
    champion_id: int
    position: str


@dataclass
class Draft:
    position: str
    allies: list[Pick] = field(default_factory=list)
    enemies: list[Pick] = field(default_factory=list)
    bans: list[int] = field(default_factory=list)

    def __post_init__(self):
        for pick in [Pick(0, self.position), *self.allies, *self.enemies]:
            if pick.position not in POSITIONS:
                raise ValueError(f"unknown position {pick.position!r}")

    @property
    def known_enemies(self) -> int:
        return len(self.enemies)

    @property
    def unavailable(self) -> set[int]:
        return set(self.bans) | {p.champion_id for p in self.allies + self.enemies}


@dataclass(frozen=True)
class PlayerGame:
    champion_id: int
    win: bool
    days_ago: float


@dataclass(frozen=True)
class Mastery:
    points: int
    days_since_played: float


@dataclass
class PlayerProfile:
    """Recent ranked games and mastery of the player. Fetched from the Riot API by app/profile.py."""

    games: list[PlayerGame] = field(default_factory=list)
    mastery: dict[int, Mastery] = field(default_factory=dict)


@dataclass
class Aggregates:
    champions: pd.DataFrame  # champion_role_stats
    matchups: pd.DataFrame
    duos: pd.DataFrame
    profile: pd.DataFrame
    meta: dict
    names: dict[int, str] = field(default_factory=dict)  # Data Dragon champion names

    @classmethod
    def from_db(cls, conn) -> "Aggregates":
        read = lambda table: pd.read_sql_query(f"SELECT * FROM {table}", conn)  # noqa: E731
        try:
            meta = {k: json.loads(v) for k, v in conn.execute("SELECT key, value FROM aggregate_meta")}
        except Exception as exc:
            raise RuntimeError("aggregates missing, run python -m pipeline.aggregate") from exc
        names = dict(conn.execute("SELECT champion_id, name FROM champions").fetchall())
        return cls(read("champion_role_stats"), read("matchup_stats"), read("duo_stats"),
                   read("champion_profile"), meta, names)

    @classmethod
    def from_tables(cls, tables: dict, meta: dict, names: dict | None = None) -> "Aggregates":
        """From the output of pipeline.aggregate.compute, kept in memory (backtest)."""
        return cls(tables["champion_role_stats"], tables["matchup_stats"], tables["duo_stats"],
                   tables["champion_profile"], meta, names or {})
