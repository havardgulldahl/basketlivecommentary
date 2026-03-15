# commentary.py
from normalizer import NormalizedEvent
from match_metadata import MatchMetadata
from typing import Optional


def get_commentary(
    evt: NormalizedEvent, metadata: Optional[MatchMetadata] = None, language: str = "no"
) -> Optional[str]:
    """
    Generate commentary for a normalized event.

    Args:
        evt: The normalized event
        metadata: Optional match metadata for player/team names
        language: Language code ("no" for Norwegian, "en" for English)

    Returns:
        Commentary string, or None if event should be silent
    """
    if language == "en":
        return english_commentary(evt, metadata)
    else:
        return norwegian_commentary(evt, metadata)


def norwegian_commentary(
    evt: NormalizedEvent, metadata: Optional[MatchMetadata] = None
) -> Optional[str]:
    """
    Generate Norwegian commentary for a normalized event.

    Args:
        evt: The normalized event
        metadata: Optional match metadata for player/team names

    Returns:
        Norwegian commentary string, or None if event should be silent
    """

    print(
        f"[commentary] Generating Norwegian commentary for: {evt.kind} - {evt.subtype}"
    )

    # Helper to get player name
    def player_name(player_id: Optional[int]) -> str:
        if metadata and player_id:
            return metadata.get_player_name(player_id)
        return f"spiller {player_id}" if player_id else "ukjent spiller"

    # Helper to get team name
    def team_name(team_code: Optional[str]) -> str:
        if metadata and team_code:
            return metadata.get_team_name(team_code)
        return f"lag {team_code}" if team_code else "ukjent lag"

    # Silent events (no commentary)
    if evt.kind in ("match_data",):
        return None

    if evt.kind == "timer":
        if evt.subtype == "stop":
            return f"Ballen er ute av spill"
        if evt.subtype == "start":
            return f"Og der er klokken igang igjen"

    # Shots
    if evt.kind == "shot":
        if evt.subtype == "made_2p":
            return f"To poeng fra {player_name(evt.player)}."

        if evt.subtype == "made_3p":
            return f"Tre poeng! {player_name(evt.player)} skårer fra distanse."

        if evt.subtype == "made_1p":
            return f"Straffekast inne av {player_name(evt.player)}."

        if evt.subtype == "missed_2p":
            return f"Bom på topoenger av {player_name(evt.player)}."

        if evt.subtype == "missed_3p":
            return f"Trepoengsforsøk bom av {player_name(evt.player)}."

        if evt.subtype == "penalty_miss_1p":
            return f"{player_name(evt.player)} bommet på straffe."

        if evt.subtype == "blocked":
            return f"Blokkert skudd av {player_name(evt.player)}."

    # Rebounds
    if evt.kind == "rebound":
        if evt.subtype == "defensive":
            return f"Defensiv retur til {player_name(evt.player)}."

        if evt.subtype == "offensive":
            return f"Offensiv retur til {player_name(evt.player)}."

    # Fouls
    if evt.kind == "foul":
        if evt.subtype == "personal":
            return f"Personlig feil på {player_name(evt.player)}."

        if evt.subtype == "defensive":
            return f"Defensiv feil på {player_name(evt.player)}."

        if evt.subtype == "offensive":
            return f"Offensiv feil på {player_name(evt.player)}."

        if evt.subtype == "technical":
            return f"Teknisk feil på {player_name(evt.player)}."

        if evt.subtype == "unsportsmanlike":
            return f"Usportslig feil på {player_name(evt.player)}."

        if evt.subtype == "disqualifying":
            return (
                f"Diskvalifiserende feil! {player_name(evt.player)} er ute av kampen."
            )

        if evt.subtype == "team":
            return f"Lagfeil på {team_name(evt.team)}."

        if evt.subtype == "shooting":
            return f"Skuddfeil på {player_name(evt.player)}."

    # Timeouts
    if evt.kind == "timeout":
        return f"Timeout til {team_name(evt.team)}."

    # Turnovers
    if evt.kind == "turnover":
        return f"Balltap av {player_name(evt.player)}."

    # Periods
    if evt.kind == "period":
        if evt.subtype == "period_start":
            return f"Periode {evt.period} er i gang."

        if evt.subtype == "end":
            return f"Slutt på periode {evt.period}."

    # Match
    if evt.kind == "match":
        if evt.subtype == "end":
            return "Kampen er slutt!"

    return None


