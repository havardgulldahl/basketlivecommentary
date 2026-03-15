import json
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Any, Optional

from pubnub.callbacks import SubscribeCallback
from pubnub.enums import PNStatusCategory
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub

from wintts import WindowsTTS


# =========================
# Config
# =========================

SUBSCRIBE_KEY = "sub-c-fa031a92-9639-11e8-8ef1-fea37cdf89b9"
MATCH_ID = 8252846
CHANNEL = f"match:{MATCH_ID}:all"
CHANNELS = [
    # add more as needed|
    "match:8262979:all",
]

# =========================
# Normalized event model
# =========================


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


# =========================
# Deduper
# =========================


class RecentEventDeduper:
    def __init__(self, maxlen: int = 500):
        self.items = deque(maxlen=maxlen)
        self.set_items = set()

    def seen(self, fingerprint: str) -> bool:
        if fingerprint in self.set_items:
            return True

        if len(self.items) == self.items.maxlen:
            old = self.items.popleft()
            self.set_items.discard(old)

        self.items.append(fingerprint)
        self.set_items.add(fingerprint)
        return False


# =========================
# Normalizer
# =========================


class GeniusBasketballNormalizer:
    """
    Custom parser/normalizer for raw Genius-style basketball payloads.

    This is intentionally defensive:
    - fields may be absent
    - event schemas may vary slightly
    - enum values may differ by feed
    """

    SHOT_MADE_CODES = {200443, 200444, 200442}
    SHOT_MISSED_CODES = {200442}

    TIMER_START_CODES = {6}
    TIMER_END_CODES = {7}

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
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type=raw_type,
                kind="foul",
                subtype="personal",
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=(
                    f"Foul on player {player}" if player is not None else "Foul"
                ),
            )

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

    def _normalize_shot(
        self,
        raw: dict,
        match_id: Optional[int],
        team: Any,
        player: Any,
        period: Optional[int],
        clock: Optional[str],
    ) -> NormalizedEvent:
        shot_result = self._to_int(raw.get("ShotResult"))
        points = self._extract_points(raw)

        if shot_result in self.SHOT_MADE_CODES:
            subtype = f"made_{points}" if points else "made"
            desc = (
                f"Made {points}-point shot by player {player}"
                if points and player is not None
                else (
                    f"Made shot by player {player}"
                    if player is not None
                    else "Made shot"
                )
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

        if shot_result in self.SHOT_MISSED_CODES:
            subtype = f"missed_{points}" if points else "missed"
            desc = (
                f"Missed {points}-point shot by player {player}"
                if points and player is not None
                else (
                    f"Missed shot by player {player}"
                    if player is not None
                    else "Missed shot"
                )
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

        return self._build_event(
            raw=raw,
            match_id=match_id,
            raw_type="Shot",
            kind="shot",
            subtype="unknown_result",
            team=team,
            player=player,
            points=points,
            period=period,
            clock=clock,
            description=f"Shot with unknown result code {shot_result}",
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
            return self._build_event(
                raw=raw,
                match_id=match_id,
                raw_type="Timer",
                kind="period",
                subtype="start",
                team=team,
                player=player,
                points=None,
                period=period,
                clock=clock,
                description=(
                    f"Start of period {period}"
                    if period is not None
                    else "Period start"
                ),
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

    def _extract_points(self, raw: dict) -> Optional[int]:
        # Try explicit point fields first
        candidates = [
            raw.get("Points"),
            raw.get("Score"),
            raw.get("ShotValue"),
            raw.get("Value"),
        ]
        for c in candidates:
            value = self._to_int(c)
            if value in {1, 2, 3}:
                return value

        # Check shot type description
        shot_type = raw.get("ShotType")
        if isinstance(shot_type, str):
            lowered = shot_type.lower()
            if "3" in lowered or "three" in lowered:
                return 3
            if "free" in lowered or "foul" in lowered:
                return 1
            if "2" in lowered or "two" in lowered:
                return 2

        # Default assumption for made shots without type info
        # Most basketball shots are 2-pointers
        shot_result = self._to_int(raw.get("ShotResult"))
        if shot_result in self.SHOT_MADE_CODES:
            if shot_result == 200443:
                return 2
            if shot_result == 200441:
                return 1
            return 3  # It's a three

        return None

    def _extract_period(self, raw: dict) -> Optional[int]:
        for key in ("Period", "CurrentPeriod", "Quarter"):
            value = self._to_int(raw.get(key))
            if value is not None:
                return value
        return None

    def _extract_clock(self, raw: dict) -> Optional[str]:
        for key in ("Clock", "GameClock", "ClockTime", "Time"):
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

        timestamp = raw.get("Timestamp") or raw.get("Created") or raw.get("Utc")
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


# =========================
# Commentary generator
# =========================


def norwegian_commentary(evt: NormalizedEvent) -> Optional[str]:
    if evt.kind == "shot" and evt.subtype == "made_3":
        return (
            f"Tre poeng fra spiller {evt.player}."
            if evt.player is not None
            else "Tre poeng."
        )

    if evt.kind == "shot" and evt.subtype == "made_2":
        return (
            f"To poeng fra spiller {evt.player}."
            if evt.player is not None
            else "To poeng."
        )

    if evt.kind == "shot" and evt.subtype == "made_1":
        return (
            f"Straffekast satt av spiller {evt.player}."
            if evt.player is not None
            else "Straffekast satt."
        )

    if evt.kind == "shot" and evt.subtype == "missed_3":
        return (
            f"Bom på trepoenger fra spiller {evt.player}."
            if evt.player is not None
            else "Bom på trepoenger."
        )

    if evt.kind == "shot" and evt.subtype and evt.subtype.startswith("missed"):
        return (
            f"Skuddet bommes av spiller {evt.player}."
            if evt.player is not None
            else "Bom."
        )

    if evt.kind == "foul":
        return (
            f"Feil på spiller {evt.player}." if evt.player is not None else "Feil dømt."
        )

    if evt.kind == "timeout":
        return "Timeout."

    if evt.kind == "period" and evt.subtype == "start":
        if evt.period is not None:
            return f"Periode {evt.period} er i gang."
        return "Ny periode er i gang."

    if evt.kind == "period" and evt.subtype == "end":
        if evt.period is not None:
            return f"Slutt på periode {evt.period}."
        return "Periodeslutt."

    return None


# =========================
# PubNub listener
# =========================


class MatchFeedListener(SubscribeCallback):
    def __init__(
        self,
        normalizer: GeniusBasketballNormalizer,
        deduper: RecentEventDeduper,
        tts: WindowsTTS,
        log_file: str = "raw_events.jsonl",
    ):
        self.normalizer = normalizer
        self.deduper = deduper
        self.tts = tts  # Store it
        self.log_file = log_file

        # Open the log file in append mode
        self.log_fp = open(self.log_file, "a", encoding="utf-8")

    def status(self, pubnub, status):
        category = status.category
        if category == PNStatusCategory.PNConnectedCategory:
            print("[status] Connected to PubNub")
        elif category == PNStatusCategory.PNUnexpectedDisconnectCategory:
            print("[status] Unexpected disconnect")
        elif category == PNStatusCategory.PNReconnectedCategory:
            print("[status] Reconnected")
        else:
            print(f"[status] {category}")

    def presence(self, pubnub, presence):
        pass

    def message(self, pubnub, message):
        try:
            raw_msg = message.message
            print("\n[raw]")
            print(json.dumps(raw_msg, ensure_ascii=False, indent=2))
            self.log_fp.write(json.dumps(raw_msg, ensure_ascii=False) + "\n")

            evt = self.normalizer.normalize(raw_msg)
            if evt is None:
                print("[normalize] skipped: could not parse payload")
                return

            if self.deduper.seen(evt.fingerprint):
                print(f"[dedupe] skipped duplicate: {evt.fingerprint}")
                return

            print("[normalized]")
            print(json.dumps(asdict(evt), ensure_ascii=False, indent=2, default=str))

            spoken = norwegian_commentary(evt)
            if spoken:
                print(f"[commentary] {spoken}")
                self.tts.speak(spoken)
            else:
                print("[commentary] no spoken line for this event")

        except Exception as e:
            print(f"[error] message handling failed: {e}")


# =========================
# Main
# =========================


def build_pubnub() -> PubNub:
    config = PNConfiguration()
    config.subscribe_key = SUBSCRIBE_KEY
    config.uuid = f"gpt54-listener-{int(time.time())}"
    return PubNub(config)


def main():
    pubnub = build_pubnub()
    normalizer = GeniusBasketballNormalizer()
    deduper = RecentEventDeduper(maxlen=500)
    tts = WindowsTTS()
    listener = MatchFeedListener(normalizer, deduper, tts)

    pubnub.add_listener(listener)

    print(f"Subscribing to channels: {CHANNELS}")
    pubnub.subscribe().channels(CHANNELS).execute()

    def shutdown_handler(sig, frame):
        print("\nShutting down...")
        pubnub.unsubscribe_all()
        pubnub.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
