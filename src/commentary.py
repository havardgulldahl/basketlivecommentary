from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, cast

from event_tokens import (
    EventKind,
    FoulSubtype,
    Language,
    MatchSubtype,
    PeriodSubtype,
    ReboundSubtype,
    ShotSubtype,
    TimerSubtype,
    to_enum,
)
from match_metadata import MatchMetadata
from normalizer import NormalizedEvent


class CommentaryGenerator(ABC):
    """
    Common commentary interface for all languages.
    Subclasses override per-event-kind methods.
    """

    silent_kinds = {EventKind.MATCH_DATA}

    def __init__(self, metadata: Optional[MatchMetadata] = None) -> None:
        self.metadata = metadata

    def generate(self, evt: NormalizedEvent) -> Optional[str]:
        kind = to_enum(evt.kind, EventKind)

        print(
            f"[commentary] Generating {self.language_label()} commentary for: "
            f"{evt.kind} - {evt.subtype}"
        )

        if kind is None:
            return None

        if kind in self.silent_kinds:
            return None

        dispatch = {
            EventKind.TIMER: self.comment_timer,
            EventKind.SHOT: self.comment_shot,
            EventKind.REBOUND: self.comment_rebound,
            EventKind.FOUL: self.comment_foul,
            EventKind.TIMEOUT: self.comment_timeout,
            EventKind.TURNOVER: self.comment_turnover,
            EventKind.PERIOD: self.comment_period,
            EventKind.MATCH: self.comment_match,
            EventKind.LINEUP: self.comment_lineup,
        }

        handler = dispatch.get(kind)
        spoken = handler(evt) if handler else None
        score_line = self.score_commentary(evt)
        if score_line:
            spoken = f"{spoken} {score_line}" if spoken else score_line
        return spoken

    def score_commentary(self, evt: NormalizedEvent) -> Optional[str]:
        if (
            evt.home_score is None
            or evt.away_score is None
            or not evt.score_announcement
            and not evt.score_time_announcement
            and not evt.final_summary
        ):
            return None

        home_name = self.team_name("H")
        away_name = self.team_name("A")
        if evt.final_summary:
            return self.final_score_line(
                home_name, away_name, evt.home_score, evt.away_score
            )
        if evt.score_time_announcement:
            raw = cast(dict[str, Any], evt.raw)
            period_name = raw.get("PeriodName") or f"periode {evt.period}"
            # TotalMatchTime is the countdown remaining; PeriodTime counts up (elapsed).
            remaining = raw.get("TotalMatchTime") or evt.clock or "ukjent tid"
            return self.score_time_line(
                home_name,
                away_name,
                evt.home_score,
                evt.away_score,
                period_name,
                str(remaining),
            )
        if evt.home_score == evt.away_score:
            return self.score_tie_line(home_name, away_name, evt.home_score)

        if evt.home_score > evt.away_score:
            leader_name, leader_score = home_name, evt.home_score
            trailing_score = evt.away_score
        else:
            leader_name, leader_score = away_name, evt.away_score
            trailing_score = evt.home_score
        return self.score_lead_line(leader_name, leader_score, trailing_score)

    @abstractmethod
    def score_tie_line(self, home_name: str, away_name: str, score: int) -> str:
        pass

    @abstractmethod
    def score_lead_line(
        self, leader_name: str, leader_score: int, trailing_score: int
    ) -> str:
        pass

    @abstractmethod
    def score_time_line(
        self,
        home_name: str,
        away_name: str,
        home_score: int,
        away_score: int,
        period_name: str,
        remaining: str,
    ) -> str:
        pass

    @abstractmethod
    def final_score_line(
        self, home_name: str, away_name: str, home_score: int, away_score: int
    ) -> str:
        pass

    def player_name(self, player_id: Optional[int]) -> str:
        if self.metadata and player_id:
            player = self.metadata.get_player(player_id)
            if player:
                return player.full_name
        return self.fallback_player_name(player_id)

    def team_name(self, team_code: Optional[str]) -> str:
        if self.metadata and team_code:
            return self.metadata.get_team_name(team_code)
        return self.fallback_team_name(team_code)

    @abstractmethod
    def language_label(self) -> str:
        pass

    @abstractmethod
    def fallback_player_name(self, player_id: Optional[int]) -> str:
        pass

    @abstractmethod
    def fallback_team_name(self, team_code: Optional[str]) -> str:
        pass

    @abstractmethod
    def comment_timer(self, evt: NormalizedEvent) -> Optional[str]:
        pass

    @abstractmethod
    def comment_shot(self, evt: NormalizedEvent) -> Optional[str]:
        pass

    @abstractmethod
    def comment_rebound(self, evt: NormalizedEvent) -> Optional[str]:
        pass

    @abstractmethod
    def comment_foul(self, evt: NormalizedEvent) -> Optional[str]:
        pass

    @abstractmethod
    def comment_timeout(self, evt: NormalizedEvent) -> Optional[str]:
        pass

    @abstractmethod
    def comment_turnover(self, evt: NormalizedEvent) -> Optional[str]:
        pass

    @abstractmethod
    def comment_period(self, evt: NormalizedEvent) -> Optional[str]:
        pass

    @abstractmethod
    def comment_match(self, evt: NormalizedEvent) -> Optional[str]:
        pass

    @abstractmethod
    def comment_lineup(self, evt: NormalizedEvent) -> Optional[str]:
        pass


