"""List recorded games and build summaries from completed event logs."""

import json
from dataclasses import dataclass
from pathlib import Path

from game_summary import GameSummary
from match_metadata import MatchMetadata
from normalizer import GeniusBasketballNormalizer


@dataclass
class RecordedGame:
    """A game with cached metadata and its locally recorded state."""

    directory: Path
    metadata: MatchMetadata
    complete: bool

    @property
    def summary_path(self) -> Path:
        """Return the expected Markdown summary path."""
        return self.directory / "summary.md"


def load_recorded_games(matchdata_dir: Path) -> list[RecordedGame]:
    """Load games that have cached metadata, ordered by match date and ID."""
    games = [
        _load_recorded_game(metadata_path)
        for metadata_path in matchdata_dir.glob("*/metadata.json")
    ]
    return sorted(
        games,
        key=lambda game: (game.metadata.match_date, game.metadata.match_id),
    )


def generate_missing_summary(game: RecordedGame) -> bool:
    """Generate a missing summary when the logs include the match end."""
    if game.summary_path.exists() or not game.complete:
        return False

    summary, complete = _read_game_events(game.directory)
    if not complete:
        return False
    summary.write(game.summary_path, game.metadata)
    return True


def print_game_overview(
    games: list[RecordedGame],
    generate_missing: bool = False,
) -> None:
    """Print completion and summary status for recorded games."""
    generated: set[int] = set()
    if generate_missing:
        for game in games:
            if generate_missing_summary(game):
                generated.add(game.metadata.match_id)

    headers = ("MATCH", "DATE", "STATUS", "SUMMARY", "TEAMS")
    rows = []
    for game in games:
        metadata = game.metadata
        summary_status = "available" if game.summary_path.exists() else "missing"
        if metadata.match_id in generated:
            summary_status = "generated"
        rows.append(
            (
                str(metadata.match_id),
                metadata.match_date[:10] or "-",
                "complete" if game.complete else "incomplete",
                summary_status,
                _truncate(
                    f"{metadata.home_team_name.strip()} - "
                    f"{metadata.away_team_name.strip()}",
                    35,
                ),
            )
        )

    if not rows:
        print(f"No games with metadata found in {matchdata_dir_display()}")
        return

    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print(_format_row(headers, widths))
    print(_format_row(tuple("-" * width for width in widths), widths))
    for row in rows:
        print(_format_row(row, widths))


def matchdata_dir_display() -> str:
    """Return the default match data directory for user-facing messages."""
    return "matchdata"


def _load_recorded_game(metadata_path: Path) -> RecordedGame:
    raw_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata = MatchMetadata.from_raw(raw_metadata)
    _, complete = _read_game_events(metadata_path.parent, collect=False)
    return RecordedGame(metadata_path.parent, metadata, complete)


def _read_game_events(
    game_dir: Path,
    collect: bool = True,
) -> tuple[GameSummary, bool]:
    normalizer = GeniusBasketballNormalizer()
    summary = GameSummary()
    complete = False

    for log_path in sorted(game_dir.glob("raw_events_*.jsonl")):
        with log_path.open(encoding="utf-8") as log_file:
            for line_number, line in enumerate(log_file, 1):
                if not line.strip():
                    continue
                try:
                    raw_event = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSON in {log_path}:{line_number}"
                    ) from error
                event = normalizer.normalize(raw_event)
                if event is None:
                    continue
                if collect:
                    summary.update(event)
                if event.kind == "match" and event.subtype == "end":
                    complete = True

    return summary, complete


def _format_row(row: tuple[str, ...], widths: list[int]) -> str:
    return "  ".join(
        value.ljust(widths[index]) for index, value in enumerate(row)
    ).rstrip()


def _truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return value[: width - 3] + "..."
