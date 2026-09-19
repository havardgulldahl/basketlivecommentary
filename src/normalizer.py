from dataclasses import dataclass
from typing import Any, Optional

from event_tokens import (
    EventKind,
    FoulSubtype,
    MatchSubtype,
    PeriodSubtype,
    RawEventType,
    ReboundSubtype,
    ShotSubtype,
    TimerSubtype,
    to_enum,
)


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
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    score_announcement: bool = False


class GeniusBasketballNormalizer:
    """
    Custom parser/normalizer for raw Genius-style basketball payloads.
    """

    # Shot result codes -> canonical shot subtype
    SHOT_RESULT_CODES = {
        200442: ShotSubtype.MADE_3P,
        200443: ShotSubtype.MADE_2P,
        200444: ShotSubtype.MADE_1P,
        200445: ShotSubtype.MISSED_1P,
        200580: ShotSubtype.MISSED_3P,
        200581: ShotSubtype.MISSED_2P,
    }

    # Foul type codes
    FOUL_TYPE_CODES = {
        200448: FoulSubtype.DEFENSIVE,
        200449: FoulSubtype.OFFENSIVE,
        200450: FoulSubtype.TECHNICAL,
        200451: FoulSubtype.FLAGRANT,
        200461: FoulSubtype.SHOOTING,
    }

    # Timer type mapping
    TIMER_TYPE_MAP = {
        1: (EventKind.TIMER, TimerSubtype.START),  # Start
        2: (EventKind.TIMER, TimerSubtype.STOP),  # Stop
        3: (EventKind.TIMER, TimerSubtype.UPDATE),  # Update
        5: (EventKind.MATCH, MatchSubtype.END),  # Match end
        6: (EventKind.PERIOD, PeriodSubtype.PERIOD_START),  # Period start
        7: (EventKind.PERIOD, PeriodSubtype.END),  # Period end
    }

    # Map PartialResultTypeId to period number
    PERIOD_ID_MAP = {
        200073: 1,
        200074: 2,
        200075: 3,
        200076: 4,
        # 200077: 5,  # OT1
        # 200078: 6,  # OT2
    }

    def normalize(self, envelope_message: Any) -> Optional[NormalizedEvent]:
        raw = self._extract_payload(envelope_message)
        if not isinstance(raw, dict):
            return None

        raw_type_value = raw.get("MatchEventType")
        raw_type = to_enum(raw_type_value, RawEventType)

        match_id = self._to_int(raw.get("MatchId"))
        team = raw.get("Team")
        player = raw.get("Player")
        period = self._extract_period(raw)
        clock = self._extract_clock(raw)

        if raw_type == RawEventType.SHOT:
            return self._normalize_shot(raw, match_id, team, player, period, clock)

        if raw_type == RawEventType.FOUL:
            return self._normalize_foul(raw, match_id, team, player, period, clock)

        if raw_type == RawEventType.DEFENSIVE_REBOUND:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind=EventKind.REBOUND,
                subtype=ReboundSubtype.DEFENSIVE,
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

        if raw_type == RawEventType.OFFENSIVE_REBOUND:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind=EventKind.REBOUND,
                subtype=ReboundSubtype.OFFENSIVE,
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

        if raw_type == RawEventType.TURNOVER:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind=EventKind.TURNOVER,
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

        if raw_type == RawEventType.TIMER:
            return self._normalize_timer(raw, match_id, team, player, period, clock)

        if raw_type == RawEventType.TIMEOUT:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind=EventKind.TIMEOUT,
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

        if raw_type == RawEventType.MATCH_DATA:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind=EventKind.MATCH_DATA,
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
            raw_type=raw_type_value,
            kind=EventKind.UNKNOWN,
            subtype=None,
            team=team,
            player=player,
            points=None,
            period=period,
            clock=clock,
            description=f"Unknown event type: {raw_type_value}",
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

        foul_type = self.FOUL_TYPE_CODES.get(foul_type_code, FoulSubtype.PERSONAL)

        if is_coach:
            desc = f"Foul on coach (team {team})" if team else "Foul on coach"
        elif player is not None:
            desc = f"{foul_type.value.capitalize()} foul on player {player}"
        else:
            desc = f"{foul_type.value.capitalize()} foul"

        if foul_severity and foul_severity > 0:
            desc += f" (severity: {foul_severity})"

        return self._build_event(
            raw=raw,
            match_id=match_id,
            raw_type=RawEventType.FOUL,
            kind=EventKind.FOUL,
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
        shot_subtype = self.SHOT_RESULT_CODES.get(shot_result_code)

        if shot_subtype is None:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=RawEventType.SHOT,
                kind=EventKind.SHOT,
                subtype=ShotSubtype.UNKNOWN_RESULT,
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=f"Shot with unknown result code {shot_result_code}",
            )

        points = self._points_from_shot_subtype(shot_subtype)

        if shot_subtype in {
            ShotSubtype.MADE_1P,
            ShotSubtype.MADE_2P,
            ShotSubtype.MADE_3P,
            ShotSubtype.PENALTY_MADE_1P,
        }:
            desc = (
                f"Made {points}-point shot by player {player}"
                if points and player is not None
                else (
                    f"Made shot by player {player}"
                    if player is not None
                    else "Made shot"
                )
            )
        elif shot_subtype == ShotSubtype.BLOCKED:
            desc = (
                f"Shot blocked (player {player})"
                if player is not None
                else "Shot blocked"
            )
        else:
            point_desc = self._miss_description_for_shot(shot_subtype)
            desc = (
                f"Missed {point_desc} shot by player {player}"
                if player is not None
                else f"Missed {point_desc} shot"
            )

        return self._build_event(
            raw=raw,
            match_id=match_id,
            raw_type=RawEventType.SHOT,
            kind=EventKind.SHOT,
            subtype=shot_subtype,
            team=team,
            player=player,
            points=points,
            period=period,
            clock=clock,
            description=desc,
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
        mapped = self.TIMER_TYPE_MAP.get(timer_type)

        if mapped is None:
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=RawEventType.TIMER,
                kind=EventKind.TIMER,
                subtype=TimerSubtype.UNKNOWN,
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=f"Timer event type {timer_type}",
            )

        kind, subtype = mapped

        if kind == EventKind.PERIOD and subtype == PeriodSubtype.PERIOD_START:
            description = (
                f"Start of period {period}" if period is not None else "Start of period"
            )
        elif kind == EventKind.PERIOD and subtype == PeriodSubtype.END:
            description = (
                f"End of period {period}" if period is not None else "Period end"
            )
        elif kind == EventKind.MATCH and subtype == MatchSubtype.END:
            description = "Match end"
        elif kind == EventKind.TIMER and subtype == TimerSubtype.START:
            description = "Clock start"
        elif kind == EventKind.TIMER and subtype == TimerSubtype.STOP:
            description = "Clock stop"
        else:
            description = "Timer update"

        return self._build_event(
            raw=raw,
            match_id=match_id,
            raw_type=RawEventType.TIMER,
            kind=kind,
            subtype=subtype,
            team=team,
            player=player,
            points=None,
            period=period,
            clock=clock,
            description=description,
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
        for key in ("PartialResultTypeId", "Period"):
            period_id = self._to_int(raw.get(key))
            if period_id in self.PERIOD_ID_MAP:
                return self.PERIOD_ID_MAP[period_id]
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
        raw_type: Optional[object],
        kind: EventKind,
        subtype: Optional[object],
        team: Any,
        player: Any,
        points: Optional[int],
        period: Optional[int],
        clock: Optional[str],
        description: str,
    ) -> NormalizedEvent:
        raw_type_value = raw_type.value if hasattr(raw_type, "value") else raw_type
        kind_value = kind.value if hasattr(kind, "value") else str(kind)
        subtype_value = subtype.value if hasattr(subtype, "value") else subtype

        fingerprint = self._fingerprint(
            raw,
            match_id,
            raw_type_value,
            kind_value,
            subtype_value,
            team,
            player,
            points,
            period,
            clock,
        )

        return NormalizedEvent(
            match_id=match_id,
            raw_type=raw_type_value,
            kind=kind_value,
            subtype=subtype_value,
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
        except ValueError, TypeError:
            return None

    def _points_from_shot_subtype(self, subtype: ShotSubtype) -> Optional[int]:
        if subtype in {ShotSubtype.MADE_1P, ShotSubtype.PENALTY_MADE_1P}:
            return 1
        if subtype == ShotSubtype.MADE_2P:
            return 2
        if subtype == ShotSubtype.MADE_3P:
            return 3
        return None

    def _miss_description_for_shot(self, subtype: ShotSubtype) -> str:
        if subtype in {ShotSubtype.MISSED_1P, ShotSubtype.PENALTY_MISS_1P}:
            return "1-point"
        if subtype == ShotSubtype.MISSED_2P:
            return "2-point"
        if subtype == ShotSubtype.MISSED_3P:
            return "3-point"
        return "unknown"