class NorwegianCommentary(CommentaryGenerator):
    def language_label(self) -> str:
        return "Norwegian"

    def fallback_player_name(self, player_id: Optional[int]) -> str:
        return "ukjent spiller"

    def fallback_team_name(self, team_code: Optional[str]) -> str:
        return {"H": "hjemmelaget", "A": "bortelaget"}.get(team_code, "ukjent lag")

    def score_tie_line(self, home_name: str, away_name: str, score: int) -> str:
        return f"Stillingen er {score}-{score} mellom {home_name} og {away_name}."

    def score_lead_line(
        self, leader_name: str, leader_score: int, trailing_score: int
    ) -> str:
        return f"Stillingen er {leader_score}-{trailing_score}, og {leader_name} leder."

    def score_time_line(
        self,
        home_name: str,
        away_name: str,
        home_score: int,
        away_score: int,
        period_name: str,
        remaining: str,
    ) -> str:
        return (
            f"Stillingen er {home_score}-{away_score}. Det er {remaining} igjen "
            f"av {period_name.lower()}, mellom {home_name} og {away_name}."
        )

    def final_score_line(
        self, home_name: str, away_name: str, home_score: int, away_score: int
    ) -> str:
        if home_score == away_score:
            return f"Kampen er slutt. Det ble uavgjort {home_score}-{away_score} mellom {home_name} og {away_name}."
        winner = home_name if home_score > away_score else away_name
        return f"Kampen er slutt. {winner} vinner {home_score}-{away_score}."

    def comment_timer(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, TimerSubtype)
        mapping = {
            TimerSubtype.STOP: "Ballen er ute av spill",
            TimerSubtype.START: "Og der er klokken igang igjen",
        }
        return mapping.get(subtype)

    def comment_shot(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, ShotSubtype)
        mapping = {
            ShotSubtype.MADE_2P: f"To poeng fra {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ShotSubtype.MADE_3P: f"Tre poeng! {self.player_name(evt.player)} skårer for {self.team_name(evt.team)}.",
            ShotSubtype.MADE_1P: f"Straffekast inne av {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ShotSubtype.PENALTY_MADE_1P: f"Straffekast inne av {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ShotSubtype.MISSED_2P: f"{self.player_name(evt.player)} bommer på topoengeren for {self.team_name(evt.team)}.",
            ShotSubtype.MISSED_3P: f"{self.player_name(evt.player)} bommer på trepoengeren for {self.team_name(evt.team)}.",
            ShotSubtype.MISSED_1P: f"{self.player_name(evt.player)} bommet på straffekastet for {self.team_name(evt.team)}.",
            ShotSubtype.PENALTY_MISS_1P: f"{self.player_name(evt.player)} bommet på straffe for {self.team_name(evt.team)}.",
            ShotSubtype.BLOCKED: f"Blokkert skudd av {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
        }
        return mapping.get(subtype)

    def comment_rebound(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, ReboundSubtype)
        mapping = {
            ReboundSubtype.DEFENSIVE: f"Defensiv retur til {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ReboundSubtype.OFFENSIVE: f"Offensiv retur til {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
        }
        return mapping.get(subtype)

    def comment_foul(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, FoulSubtype)
        mapping = {
            FoulSubtype.PERSONAL: f"Personlig feil på {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.DEFENSIVE: f"Defensiv feil på {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.OFFENSIVE: f"Offensiv feil på {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.TECHNICAL: f"Teknisk feil på {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.UNSPORTSMANLIKE: f"Usportslig feil på {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.FLAGRANT: f"Grov feil på {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.DISQUALIFYING: (
                f"Diskvalifiserende feil! {self.player_name(evt.player)} er ute av kampen."
            ),
            FoulSubtype.TEAM: f"Lagfeil på {self.team_name(evt.team)}.",
            FoulSubtype.SHOOTING: f"Skuddfeil på {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
        }
        return mapping.get(subtype)

    def comment_timeout(self, evt: NormalizedEvent) -> Optional[str]:
        return f"Timeout til {self.team_name(evt.team)}."

    def comment_turnover(self, evt: NormalizedEvent) -> Optional[str]:
        return (
            f"Balltap av {self.player_name(evt.player)} for {self.team_name(evt.team)}."
        )

    def comment_period(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, PeriodSubtype)
        if subtype == PeriodSubtype.PERIOD_START:
            return f"Periode {evt.period} er i gang."
        if subtype == PeriodSubtype.END:
            return f"Slutt på periode {evt.period}."
        return None

    def comment_match(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, MatchSubtype)
        if subtype == MatchSubtype.END:
            return None
        return None

    def comment_lineup(self, evt: NormalizedEvent) -> Optional[str]:
        changes = evt.lineup_changes or {}
        added = ", ".join(changes.get("added", []))
        removed = ", ".join(changes.get("removed", []))
        team = self.team_name(evt.team)
        if added and removed:
            return f"Bytte for {team}: {added} inn, {removed} ut."
        if added:
            return f"{added} kommer inn for {team}."
        if removed:
            return f"{removed} går ut for {team}."
        return None


class EnglishCommentary(CommentaryGenerator):
    def language_label(self) -> str:
        return "English"

    def fallback_player_name(self, player_id: Optional[int]) -> str:
        return "unknown player"

    def fallback_team_name(self, team_code: Optional[str]) -> str:
        return {"H": "the home team", "A": "the away team"}.get(
            team_code, "unknown team"
        )

    def score_tie_line(self, home_name: str, away_name: str, score: int) -> str:
        return f"The score is {score}-{score} between {home_name} and {away_name}."

    def score_lead_line(
        self, leader_name: str, leader_score: int, trailing_score: int
    ) -> str:
        return f"The score is {leader_score}-{trailing_score}, with {leader_name} in front."

    def score_time_line(
        self,
        home_name: str,
        away_name: str,
        home_score: int,
        away_score: int,
        period_name: str,
        remaining: str,
    ) -> str:
        return (
            f"The score is {home_score}-{away_score}, with {remaining} remaining "
            f"in the {period_name.lower()}, between {home_name} and {away_name}."
        )

    def final_score_line(
        self, home_name: str, away_name: str, home_score: int, away_score: int
    ) -> str:
        if home_score == away_score:
            return f"The game is over. It finished tied {home_score}-{away_score} between {home_name} and {away_name}."
        winner = home_name if home_score > away_score else away_name
        return f"The game is over. {winner} win {home_score}-{away_score}."

    def comment_timer(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, TimerSubtype)
        mapping = {
            TimerSubtype.STOP: "The ball is out of play",
            TimerSubtype.START: "And the clock is running again",
        }
        return mapping.get(subtype)

    def comment_shot(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, ShotSubtype)
        mapping = {
            ShotSubtype.MADE_2P: f"Two points from {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ShotSubtype.MADE_3P: f"Three points! {self.player_name(evt.player)} scores for {self.team_name(evt.team)}.",
            ShotSubtype.MADE_1P: f"Free throw made by {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ShotSubtype.PENALTY_MADE_1P: f"Free throw made by {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ShotSubtype.MISSED_2P: f"Missed two-pointer by {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ShotSubtype.MISSED_3P: f"Three-point attempt misses by {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ShotSubtype.MISSED_1P: f"{self.player_name(evt.player)} misses the free throw for {self.team_name(evt.team)}.",
            ShotSubtype.PENALTY_MISS_1P: f"{self.player_name(evt.player)} missed the free throw for {self.team_name(evt.team)}.",
            ShotSubtype.BLOCKED: f"Shot blocked by {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
        }
        return mapping.get(subtype)

    def comment_rebound(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, ReboundSubtype)
        mapping = {
            ReboundSubtype.DEFENSIVE: f"Defensive rebound to {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            ReboundSubtype.OFFENSIVE: f"Offensive rebound to {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
        }
        return mapping.get(subtype)

    def comment_foul(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, FoulSubtype)
        mapping = {
            FoulSubtype.PERSONAL: f"Personal foul on {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.DEFENSIVE: f"Defensive foul on {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.OFFENSIVE: f"Offensive foul on {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.TECHNICAL: f"Technical foul on {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.UNSPORTSMANLIKE: f"Unsportsmanlike foul on {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.FLAGRANT: f"Flagrant foul on {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
            FoulSubtype.DISQUALIFYING: (
                f"Disqualifying foul! {self.player_name(evt.player)} is ejected from the game."
            ),
            FoulSubtype.TEAM: f"Team foul on {self.team_name(evt.team)}.",
            FoulSubtype.SHOOTING: f"Shooting foul on {self.player_name(evt.player)} for {self.team_name(evt.team)}.",
        }
        return mapping.get(subtype)

    def comment_timeout(self, evt: NormalizedEvent) -> Optional[str]:
        return f"Timeout called by {self.team_name(evt.team)}."

    def comment_turnover(self, evt: NormalizedEvent) -> Optional[str]:
        return f"Turnover by {self.player_name(evt.player)} for {self.team_name(evt.team)}."

    def comment_period(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, PeriodSubtype)
        if subtype == PeriodSubtype.PERIOD_START:
            return f"Period {evt.period} is underway."
        if subtype == PeriodSubtype.END:
            return f"End of period {evt.period}."
        return None

    def comment_match(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, MatchSubtype)
        if subtype == MatchSubtype.END:
            return None
        return None

    def comment_lineup(self, evt: NormalizedEvent) -> Optional[str]:
        changes = evt.lineup_changes or {}
        added = ", ".join(changes.get("added", []))
        removed = ", ".join(changes.get("removed", []))
        team = self.team_name(evt.team)
        if added and removed:
            return f"Change for {team}: {added} in, {removed} out."
        if added:
            return f"{added} comes in for {team}."
        if removed:
            return f"{removed} comes off for {team}."
        return None


def get_commentary(
    evt: NormalizedEvent,
    metadata: Optional[MatchMetadata] = None,
    language: str = Language.NO.value,
) -> Optional[str]:
    """
    Commentary factory.
    """
    lang = to_enum((language or Language.NO.value).lower(), Language)

    generator: CommentaryGenerator
    if lang == Language.EN:
        generator = EnglishCommentary(metadata)
    else:
        generator = NorwegianCommentary(metadata)

    return generator.generate(evt)


def get_score_commentary(
    evt: NormalizedEvent,
    metadata: Optional[MatchMetadata] = None,
    language: str = Language.NO.value,
) -> Optional[str]:
    lang = to_enum((language or Language.NO.value).lower(), Language)
    generator = (
        EnglishCommentary(metadata)
        if lang == Language.EN
        else NorwegianCommentary(metadata)
    )
    if evt.score_announcement or evt.score_time_announcement or evt.final_summary:
        return generator.score_commentary(evt)
    return None
