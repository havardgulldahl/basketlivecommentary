from enum import Enum
from typing import Optional, Type, TypeVar


class Language(str, Enum):
    NO = "no"
    EN = "en"


class RawEventType(str, Enum):
    SHOT = "Shot"
    FOUL = "Foul"
    DEFENSIVE_REBOUND = "DefensiveRebound"
    OFFENSIVE_REBOUND = "OffensiveRebound"
    TURNOVER = "Turnover"
    TIMER = "Timer"
    TIMEOUT = "Timeout"
    MATCH_DATA = "MatchData"


class EventKind(str, Enum):
    MATCH_DATA = "match_data"
    TIMER = "timer"
    SHOT = "shot"
    REBOUND = "rebound"
    FOUL = "foul"
    TIMEOUT = "timeout"
    TURNOVER = "turnover"
    PERIOD = "period"
    MATCH = "match"
    UNKNOWN = "unknown"


class TimerSubtype(str, Enum):
    START = "start"
    STOP = "stop"
    UPDATE = "update"
    UNKNOWN = "unknown"


class PeriodSubtype(str, Enum):
    PERIOD_START = "period_start"
    END = "end"


class MatchSubtype(str, Enum):
    END = "end"


class ShotSubtype(str, Enum):
    MADE_1P = "made_1p"
    MADE_2P = "made_2p"
    MADE_3P = "made_3p"
    MISSED_1P = "missed_1p"
    MISSED_2P = "missed_2p"
    MISSED_3P = "missed_3p"
    PENALTY_MISS_1P = "penalty_miss_1p"
    PENALTY_MADE_1P = "penalty_made_1p"
    BLOCKED = "blocked"
    UNKNOWN_RESULT = "unknown_result"


class ReboundSubtype(str, Enum):
    DEFENSIVE = "defensive"
    OFFENSIVE = "offensive"


class FoulSubtype(str, Enum):
    PERSONAL = "personal"
    DEFENSIVE = "defensive"
    OFFENSIVE = "offensive"
    TECHNICAL = "technical"
    FLAGRANT = "flagrant"
    UNSPORTSMANLIKE = "unsportsmanlike"
    DISQUALIFYING = "disqualifying"
    TEAM = "team"
    SHOOTING = "shooting"


E = TypeVar("E", bound=Enum)


def to_enum(value: object, enum_cls: Type[E]) -> Optional[E]:
    if not isinstance(value, str):
        return None
    try:
        return enum_cls(value)
    except ValueError:
        return None