def english_commentary(
    evt: NormalizedEvent, metadata: Optional[MatchMetadata] = None
) -> Optional[str]:
    """
    Generate English commentary for a normalized event.

    Args:
        evt: The normalized event
        metadata: Optional match metadata for player/team names

    Returns:
        English commentary string, or None if event should be silent
    """

    print(f"[commentary] Generating English commentary for: {evt.kind} - {evt.subtype}")

    # Helper to get player name
    def player_name(player_id: Optional[int]) -> str:
        if metadata and player_id:
            return metadata.get_player_name(player_id)
        return f"player {player_id}" if player_id else "unknown player"

    # Helper to get team name
    def team_name(team_code: Optional[str]) -> str:
        if metadata and team_code:
            return metadata.get_team_name(team_code)
        return f"team {team_code}" if team_code else "unknown team"

    # Silent events (no commentary)
    if evt.kind in ("match_data",):
        return None

    if evt.kind == "timer":
        if evt.subtype == "stop":
            return "The ball is out of play"
        if evt.subtype == "start":
            return "And the clock is running again"

    # Shots
    if evt.kind == "shot":
        if evt.subtype == "made_2p":
            return f"Two points from {player_name(evt.player)}."

        if evt.subtype == "made_3p":
            return f"Three points! {player_name(evt.player)} scores from downtown."

        if evt.subtype == "made_1p":
            return f"Free throw made by {player_name(evt.player)}."

        if evt.subtype == "missed_2p":
            return f"Missed two-pointer by {player_name(evt.player)}."

        if evt.subtype == "missed_3p":
            return f"Three-point attempt misses by {player_name(evt.player)}."

        if evt.subtype == "penalty_miss_1p":
            return f"{player_name(evt.player)} missed the free throw."

        if evt.subtype == "blocked":
            return f"Shot blocked by {player_name(evt.player)}."

    # Rebounds
    if evt.kind == "rebound":
        if evt.subtype == "defensive":
            return f"Defensive rebound to {player_name(evt.player)}."

        if evt.subtype == "offensive":
            return f"Offensive rebound to {player_name(evt.player)}."

    # Fouls
    if evt.kind == "foul":
        if evt.subtype == "personal":
            return f"Personal foul on {player_name(evt.player)}."

        if evt.subtype == "defensive":
            return f"Defensive foul on {player_name(evt.player)}."

        if evt.subtype == "offensive":
            return f"Offensive foul on {player_name(evt.player)}."

        if evt.subtype == "technical":
            return f"Technical foul on {player_name(evt.player)}."

        if evt.subtype == "unsportsmanlike":
            return f"Unsportsmanlike foul on {player_name(evt.player)}."

        if evt.subtype == "disqualifying":
            return f"Disqualifying foul! {player_name(evt.player)} is ejected from the game."

        if evt.subtype == "team":
            return f"Team foul on {team_name(evt.team)}."

        if evt.subtype == "shooting":
            return f"Shooting foul on {player_name(evt.player)}."

    # Timeouts
    if evt.kind == "timeout":
        return f"Timeout called by {team_name(evt.team)}."

    # Turnovers
    if evt.kind == "turnover":
        return f"Turnover by {player_name(evt.player)}."

    # Periods
    if evt.kind == "period":
        if evt.subtype == "period_start":
            return f"Period {evt.period} is underway."

        if evt.subtype == "end":
            return f"End of period {evt.period}."

    # Match
    if evt.kind == "match":
        if evt.subtype == "end":
            return "That's the final buzzer! Game over!"

    return None
