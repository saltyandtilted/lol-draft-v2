"""Download-time quality checks for a single match.

Each check returns a list of (reason, detail) problems. An empty list means the match is clean.
The first reason becomes the quarantine reason; all details are kept.
"""

from pydantic import ValidationError

from .schemas import Match

RANKED_SOLO_QUEUE = 420
POSITIONS = {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}
# Remakes end before 3:30 or so; anything under 5 minutes is not a real game.
MIN_DURATION_SECONDS = 300

Problems = list[tuple[str, str]]


def parse_match(raw: dict) -> tuple[Match | None, Problems]:
    try:
        return Match.model_validate(raw), []
    except ValidationError as exc:
        return None, [("schema_error", f"{exc.error_count()} validation errors")]


def check_queue_and_version(match: Match) -> Problems:
    problems = []
    if match.info.queueId != RANKED_SOLO_QUEUE:
        problems.append(("wrong_queue", f"queueId={match.info.queueId}"))
    if not match.info.gameVersion.strip():
        problems.append(("missing_game_version", "gameVersion is empty"))
    return problems


def check_remake(match: Match) -> Problems:
    problems = []
    if any(p.gameEndedInEarlySurrender for p in match.info.participants):
        problems.append(("early_surrender", "gameEndedInEarlySurrender=true"))
    duration = match.info.duration_seconds
    if duration < MIN_DURATION_SECONDS:
        problems.append(("too_short", f"duration={duration}s"))
    return problems


def check_completeness(match: Match) -> Problems:
    participants = match.info.participants
    if len(participants) != 10:
        return [("incomplete", f"{len(participants)} participants")]
    problems = []
    for team_id in (100, 200):
        team = [p for p in participants if p.teamId == team_id]
        positions = [p.teamPosition for p in team]
        invalid = [pos or "<empty>" for pos in positions if pos not in POSITIONS]
        if len(team) != 5:
            problems.append(("incomplete", f"team {team_id} has {len(team)} players"))
        elif invalid:
            problems.append(("invalid_position", f"team {team_id}: {', '.join(invalid)}"))
        elif len(set(positions)) != 5:
            problems.append(("duplicate_position", f"team {team_id}: {sorted(positions)}"))
    winners = {p.teamId for p in participants if p.win}
    if len(winners) != 1:
        problems.append(("inconsistent_result", f"winning teams: {sorted(winners)}"))
    return problems


def check_champions(match: Match, known_ids: set[int]) -> Problems:
    unknown = sorted({p.championId for p in match.info.participants} - known_ids)
    if unknown:
        return [("unknown_champion", f"championId not in Data Dragon: {unknown}")]
    return []


def validate_match(raw: dict, known_champion_ids: set[int]) -> tuple[Match | None, Problems]:
    """Run all checks. Returns the parsed match (if parseable) and the list of problems."""
    match, problems = parse_match(raw)
    if match is None:
        return None, problems
    problems += check_queue_and_version(match)
    problems += check_remake(match)
    problems += check_completeness(match)
    problems += check_champions(match, known_champion_ids)
    return match, problems


def patch_of(game_version: str) -> str:
    """"15.20.712.3456" -> "15.20"."""
    return ".".join(game_version.split(".")[:2])
