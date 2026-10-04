"""The App and the integration ship identical copies of the season calendar."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDIO = ROOT / "app/src/sound_effects_studio/seasons.py"
INTEGRATION = ROOT / "custom_components/sound_effects/seasons.py"
FUNCTIONS = ("class SeasonLike", "def season_matches", "def resolve_calendar_season")


def _calendar_block(path: Path) -> list[str]:
    """Return the non-blank lines from SeasonLike through resolve_calendar_season."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(FUNCTIONS[0]))
    end = next(i for i, line in enumerate(lines) if line.startswith(FUNCTIONS[-1]))
    stop = next(
        (i for i in range(end + 1, len(lines)) if lines[i] and not lines[i][0].isspace()),
        len(lines),
    )
    return [line for line in lines[start:stop] if line.strip()]


def test_calendar_copies_are_identical() -> None:
    assert _calendar_block(STUDIO) == _calendar_block(INTEGRATION)


def test_both_copies_define_regular() -> None:
    for path in (STUDIO, INTEGRATION):
        assert 'REGULAR = "regular"' in path.read_text(encoding="utf-8")
