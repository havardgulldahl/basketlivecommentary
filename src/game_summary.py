from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from match_metadata import MatchMetadata
from normalizer import NormalizedEvent


@dataclass
class Stats:
    """Box-score statistics for one player, team, or period."""

    points: int = 0
    field_goals_made: int = 0
    field_goals_attempted: int = 0
    three_points_made: int = 0
    three_points_attempted: int = 0
    free_throws_made: int = 0
    free_throws_attempted: int = 0
    offensive_rebounds: int = 0
    defensive_rebounds: int = 0
    assists: int = 0
    steals: int = 0
    blocks: int = 0
    turnovers: int = 0
    fouls: int = 0

    @property
    def rebounds(self) -> int:
        """Return total rebounds."""
        return self.offensive_rebounds + self.defensive_rebounds


class GameSummary:
    """Collect corrected feed events and produce a Markdown box score."""

    def __init__(self) -> None:
        self.events: dict[str, NormalizedEvent] = {}

    def update(self, event: NormalizedEvent) -> None:
        """Store the latest version of an event."""
        self.events[event.fingerprint] = event

    def write(self, path: Path, metadata: MatchMetadata) -> None:
        """Write the current game summary to a Markdown file."""
        path.write_text(self.render(metadata), encoding="utf-8")

    def render(self, metadata: MatchMetadata) -> str:
        """Render a Markdown summary of the final game statistics."""
        team_stats, player_stats, period_stats = self._aggregate()
        home_name = metadata.home_team_name.strip()
        away_name = metadata.away_team_name.strip()
        home = team_stats["H"]
        away = team_stats["A"]
        winner = self._winner(home_name, away_name, home.points, away.points)

        lines = [
            f"# {home_name} {home.points}-{away.points} {away_name}",
            "",
            f"**Result:** {winner}",
            "",
            "## Period summary",
            "",
            "| Period | Score | Winner | FG | 3P | FT | REB | TO |",
            "|---:|:---:|:---|:---:|:---:|:---:|---:|---:|",
        ]
        periods = sorted(period_stats)
        for period in periods:
            home_period = period_stats[period]["H"]
            away_period = period_stats[period]["A"]
            period_winner = self._winner(
                home_name,
                away_name,
                home_period.points,
                away_period.points,
                tied="Tied",
            )
            lines.append(
                f"| {period} | {home_period.points}-{away_period.points} "
                f"| {period_winner} | "
                f"{self._attempts(home_period, away_period, 'field_goal')} | "
                f"{self._attempts(home_period, away_period, 'three_point')} | "
                f"{self._attempts(home_period, away_period, 'free_throw')} | "
                f"{home_period.rebounds}-{away_period.rebounds} | "
                f"{home_period.turnovers}-{away_period.turnovers} |"
            )

        lines.extend(
            [
                "",
                f"Scores and paired statistics are shown as "
                f"{home_name}-{away_name}.",
                "",
                "## Player stats",
                "",
            ]
        )
        for team, players in (
            ("H", metadata.home_players),
            ("A", metadata.away_players),
        ):
            lines.extend(
                [
                    f"### {home_name if team == 'H' else away_name}",
                    "",
                    "| Player | PTS | FG | 3P | FT | REB | OREB | AST | "
                    "STL | BLK | TO | PF |",
                    "|:---|---:|:---:|:---:|:---:|---:|---:|---:|---:|"
                    "---:|---:|---:|",
                ]
            )
            rows = []
            for player in players:
                stats = player_stats.get(player.id)
                if stats is None:
                    continue
                rows.append((stats.points, player.shirt_no or 999, player, stats))
            for _, _, player, stats in sorted(
                rows, reverse=True, key=lambda row: row[:2]
            ):
                lines.append(
                    f"| {player.display_name} | {stats.points} | "
                    f"{self._made_attempted(stats, 'field_goal')} | "
                    f"{self._made_attempted(stats, 'three_point')} | "
                    f"{self._made_attempted(stats, 'free_throw')} | "
                    f"{stats.rebounds} | {stats.offensive_rebounds} | "
                    f"{stats.assists} | {stats.steals} | {stats.blocks} | "
                    f"{stats.turnovers} | {stats.fouls} |"
                )
            if not rows:
                lines.append(
                    "| No recorded player events | 0 | 0/0 | 0/0 | "
                    "0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |"
                )
            lines.append("")

        lines.extend(self._best_periods(period_stats, metadata))
        lines.extend(self._advanced_stats(team_stats, metadata))
        lines.extend(
            [
                "## Team totals",
                "",
                "| Team | PTS | FG | FG% | 3P | 3P% | FT | FT% | REB | "
                "AST | STL | BLK | TO | PF |",
                "|:---|---:|:---:|---:|:---:|---:|:---:|---:|---:|---:|"
                "---:|---:|---:|---:|---:|",
            ]
        )
        for team, name in (("H", home_name), ("A", away_name)):
            stats = team_stats[team]
            lines.append(
                f"| {name} | {stats.points} | "
                f"{self._made_attempted(stats, 'field_goal')} | "
                f"{self._percent(stats.field_goals_made, stats.field_goals_attempted)} "
                f"| {self._made_attempted(stats, 'three_point')} | "
                f"{self._percent(stats.three_points_made, stats.three_points_attempted)} "
                f"| {self._made_attempted(stats, 'free_throw')} | "
                f"{self._percent(stats.free_throws_made, stats.free_throws_attempted)} "
                f"| {stats.rebounds} | {stats.assists} | {stats.steals} | "
                f"{stats.blocks} | {stats.turnovers} | {stats.fouls} |"
            )
        return "\n".join(lines) + "\n"

    def _aggregate(
        self,
    ) -> tuple[
        dict[str, Stats],
        dict[int, Stats],
        dict[int, dict[str, Stats]],
    ]:
        team_stats = defaultdict(Stats)
        player_stats = defaultdict(Stats)
        period_stats: dict[int, dict[str, Stats]] = defaultdict(
            lambda: defaultdict(Stats)
        )
        for event in self.events.values():
            if event.team not in {"H", "A"}:
                continue
            targets = [team_stats[event.team]]
            if event.period is not None:
                targets.append(period_stats[event.period][event.team])
            if isinstance(event.player, int):
                targets.append(player_stats[event.player])
            self._add_event(targets, event)
            if event.points and isinstance(event.assist, int):
                player_stats[event.assist].assists += 1
                team_stats[event.team].assists += 1
                if event.period is not None:
                    period_stats[event.period][event.team].assists += 1
        return team_stats, player_stats, period_stats

    @staticmethod
    def _add_event(targets: list[Stats], event: NormalizedEvent) -> None:
        subtype = event.subtype or ""
        for stats in targets:
            if event.kind == "shot":
                if subtype.endswith("1p"):
                    stats.free_throws_attempted += 1
                    if event.points == 1:
                        stats.free_throws_made += 1
                        stats.points += 1
                elif subtype.endswith(("2p", "3p")):
                    stats.field_goals_attempted += 1
                    if subtype.endswith("3p"):
                        stats.three_points_attempted += 1
                    if event.points in {2, 3}:
                        stats.field_goals_made += 1
                        stats.points += event.points
                        if event.points == 3:
                            stats.three_points_made += 1
            elif event.kind == "rebound":
                if event.subtype == "offensive":
                    stats.offensive_rebounds += 1
                else:
                    stats.defensive_rebounds += 1
            elif event.kind == "steal":
                stats.steals += 1
            elif event.kind == "block":
                stats.blocks += 1
            elif event.kind == "turnover":
                stats.turnovers += 1
            elif event.kind == "foul":
                stats.fouls += 1

    def _best_periods(
        self,
        periods: dict[int, dict[str, Stats]],
        metadata: MatchMetadata,
    ) -> list[str]:
        lines = ["## Best periods", ""]
        for team, opponent in (("H", "A"), ("A", "H")):
            name = (
                metadata.home_team_name if team == "H" else metadata.away_team_name
            ).strip()
            if not periods:
                lines.append(f"- **{name}:** No period data.")
                continue
            best = max(
                periods,
                key=lambda period: (
                    periods[period][team].points - periods[period][opponent].points,
                    periods[period][team].points,
                ),
            )
            own = periods[best][team].points
            other = periods[best][opponent].points
            lines.append(
                f"- **{name}:** Period {best}, {own}-{other} "
                f"({own - other:+d} point differential)."
            )
        return lines + [""]

    def _advanced_stats(
        self,
        teams: dict[str, Stats],
        metadata: MatchMetadata,
    ) -> list[str]:
        lines = [
            "## Stats nerd corner",
            "",
            "| Team | eFG% | TS% | AST/TO | Est. possessions | Off. rating |",
            "|:---|---:|---:|---:|---:|---:|",
        ]
        for team, name in (
            ("H", metadata.home_team_name.strip()),
            ("A", metadata.away_team_name.strip()),
        ):
            stats = teams[team]
            effective = self._ratio(
                stats.field_goals_made + 0.5 * stats.three_points_made,
                stats.field_goals_attempted,
                percent=True,
            )
            true_shooting = self._ratio(
                stats.points,
                2 * (stats.field_goals_attempted + 0.44 * stats.free_throws_attempted),
                percent=True,
            )
            assist_turnover = self._ratio(stats.assists, stats.turnovers)
            possessions = (
                stats.field_goals_attempted
                + 0.44 * stats.free_throws_attempted
                - stats.offensive_rebounds
                + stats.turnovers
            )
            rating = self._ratio(stats.points * 100, possessions)
            lines.append(
                f"| {name} | {effective} | {true_shooting} | "
                f"{assist_turnover} | {possessions:.1f} | {rating} |"
            )
        lines.extend(
            [
                "",
                "Estimated possessions use FGA + 0.44 x FTA - OREB + TO. "
                "Offensive rating is points per 100 estimated possessions.",
                "",
            ]
        )
        return lines

    @staticmethod
    def _winner(
        home_name: str,
        away_name: str,
        home_points: int,
        away_points: int,
        tied: str = "Draw",
    ) -> str:
        if home_points > away_points:
            return home_name
        if away_points > home_points:
            return away_name
        return tied

    @staticmethod
    def _made_attempted(stats: Stats, prefix: str) -> str:
        made = getattr(stats, f"{prefix}s_made")
        attempted = getattr(stats, f"{prefix}s_attempted")
        return f"{made}/{attempted}"

    def _attempts(
        self,
        home: Stats,
        away: Stats,
        prefix: str,
    ) -> str:
        return (
            f"{self._made_attempted(home, prefix)}-"
            f"{self._made_attempted(away, prefix)}"
        )

    @staticmethod
    def _percent(made: int, attempted: int) -> str:
        return f"{100 * made / attempted:.1f}%" if attempted else "-"

    @staticmethod
    def _ratio(
        numerator: float,
        denominator: float,
        percent: bool = False,
    ) -> str:
        if not denominator:
            return "-"
        value = numerator / denominator
        return f"{value * 100:.1f}%" if percent else f"{value:.1f}"
