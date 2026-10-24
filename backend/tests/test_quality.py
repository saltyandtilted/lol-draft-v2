import pytest

from pipeline.quality import patch_of, validate_match
from tests.match_factory import TEST_CHAMPION_IDS, make_match, with_participant


def reasons(raw):
    _, problems = validate_match(raw, TEST_CHAMPION_IDS)
    return [reason for reason, _ in problems]


def test_clean_match_passes():
    match, problems = validate_match(make_match(), TEST_CHAMPION_IDS)

    assert problems == []
    assert match.metadata.matchId == "EUN1_TEST_1"


@pytest.mark.parametrize(
    "raw, expected",
    [
        (make_match(queueId=440), "wrong_queue"),
        (make_match(gameVersion=""), "missing_game_version"),
        (with_participant(make_match(), 3, gameEndedInEarlySurrender=True), "early_surrender"),
        (make_match(gameDuration=200), "too_short"),
        (with_participant(make_match(), 0, teamPosition=""), "invalid_position"),
        (with_participant(make_match(), 7, teamPosition="Invalid"), "invalid_position"),
        (with_participant(make_match(), 1, teamPosition="TOP"), "duplicate_position"),
        (with_participant(make_match(), 2, championId=99999), "unknown_champion"),
        (with_participant(make_match(), 9, win=True), "inconsistent_result"),
    ],
)
def test_defective_match_is_flagged(raw, expected):
    assert expected in reasons(raw)


def test_missing_participant_is_incomplete():
    raw = make_match()
    raw["info"]["participants"].pop()

    assert reasons(raw)[0] == "incomplete"


def test_unparseable_response_is_schema_error():
    raw = make_match()
    del raw["info"]["participants"]

    assert reasons(raw) == ["schema_error"]


def test_remake_reports_all_problems():
    # A typical remake: early surrender flag and a 3 minute game.
    raw = with_participant(make_match(gameDuration=190), 0, gameEndedInEarlySurrender=True)

    assert reasons(raw) == ["early_surrender", "too_short"]


def test_legacy_duration_in_milliseconds():
    raw = make_match(gameDuration=1_800_000, gameEndTimestamp=None)
    match, problems = validate_match(raw, TEST_CHAMPION_IDS)

    assert problems == []
    assert match.info.duration_seconds == 1800


def test_patch_of():
    assert patch_of("15.20.712.3456") == "15.20"
