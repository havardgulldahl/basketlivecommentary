# commentary.py
from abc import ABC, abstractmethod
from normalizer import NormalizedEvent
from match_metadata import MatchMetadata
from typing import Optional


class BaseCommentary(ABC):
    """
    Abstract base class for language-specific commentary generators.

    Subclasses override one method per event type to provide
    language-specific commentary strings.
    """

    def comment(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata] = None
    ) -> Optional[str]:
        """
        Generate commentary for a normalized event by dispatching to the
        appropriate per-event method.

        Returns:
            Commentary string, or None if the event should be silent.
        """
        print(
            f"[commentary] Generating {self.__class__.__name__} commentary for:"
            f" {evt.kind} - {evt.subtype}"
        )

        if evt.kind in ("match_data",):
            return None

        if evt.kind == "timer":
            return self.timer(evt, metadata)
        if evt.kind == "shot":
            return self.shot(evt, metadata)
        if evt.kind == "rebound":
            return self.rebound(evt, metadata)
        if evt.kind == "foul":
            return self.foul(evt, metadata)
        if evt.kind == "timeout":
            return self.timeout(evt, metadata)
        if evt.kind == "turnover":
            return self.turnover(evt, metadata)
        if evt.kind == "period":
            return self.period(evt, metadata)
        if evt.kind == "match":
            return self.match(evt, metadata)

        return None

    # ------------------------------------------------------------------
    # Helpers (shared across all languages)
    # ------------------------------------------------------------------

    def _player_name(
        self, player_id: Optional[int], metadata: Optional[MatchMetadata]
    ) -> str:
        if metadata and player_id:
            return metadata.get_player_name(player_id)
        return self._unknown_player(player_id)

    def _team_name(
        self, team_code: Optional[str], metadata: Optional[MatchMetadata]
    ) -> str:
        if metadata and team_code:
            return metadata.get_team_name(team_code)
        return self._unknown_team(team_code)

    # ------------------------------------------------------------------
    # Fallback labels – override in subclasses if needed
    # ------------------------------------------------------------------

    def _unknown_player(self, player_id: Optional[int]) -> str:
        return f"player {player_id}" if player_id else "unknown player"

    def _unknown_team(self, team_code: Optional[str]) -> str:
        return f"team {team_code}" if team_code else "unknown team"

    # ------------------------------------------------------------------
    # Per-event abstract methods
    # ------------------------------------------------------------------

    @abstractmethod
    def timer(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        """Commentary for timer start/stop events."""

    @abstractmethod
    def shot(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        """Commentary for shot events."""

    @abstractmethod
    def rebound(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        """Commentary for rebound events."""

    @abstractmethod
    def foul(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        """Commentary for foul events."""

    @abstractmethod
    def timeout(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        """Commentary for timeout events."""

    @abstractmethod
    def turnover(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        """Commentary for turnover events."""

    @abstractmethod
    def period(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        """Commentary for period start/end events."""

    @abstractmethod
    def match(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        """Commentary for match-level events."""


class NorwegianCommentary(BaseCommentary):
    """Norwegian-language commentary."""

    def _unknown_player(self, player_id: Optional[int]) -> str:
        return f"spiller {player_id}" if player_id else "ukjent spiller"

    def _unknown_team(self, team_code: Optional[str]) -> str:
        return f"lag {team_code}" if team_code else "ukjent lag"

    def timer(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        if evt.subtype == "stop":
            return "Ballen er ute av spill"
        if evt.subtype == "start":
            return "Og der er klokken igang igjen"
        return None

    def shot(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        p = self._player_name(evt.player, metadata)
        if evt.subtype == "made_2p":
            return f"To poeng fra {p}."
        if evt.subtype == "made_3p":
            return f"Tre poeng! {p} skårer fra distanse."
        if evt.subtype == "made_1p":
            return f"Straffekast inne av {p}."
        if evt.subtype == "missed_2p":
            return f"Bom på topoenger av {p}."
        if evt.subtype == "missed_3p":
            return f"Trepoengsforsøk bom av {p}."
        if evt.subtype == "penalty_miss_1p":
            return f"{p} bommet på straffe."
        if evt.subtype == "blocked":
            return f"Blokkert skudd av {p}."
        return None

    def rebound(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        p = self._player_name(evt.player, metadata)
        if evt.subtype == "defensive":
            return f"Defensiv retur til {p}."
        if evt.subtype == "offensive":
            return f"Offensiv retur til {p}."
        return None

    def foul(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        p = self._player_name(evt.player, metadata)
        t = self._team_name(evt.team, metadata)
        if evt.subtype == "personal":
            return f"Personlig feil på {p}."
        if evt.subtype == "defensive":
            return f"Defensiv feil på {p}."
        if evt.subtype == "offensive":
            return f"Offensiv feil på {p}."
        if evt.subtype == "technical":
            return f"Teknisk feil på {p}."
        if evt.subtype == "unsportsmanlike":
            return f"Usportslig feil på {p}."
        if evt.subtype == "disqualifying":
            return f"Diskvalifiserende feil! {p} er ute av kampen."
        if evt.subtype == "team":
            return f"Lagfeil på {t}."
        if evt.subtype == "shooting":
            return f"Skuddfeil på {p}."
        return None

    def timeout(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        return f"Timeout til {self._team_name(evt.team, metadata)}."

    def turnover(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        return f"Balltap av {self._player_name(evt.player, metadata)}."

    def period(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        if evt.subtype == "period_start":
            return f"Periode {evt.period} er i gang."
        if evt.subtype == "end":
            return f"Slutt på periode {evt.period}."
        return None

    def match(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        if evt.subtype == "end":
            return "Kampen er slutt!"
        return None


class EnglishCommentary(BaseCommentary):
    """English-language commentary."""

    def timer(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        if evt.subtype == "stop":
            return "The ball is out of play"
        if evt.subtype == "start":
            return "And the clock is running again"
        return None

    def shot(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        p = self._player_name(evt.player, metadata)
        if evt.subtype == "made_2p":
            return f"Two points from {p}."
        if evt.subtype == "made_3p":
            return f"Three points! {p} scores from downtown."
        if evt.subtype == "made_1p":
            return f"Free throw made by {p}."
        if evt.subtype == "missed_2p":
            return f"Missed two-pointer by {p}."
        if evt.subtype == "missed_3p":
            return f"Three-point attempt misses by {p}."
        if evt.subtype == "penalty_miss_1p":
            return f"{p} missed the free throw."
        if evt.subtype == "blocked":
            return f"Shot blocked by {p}."
        return None

    def rebound(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        p = self._player_name(evt.player, metadata)
        if evt.subtype == "defensive":
            return f"Defensive rebound to {p}."
        if evt.subtype == "offensive":
            return f"Offensive rebound to {p}."
        return None

    def foul(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        p = self._player_name(evt.player, metadata)
        t = self._team_name(evt.team, metadata)
        if evt.subtype == "personal":
            return f"Personal foul on {p}."
        if evt.subtype == "defensive":
            return f"Defensive foul on {p}."
        if evt.subtype == "offensive":
            return f"Offensive foul on {p}."
        if evt.subtype == "technical":
            return f"Technical foul on {p}."
        if evt.subtype == "unsportsmanlike":
            return f"Unsportsmanlike foul on {p}."
        if evt.subtype == "disqualifying":
            return f"Disqualifying foul! {p} is ejected from the game."
        if evt.subtype == "team":
            return f"Team foul on {t}."
        if evt.subtype == "shooting":
            return f"Shooting foul on {p}."
        return None

    def timeout(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        return f"Timeout called by {self._team_name(evt.team, metadata)}."

    def turnover(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        return f"Turnover by {self._player_name(evt.player, metadata)}."

    def period(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        if evt.subtype == "period_start":
            return f"Period {evt.period} is underway."
        if evt.subtype == "end":
            return f"End of period {evt.period}."
        return None

    def match(self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]) -> Optional[str]:
        if evt.subtype == "end":
            return "That's the final buzzer! Game over!"
        return None


_COMMENTATORS: dict[str, BaseCommentary] = {
    "no": NorwegianCommentary(),
    "en": EnglishCommentary(),
}


def get_commentary(
    evt: NormalizedEvent,
    metadata: Optional[MatchMetadata] = None,
    language: str = "no",
) -> Optional[str]:
    """
    Factory that returns language-appropriate commentary for a normalized event.

    Args:
        evt: The normalized event
        metadata: Optional match metadata for player/team names
        language: Language code ("no" for Norwegian, "en" for English)

    Returns:
        Commentary string, or None if event should be silent
    """
    commentator = _COMMENTATORS.get(language, _COMMENTATORS["no"])
    return commentator.comment(evt, metadata)
