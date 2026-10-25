"""Explain a recommendation for one draft as JSON (used by the explain-recommendation skill).

Usage (from backend/):
    .venv\\Scripts\\python -m model.explain --position TOP --ally "Lee Sin:JUNGLE" \\
        --enemy "Darius:TOP" --ban Garen [--champion Sett]

Champions are given by name (as in Data Dragon, case and punctuation do not matter).
Reads only the aggregates in SQLite; no Riot API call, so personal form (D) and comfort (E)
are neutral. `--champion` adds the full breakdown of one champion, also outside the top 5,
compared with the #1.
"""

import argparse
import difflib
import json
import re
import sys

from app import db
from app.api import RecommendIn
from app.config import Config

from . import criteria
from .data import Aggregates, Draft, Pick
from .recommend import TOP_N, percentage_points, recommend

WIN_PARTS = ["A", "B", "C", "D", "S"]


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


class ChampionNames:
    def __init__(self, names: dict[int, str]):
        self.names = names
        self.by_key = {_key(n): cid for cid, n in names.items()}

    def id(self, name: str) -> int:
        key = _key(name)
        if key in self.by_key:
            return self.by_key[key]
        close = difflib.get_close_matches(key, self.by_key, n=3)
        hint = f" Did you mean: {', '.join(self.names[self.by_key[c]] for c in close)}?" if close else ""
        raise SystemExit(f"unknown champion {name!r}.{hint}")

    def pick(self, text: str) -> Pick:
        name, sep, position = text.rpartition(":")
        if not sep:
            raise SystemExit(f"use Name:ROLE for picks, got {text!r}")
        return Pick(self.id(name), position.strip().upper())


def build_draft(names: ChampionNames, position, allies=(), enemies=(), bans=()) -> Draft:
    allies = [names.pick(a) for a in allies]
    enemies = [names.pick(e) for e in enemies]
    ban_ids = [names.id(b) for b in bans]
    RecommendIn(  # same validation as the API: roles unique, nothing picked twice or banned
        position=position.upper(),
        allies=[{"champion_id": p.champion_id, "position": p.position} for p in allies],
        enemies=[{"champion_id": p.champion_id, "position": p.position} for p in enemies],
        bans=ban_ids,
    )
    return Draft(position.upper(), allies=allies, enemies=enemies, bans=ban_ids)


def focus(agg: Aggregates, draft: Draft, champion_id: int, top: dict | None) -> dict:
    """Breakdown of one champion: rank among all candidates and gap to the #1 per criterion."""
    name = agg.names.get(champion_id, str(champion_id))
    if champion_id in draft.unavailable:
        return {"champion_id": champion_id, "name": name, "available": False,
                "reason": "banned or already picked"}
    full = recommend(agg, draft, top_n=10_000, smaa_samples=200, stability_k=TOP_N).candidates
    row = next((c for c in full if c["champion_id"] == champion_id), None)
    if row is None:
        roles = agg.champions[agg.champions["champion_id"] == champion_id]
        share = roles.set_index("position")["role_share"].round(3).to_dict()
        return {"champion_id": champion_id, "name": name, "available": False,
                "reason": f"not a candidate in {draft.position}: under {criteria.MIN_ROLE_SHARE:.0%} "
                          "of its games in this role",
                "role_share": share}
    out = {**row, "available": True, "candidates": len(full)}
    if top is not None and top["champion_id"] != champion_id:
        out["gap_to_first_pp"] = {c: round(row["criteria_pp"].get(c, 0) - top["criteria_pp"].get(c, 0), 2)
                                  for c in ["A", "B", "C", "D"]}
        out["gap_to_first_pp"]["S"] = round(percentage_points(row["criteria"]["S"])
                                            - percentage_points(top["criteria"]["S"]), 2)
        out["gap_to_first_pp"]["F"] = round(row["criteria"]["F"] - top["criteria"]["F"], 4)
    return out


def explain(agg: Aggregates, draft: Draft, champion_id: int | None = None) -> dict:
    rec = recommend(agg, draft, top_n=TOP_N)
    top = rec.candidates[0] if rec.candidates else None
    out = {
        "draft": {
            "position": draft.position,
            "allies": [f"{agg.names.get(p.champion_id)}:{p.position}" for p in draft.allies],
            "enemies": [f"{agg.names.get(p.champion_id)}:{p.position}" for p in draft.enemies],
            "bans": [agg.names.get(b) for b in draft.bans],
        },
        "meta": rec.meta,
        "top": rec.candidates,
        "notes": ["No player profile: D (personal form) and E (comfort) are neutral."],
    }
    if champion_id is not None:
        out["focus"] = focus(agg, draft, champion_id, top)
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Explain a v2 recommendation as JSON.")
    parser.add_argument("--db", default=Config.DATABASE_PATH)
    parser.add_argument("--position", required=True, help="TOP, JUNGLE, MIDDLE, BOTTOM or UTILITY")
    parser.add_argument("--ally", action="append", default=[], help='"Name:ROLE", repeatable')
    parser.add_argument("--enemy", action="append", default=[], help='"Name:ROLE", repeatable')
    parser.add_argument("--ban", action="append", default=[], help="champion name, repeatable")
    parser.add_argument("--champion", help="also explain this champion in detail")
    args = parser.parse_args(argv)
    conn = db.connect(args.db)
    agg = Aggregates.from_db(conn)
    conn.close()
    names = ChampionNames(agg.names)
    try:
        draft = build_draft(names, args.position, args.ally, args.enemy, args.ban)
    except ValueError as exc:  # pydantic ValidationError or unknown position
        raise SystemExit(f"invalid draft: {exc}") from None
    champion_id = names.id(args.champion) if args.champion else None
    result = explain(agg, draft, champion_id)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
