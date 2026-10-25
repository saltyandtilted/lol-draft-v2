"""Recommendation API. Reads only precomputed aggregates and the cached player profile."""

import json
import logging
import math
import time
from typing import Literal

from flask import Blueprint, current_app, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from model import criteria
from model.data import POSITIONS, Aggregates, Draft, Pick
from model.recommend import recommend
from pipeline.riot_client import RiotApiError, RiotClient, RiotKeyError, RiotRateLimited

from . import db
from .profile import PLATFORMS, ProfileCache, RiotIdNotFound, fetch_profile, parse_riot_id

log = logging.getLogger(__name__)

bp = Blueprint("api", __name__, url_prefix="/api")

ICON_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{key}.png"
Position = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
# A recommendation must not hang on the Riot rate limit: wait at most this long, then answer
# without the personal criteria.
PROFILE_MAX_WAIT = 5.0


class ApiError(Exception):
    def __init__(self, status: int, error: str, message: str):
        super().__init__(message)
        self.status, self.error, self.message = status, error, message


# --- Request schema -----------------------------------------------------------------------------

class PickIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    champion_id: int
    position: Position


class RecommendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    riot_id: str | None = None
    platform: str = "eun1"
    position: Position
    allies: list[PickIn] = Field(default_factory=list, max_length=4)
    enemies: list[PickIn] = Field(default_factory=list, max_length=5)
    bans: list[int] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def check_draft(self):
        if self.platform not in PLATFORMS:
            raise ValueError(f"unknown platform {self.platform!r}")
        ally_roles = [p.position for p in self.allies]
        if self.position in ally_roles:
            raise ValueError(f"an ally already plays {self.position}")
        for team, roles in (("allies", ally_roles), ("enemies", [p.position for p in self.enemies])):
            if len(roles) != len(set(roles)):
                raise ValueError(f"two {team} share a role")
        picked = [p.champion_id for p in self.allies + self.enemies]
        if len(picked) != len(set(picked)):
            raise ValueError("a champion is picked twice")
        if set(picked) & set(self.bans):
            raise ValueError("a banned champion is also picked")
        return self


# --- Shared state: aggregates, champions, profile cache, Riot clients ---------------------------

def _state() -> dict:
    return current_app.extensions.setdefault("draft_api", {
        "aggregates": None, "computed_at": None,
        "profiles": ProfileCache(), "clients": {},
    })


def _aggregates() -> Aggregates:
    """Aggregates from SQLite, reloaded only when the pipeline wrote a new snapshot."""
    override = current_app.config.get("AGGREGATES")
    if override is not None:
        return override
    state = _state()
    with db.connect(current_app.config["DATABASE_PATH"]) as conn:
        try:
            row = conn.execute("SELECT value FROM aggregate_meta WHERE key = 'computed_at'").fetchone()
        except Exception:
            row = None
        if row is None:
            raise ApiError(503, "no_aggregates",
                           "No aggregates in the database. Run: python -m pipeline.aggregate")
        computed_at = json.loads(row["value"])
        if state["aggregates"] is None or state["computed_at"] != computed_at:
            state["aggregates"] = Aggregates.from_db(conn)
            state["computed_at"] = computed_at
    return state["aggregates"]


