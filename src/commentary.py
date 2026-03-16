from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

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
        }

        handler = dispatch.get(kind)
        return handler(evt) if handler else None

    def player_name(self, player_id: Optional[int]) -> str:
        if self.metadata and player_id:
            return self.metadata.get_player_name(player_id)
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


class NorwegianCommentary(CommentaryGenerator):
    def language_label(self) -> str:
        return "Norwegian"

    def fallback_player_name(self, player_id: Optional[int]) -> str:
        return f"spiller {player_id}" if player_id else "ukjent spiller"

    def fallback_team_name(self, team_code: Optional[str]) -> str:
        return f"lag {team_code}" if team_code else "ukjent lag"

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
            ShotSubtype.MADE_2P: f"To poeng fra {self.player_name(evt.player)}.",
            ShotSubtype.MADE_3P: f"Tre poeng! {self.player_name(evt.player)} skårer fra distanse.",
            ShotSubtype.MADE_1P: f"Straffekast inne av {self.player_name(evt.player)}.",
            ShotSubtype.PENALTY_MADE_1P: f"Straffekast inne av {self.player_name(evt.player)}.",
            ShotSubtype.MISSED_2P: f"Bom på topoenger av {self.player_name(evt.player)}.",
            ShotSubtype.MISSED_3P: f"Trepoengsforsøk bom av {self.player_name(evt.player)}.",
            ShotSubtype.MISSED_1P: f"{self.player_name(evt.player)} bommet på straffekastet.",
            ShotSubtype.PENALTY_MISS_1P: f"{self.player_name(evt.player)} bommet på straffe.",
            ShotSubtype.BLOCKED: f"Blokkert skudd av {self.player_name(evt.player)}.",
        }
        return mapping.get(subtype)

    def comment_rebound(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, ReboundSubtype)
        mapping = {
            ReboundSubtype.DEFENSIVE: f"Defensiv retur til {self.player_name(evt.player)}.",
            ReboundSubtype.OFFENSIVE: f"Offensiv retur til {self.player_name(evt.player)}.",
        }
        return mapping.get(subtype)

    def comment_foul(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, FoulSubtype)
        mapping = {
            FoulSubtype.PERSONAL: f"Personlig feil på {self.player_name(evt.player)}.",
            FoulSubtype.DEFENSIVE: f"Defensiv feil på {self.player_name(evt.player)}.",
            FoulSubtype.OFFENSIVE: f"Offensiv feil på {self.player_name(evt.player)}.",
            FoulSubtype.TECHNICAL: f"Teknisk feil på {self.player_name(evt.player)}.",
            FoulSubtype.UNSPORTSMANLIKE: f"Usportslig feil på {self.player_name(evt.player)}.",
            FoulSubtype.FLAGRANT: f"Grov feil på {self.player_name(evt.player)}.",
            FoulSubtype.DISQUALIFYING: (
                f"Diskvalifiserende feil! {self.player_name(evt.player)} er ute av kampen."
            ),
            FoulSubtype.TEAM: f"Lagfeil på {self.team_name(evt.team)}.",
            FoulSubtype.SHOOTING: f"Skuddfeil på {self.player_name(evt.player)}.",
        }
        return mapping.get(subtype)

    def comment_timeout(self, evt: NormalizedEvent) -> Optional[str]:
        return f"Timeout til {self.team_name(evt.team)}."

    def comment_turnover(self, evt: NormalizedEvent) -> Optional[str]:
        return f"Balltap av {self.player_name(evt.player)}."

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
            return "Kampen er slutt!"
        return None


class EnglishCommentary(CommentaryGenerator):
    def language_label(self) -> str:
        return "English"

    def fallback_player_name(self, player_id: Optional[int]) -> str:
        return f"player {player_id}" if player_id else "unknown player"

    def fallback_team_name(self, team_code: Optional[str]) -> str:
        return f"team {team_code}" if team_code else "unknown team"

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
            ShotSubtype.MADE_2P: f"Two points from {self.player_name(evt.player)}.",
            ShotSubtype.MADE_3P: f"Three points! {self.player_name(evt.player)} scores from downtown.",
            ShotSubtype.MADE_1P: f"Free throw made by {self.player_name(evt.player)}.",
            ShotSubtype.PENALTY_MADE_1P: f"Free throw made by {self.player_name(evt.player)}.",
            ShotSubtype.MISSED_2P: f"Missed two-pointer by {self.player_name(evt.player)}.",
            ShotSubtype.MISSED_3P: f"Three-point attempt misses by {self.player_name(evt.player)}.",
            ShotSubtype.MISSED_1P: f"{self.player_name(evt.player)} misses the free throw.",
            ShotSubtype.PENALTY_MISS_1P: f"{self.player_name(evt.player)} missed the free throw.",
            ShotSubtype.BLOCKED: f"Shot blocked by {self.player_name(evt.player)}.",
        }
        return mapping.get(subtype)

    def comment_rebound(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, ReboundSubtype)
        mapping = {
            ReboundSubtype.DEFENSIVE: f"Defensive rebound to {self.player_name(evt.player)}.",
            ReboundSubtype.OFFENSIVE: f"Offensive rebound to {self.player_name(evt.player)}.",
        }
        return mapping.get(subtype)

    def comment_foul(self, evt: NormalizedEvent) -> Optional[str]:
        subtype = to_enum(evt.subtype, FoulSubtype)
        mapping = {
            FoulSubtype.PERSONAL: f"Personal foul on {self.player_name(evt.player)}.",
            FoulSubtype.DEFENSIVE: f"Defensive foul on {self.player_name(evt.player)}.",
            FoulSubtype.OFFENSIVE: f"Offensive foul on {self.player_name(evt.player)}.",
            FoulSubtype.TECHNICAL: f"Technical foul on {self.player_name(evt.player)}.",
            FoulSubtype.UNSPORTSMANLIKE: f"Unsportsmanlike foul on {self.player_name(evt.player)}.",
            FoulSubtype.FLAGRANT: f"Flagrant foul on {self.player_name(evt.player)}.",
            FoulSubtype.DISQUALIFYING: (
                f"Disqualifying foul! {self.player_name(evt.player)} is ejected from the game."
            ),
            FoulSubtype.TEAM: f"Team foul on {self.team_name(evt.team)}.",
            FoulSubtype.SHOOTING: f"Shooting foul on {self.player_name(evt.player)}.",
        }
        return mapping.get(subtype)

    def comment_timeout(self, evt: NormalizedEvent) -> Optional[str]:
        return f"Timeout called by {self.team_name(evt.team)}."

    def comment_turnover(self, evt: NormalizedEvent) -> Optional[str]:
        return f"Turnover by {self.player_name(evt.player)}."

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
            return "That's the final buzzer! Game over!"
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
