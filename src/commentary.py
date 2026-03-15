from typing import Optional
from normalizer import NormalizedEvent


def _team_name(team: str) -> str:
    """Convert team code to Norwegian name."""
    if team == "H":
        return "hjemmelaget"
    elif team == "A":
        return "bortelaget"
    return f"lag {team}"


def norwegian_commentary(evt: NormalizedEvent) -> Optional[str]:
    """
    Generate Norwegian commentary for normalized events.
    """

    # Shot events
    if evt.kind == "shot":
        # Made shots
        if evt.subtype == "made_3p":
            return (
                f"TRE POENG fra spiller {evt.player}!" if evt.player else "TRE POENG!"
            )

        if evt.subtype == "made_2p":
            return f"To poeng fra spiller {evt.player}." if evt.player else "To poeng."

        if evt.subtype == "made_1p":
            return (
                f"Frikast inn av spiller {evt.player}."
                if evt.player
                else "Frikast inn."
            )

        if evt.subtype == "penalty_made_1p":
            return (
                f"Straffekast inn av spiller {evt.player}!"
                if evt.player
                else "Straffekast inn!"
            )

        # Missed shots
        if evt.subtype == "miss_3p":
            return (
                f"Bommer på treeren, spiller {evt.player}."
                if evt.player
                else "Bom på trepoenger."
            )

        if evt.subtype == "miss_2p":
            return f"Bommer, spiller {evt.player}." if evt.player else "Bom."

        if evt.subtype == "miss_1p":
            return (
                f"Bommer på frikastet, spiller {evt.player}."
                if evt.player
                else "Bom på frikast."
            )

        if evt.subtype == "penalty_miss_1p":
            return (
                f"Bommer på straffekastet, spiller {evt.player}!"
                if evt.player
                else "Bommer på straffekastet!"
            )

        # Blocked
        if evt.subtype == "blocked_2p":
            return "Blokkert! Flott forsvarsspill!"

    # Fouls
    if evt.kind == "foul":
        if evt.subtype == "shooting":
            return (
                f"Feil i skuddsituasjon på spiller {evt.player}. Frikast."
                if evt.player
                else "Feil i skuddsituasjon. Frikast."
            )

        if evt.subtype == "defensive":
            return (
                f"Defensiv feil på spiller {evt.player}."
                if evt.player
                else "Defensiv feil."
            )

        if evt.subtype == "offensive":
            return (
                f"Offensiv feil på spiller {evt.player}."
                if evt.player
                else "Offensiv feil."
            )

        if evt.subtype == "technical":
            return (
                f"Teknisk feil på spiller {evt.player}!"
                if evt.player
                else "Teknisk feil!"
            )

        if evt.subtype == "flagrant":
            return (
                f"Unsportslig feil på spiller {evt.player}!"
                if evt.player
                else "Unsportslig feil!"
            )

        # Generic foul
        return f"Feil på spiller {evt.player}." if evt.player else "Feil dømt."

    # Rebounds
    if evt.kind == "rebound":
        if evt.subtype == "defensive":
            return (
                f"Defensiv retursball, spiller {evt.player}."
                if evt.player
                else "Defensiv retursball."
            )
        if evt.subtype == "offensive":
            return (
                f"Offensiv retursball, spiller {evt.player}!"
                if evt.player
                else "Offensiv retursball!"
            )

    # Timeouts
    if evt.kind == "timeout":
        team_name = _team_name(evt.team) if evt.team else None
        return f"Timeout for {team_name}." if team_name else "Timeout."

    # Period events
    if evt.kind == "period":
        if evt.subtype == "start":
            return (
                f"Periode {evt.period} er i gang."
                if evt.period
                else "Ny periode er i gang."
            )
        if evt.subtype == "end":
            return f"Slutt på periode {evt.period}." if evt.period else "Periodeslutt."

    # Match events
    if evt.kind == "match":
        if evt.subtype == "end":
            return "Kampen er slutt!"

    # Silent events (no commentary)
    if evt.kind in ("timer", "match_data"):
        return None

    # No commentary for this event
    return None