def _champions() -> list[dict]:
    with db.connect(current_app.config["DATABASE_PATH"]) as conn:
        rows = conn.execute("SELECT champion_id, champion_key, name, tags, ddragon_version "
                            "FROM champions ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def _riot_client(platform: str) -> RiotClient:
    """One client per platform for the app's lifetime, so its rate limiter sees every call."""
    factory = current_app.config.get("RIOT_CLIENT_FACTORY")
    if factory is not None:
        return factory(platform)
    clients = _state()["clients"]
    if platform not in clients:
        clients[platform] = RiotClient(current_app.config["RIOT_API_KEY"], platform=platform,
                                       region=PLATFORMS[platform]["region"], max_wait=PROFILE_MAX_WAIT)
    return clients[platform]


def _profile(riot_id: str, platform: str) -> tuple:
    """Return (profile or None, info dict, warnings). User errors raise ApiError."""
    try:
        parse_riot_id(riot_id)
    except ValueError as exc:
        raise ApiError(400, "invalid_riot_id", str(exc)) from None
    try:
        profile, cached = _state()["profiles"].get(
            platform, riot_id,
            lambda: fetch_profile(_riot_client(platform), riot_id, int(time.time() * 1000)),
        )
    except RiotIdNotFound as exc:
        raise ApiError(404, "riot_id_not_found",
                       f"{exc} on {PLATFORMS[platform]['label']}. Check the name, tag and region.") from None
    except RiotKeyError:
        # The key is missing or expired: recommend anyway, without the personal criteria.
        return None, {"used": False}, [
            "Riot API key is missing or expired – renew it in .env. "
            "Personal form (D) and comfort (E) are neutral."]
    except RiotRateLimited as exc:
        log.warning("profile fetch skipped: %s", exc)
        return None, {"used": False}, [
            "Riot API rate limit reached (several new Riot IDs within 2 minutes) – try again in a "
            "minute or two. Personal form (D) and comfort (E) are neutral."]
    except RiotApiError as exc:
        log.warning("profile fetch failed: %s", exc)
        return None, {"used": False}, [
            "Riot API is not responding. Personal form (D) and comfort (E) are neutral."]
    info = {"used": True, "cached": cached, "games": len(profile.games),
            "mastery_champions": len(profile.mastery)}
    warnings = [] if profile.games else [
        "No recent ranked games found: personal form (D) is neutral."]
    return profile, info, warnings


def _json_safe(value):
    """NaN (e.g. Spearman with < 3 candidates) is not valid JSON; send null instead."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


# --- Routes -------------------------------------------------------------------------------------

@bp.errorhandler(ApiError)
def _api_error(exc: ApiError):
    return jsonify(error=exc.error, message=exc.message), exc.status


@bp.get("/champions")
def champions():
    agg = _aggregates()
    viable = agg.champions[agg.champions["role_share"] >= criteria.MIN_ROLE_SHARE]
    positions = viable.groupby("champion_id")["position"].apply(list).to_dict()
    rows = _champions()
    version = rows[0]["ddragon_version"] if rows else None
    return jsonify(ddragon_version=version, champions=[{
        "id": r["champion_id"],
        "key": r["champion_key"],
        "name": r["name"],
        "tags": json.loads(r["tags"]),
        "icon": ICON_URL.format(version=r["ddragon_version"], key=r["champion_key"]),
        "positions": [p for p in POSITIONS if p in positions.get(r["champion_id"], [])],
    } for r in rows])


@bp.get("/meta")
def meta():
    agg = _aggregates()
    return jsonify(
        patch=agg.meta.get("current_patch"),
        data_computed_at=agg.meta.get("computed_at"),
        matches_used=agg.meta.get("matches_used"),
        tier_group=agg.meta.get("tier_group"),
        positions=list(POSITIONS),
        platforms=[{"id": k, "label": v["label"]} for k, v in PLATFORMS.items()],
        default_platform=current_app.config["DEFAULT_PLATFORM"],
    )


@bp.post("/recommend")
def recommend_route():
    try:
        body = RecommendIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        message = first["msg"].removeprefix("Value error, ")
        raise ApiError(400, "invalid_draft", f"{where}: {message}" if where else message) from None

    champions = {r["champion_id"]: r for r in _champions()}
    used = {p.champion_id for p in body.allies + body.enemies} | set(body.bans)
    unknown = sorted(used - set(champions))
    if unknown:
        raise ApiError(400, "unknown_champion", f"unknown champion ids: {unknown}")

    agg = _aggregates()
    profile, profile_info, warnings = None, {"used": False}, []
    if body.riot_id and body.riot_id.strip():
        profile, profile_info, warnings = _profile(body.riot_id, body.platform)
    else:
        warnings.append("No Riot ID: personal form (D) and comfort (E) are neutral.")

    draft = Draft(
        position=body.position,
        allies=[Pick(p.champion_id, p.position) for p in body.allies],
        enemies=[Pick(p.champion_id, p.position) for p in body.enemies],
        bans=sorted(set(body.bans)),
    )
    rec = recommend(agg, draft, profile)
    for c in rec.candidates:
        r = champions.get(c["champion_id"])
        c["key"] = r["champion_key"] if r else None
        c["icon"] = ICON_URL.format(version=r["ddragon_version"], key=r["champion_key"]) if r else None
    if not rec.candidates:
        warnings.append(f"No viable {body.position} champion is left after bans and picks.")
    return jsonify(_json_safe({
        "candidates": rec.candidates,
        "meta": rec.meta,
        "profile": profile_info,
        "warnings": warnings,
    }))
