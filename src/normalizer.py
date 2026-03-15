from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class NormalizedEvent:
    match_id: Optional[int]
    raw_type: Optional[str]
    kind: str
    subtype: Optional[str]
    team: Optional[Any]
    player: Optional[Any]
    points: Optional[int]
    period: Optional[int]
    clock: Optional[str]
    description: str
    fingerprint: str
    raw: dict


class GeniusBasketballNormalizer:
    """
    Custom parser/normalizer for raw Genius-style basketball payloads.
    """

    # Shot result codes
    SHOT_RESULT_CODES = {
        200437: ("1p", "made"),  # 1-point made (free throw) - alternative code
        200438: ("2p", "made"),  # 2-point made
        200439: ("3p", "made"),  # 3-point made
        200440: ("1p", "miss"),  # 1-point miss (free throw)
        200441: ("2p", "miss"),  # 2-point miss
        200442: ("3p", "miss"),  # 3-point miss
        200443: ("2p", "made"),  # 2-point made - confirmed
        200444: ("1p", "made"),  # 1-point made (free throw) - confirmed
        200445: ("1p", "penalty_miss"),  # Penalty shot miss
        200446: ("1p", "penalty_made"),  # Penalty shot made (assumed)
    }

    # Foul type codes
    FOUL_TYPE_CODES = {
        200448: "defensive",  # Defensive foul (non-shooting)
        200449: "offensive",  # Offensive foul
        200450: "technical",  # Technical foul (assumed)
        200451: "flagrant",  # Flagrant foul (assumed)
        200461: "shooting",  # Shooting foul (defensive foul resulting in free throws)
    }

    # Timer type codes
    TIMER_START_CODES = {1, 6}  # 1=Start, 6=Period start
    TIMER_STOP_CODES = {2}  # 2=Stop
    TIMER_END_CODES = {7}  # 7=Period end
    TIMER_MATCH_END_CODES = {5}  # 5=Match end
    TIMER_UPDATE_CODES = {3}  # 3=Update

    def normalize(self, envelope_message: Any) -> Optional[NormalizedEvent]:
        """
        PubNub SDK usually gives the message payload itself.
        Some feeds may wrap the actual event inside 'd'.
        """
        raw = self._extract_payload(envelope_message)
        if not isinstance(raw, dict):
            return None

        raw_type = raw.get("MatchEventType")
        match_id = self._to_int(raw.get("MatchId"))
        team = raw.get("Team")
        player = raw.get("Player")
        period = self._extract_period(raw)
        clock = self._extract_clock(raw)

        if raw_type == "Shot":
            return self._normalize_shot(raw, match_id, team, player, period, clock)

        if raw_type == "Foul":
            return self._normalize_foul(raw, match_id, team, player, period, clock)

        if raw_type == "DefensiveRebound":
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind="rebound",
                subtype="defensive",
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=(
                    f"Defensive rebound by player {player}"
                    if player is not None
                    else "Defensive rebound"
                ),
            )

        if raw_type == "OffensiveRebound":
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind="rebound",
                subtype="offensive",
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=(
                    f"Offensive rebound by player {player}"
                    if player is not None
                    else "Offensive rebound"
                ),
            )
        if raw_type == "Turnover":
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind="turnover",
                subtype=None,
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=(
                    f"Turnover by player {player}" if player is not None else "Turnover"
                ),
            )

        if raw_type == "Timer":
            return self._normalize_timer(raw, match_id, team, player, period, clock)

        if raw_type == "Timeout":
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind="timeout",
                subtype=None,
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=(
                    f"Timeout for team {team}" if team is not None else "Timeout"
                ),
            )

        if raw_type == "MatchData":
            # This is match metadata (rosters, etc.) - usually ignore for commentary
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind="match_data",
                subtype=None,
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description="Match data update",
            )

        return self._build_event(
            raw=raw,
            match_id=match_id,
            raw_type=raw_type,
            kind="unknown",
            subtype=None,
            team=team,
            player=player,
            points=None,
            period=period,
            clock=clock,
            description=f"Unknown event type: {raw_type}",
        )

    def _normalize_foul(
        self,
        raw: dict,
        match_id: Optional[int],
        team: Any,
        player: Any,
        period: Optional[int],
        clock: Optional[str],
    ) -> NormalizedEvent:
        foul_type_code = self._to_int(raw.get("FoulType"))
        foul_severity = self._to_int(raw.get("FoulSeverity"))
        is_coach = raw.get("IsCoach", False)

        # Look up foul type
        foul_type = self.FOUL_TYPE_CODES.get(foul_type_code, "personal")

        # Build description
        if is_coach:
            desc = f"Foul on coach (team {team})" if team else "Foul on coach"
        elif player is not None:
            desc = f"{foul_type.capitalize()} foul on player {player}"
        else:
            desc = f"{foul_type.capitalize()} foul"

        if foul_severity and foul_severity > 0:
            desc += f" (severity: {foul_severity})"

        return self._build_event(
            raw=raw,
            match_id=match_id,
            raw_type="Foul",
            kind="foul",
            subtype=foul_type,
            team=team,
            player=player,
            points=None,
            period=period,
            clock=clock,
            description=desc,
        )

    def _normalize_shot(
        self,
        raw: dict,
        match_id: Optional[int],
        team: Any,
        player: Any,
        period: Optional[int],
        clock: Optional[str],
    ) -> NormalizedEvent:
        shot_result_code = self._to_int(raw.get("ShotResult"))

        # Look up shot type and result
        shot_info = self.SHOT_RESULT_CODES.get(shot_result_code)

        if shot_info:
            shot_type, result = shot_info

            # Determine points
            points = None
            if result in ("made", "penalty_made"):
                if shot_type == "1p":
                    points = 1
                elif shot_type == "2p":
                    points = 2
                elif shot_type == "3p":
                    points = 3

            # Build subtype
            subtype = f"{result}_{shot_type}"

            # Build description
            if result in ("made", "penalty_made"):
                desc = (
                    f"Made {points}-point shot by player {player}"
                    if points and player is not None
                    else (
                        f"Made shot by player {player}"
                        if player is not None
                        else "Made shot"
                    )
                )
            elif result == "blocked":
                desc = (
                    f"Shot blocked (player {player})"
                    if player is not None
                    else "Shot blocked"
                )
            else:  # miss or penalty_miss
                point_desc = shot_type.replace("p", "-point")
                desc = (
                    f"Missed {point_desc} shot by player {player}"
                    if player is not None
                    else f"Missed {point_desc} shot"
                )

            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type="Shot",
                kind="shot",
                subtype=subtype,
                team=team,
                player=player,
                points=points,
                period=period,
                clock=clock,
                description=desc,
            )

        # Unknown shot result code
        return self._build_event(
            raw=raw,
            match_id=match_id,
            raw_type="Shot",
            kind="shot",
            subtype="unknown_result",
            team=team,
            player=player,
            points=None,
            period=period,
            clock=clock,
            description=f"Shot with unknown result code {shot_result_code}",
        )

    def _normalize_timer(
        self,
        raw: dict,
        match_id: Optional[int],
        team: Any,
        player: Any,
        period: Optional[int],
        clock: Optional[str],
    ) -> NormalizedEvent:
        timer_type = self._to_int(raw.get("Type"))

        if timer_type in self.TIMER_START_CODES:
            subtype = "period_start" if timer_type == 6 else "start"
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type="Timer",
                kind="period" if timer_type == 6 else "timer",
                subtype=subtype,
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=(
                    f"Start of period {period}"
                    if timer_type == 6 and period is not None
                    else "Clock start"
                ),
            )

        if timer_type in self.TIMER_STOP_CODES:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type="Timer",
                kind="timer",
                subtype="stop",
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description="Clock stop",
            )

        if timer_type in self.TIMER_END_CODES:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type="Timer",
                kind="period",
                subtype="end",
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=(
                    f"End of period {period}" if period is not None else "Period end"
                ),
            )

        if timer_type in self.TIMER_MATCH_END_CODES:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type="Timer",
                kind="match",
                subtype="end",
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description="Match end",
            )

        if timer_type in self.TIMER_UPDATE_CODES:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type="Timer",
                kind="timer",
                subtype="update",
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description="Timer update",
            )

        return self._build_event(
            raw=raw,
            match_id=match_id,
            raw_type="Timer",
            kind="timer",
            subtype="unknown",
            team=team,
            player=player,
            points=None,
            period=period,
            clock=clock,
            description=f"Timer event type {timer_type}",
        )

    def _extract_payload(self, message: Any) -> Any:
        if (
            isinstance(message, dict)
            and "d" in message
            and isinstance(message["d"], dict)
        ):
            return message["d"]
        return message

    def _extract_period(self, raw: dict) -> Optional[int]:
        for key in ("Period", "CurrentPeriod", "Quarter"):
            value = self._to_int(raw.get(key))
            if value is not None:
                return value
        return None

    def _extract_clock(self, raw: dict) -> Optional[str]:
        for key in ("Clock", "GameClock", "ClockTime", "Time", "PeriodTime"):
            value = raw.get(key)
            if value is not None:
                return str(value)
        return None

    def _build_event(
        self,
        raw: dict,
        match_id: Optional[int],
        raw_type: Optional[str],
        kind: str,
        subtype: Optional[str],
        team: Any,
        player: Any,
        points: Optional[int],
        period: Optional[int],
        clock: Optional[str],
        description: str,
    ) -> NormalizedEvent:
        fingerprint = self._fingerprint(
            raw, match_id, raw_type, kind, subtype, team, player, points, period, clock
        )
        return NormalizedEvent(
            match_id=match_id,
            raw_type=raw_type,
            kind=kind,
            subtype=subtype,
            team=team,
            player=player,
            points=points,
            period=period,
            clock=clock,
            description=description,
            fingerprint=fingerprint,
            raw=raw,
        )

    def _fingerprint(
        self,
        raw: dict,
        match_id: Optional[int],
        raw_type: Optional[str],
        kind: str,
        subtype: Optional[str],
        team: Any,
        player: Any,
        points: Optional[int],
        period: Optional[int],
        clock: Optional[str],
    ) -> str:
        """
        Prefer real IDs if present. Fall back to a composite key.
        """
        event_id = raw.get("EventId") or raw.get("Id") or raw.get("MessageId")
        if event_id is not None:
            return f"id:{event_id}"

        timestamp = (
            raw.get("Timestamp")
            or raw.get("Created")
            or raw.get("Utc")
            or raw.get("ServerTimeStamp")
        )
        return "|".join(
            [
                str(match_id),
                str(raw_type),
                str(kind),
                str(subtype),
                str(team),
                str(player),
                str(points),
                str(period),
                str(clock),
                str(timestamp),
            ]
        )

    def _to_int(self, value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except (ValueError, TypeError):
            return None
