import json
import time
import threading
import platform
import traceback
from collections import deque
from pathlib import Path
from typing import Any, Optional, cast
from datetime import datetime

from pubnub.callbacks import SubscribeCallback
from pubnub.enums import PNStatusCategory, PNReconnectionPolicy
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub

from commentary import get_commentary
from game_summary import GameSummary
from normalizer import GeniusBasketballNormalizer, NormalizedEvent
from game_clock import GameClock
from match_metadata import MatchMetadata
from tts import BaseTTS
from llm_commentary import BufferedCommentaryEngine

# =========================
# Config
# =========================

SUBSCRIBE_KEY = "sub-c-fa031a92-9639-11e8-8ef1-fea37cdf89b9"


# =========================
# Deduper
# =========================


class RecentEventDeduper:
    def __init__(self, maxlen: int = 500) -> None:
        self.items: deque[str] = deque(maxlen=maxlen)
        self.set_items: set[str] = set()
        self.score_versions: dict[str, tuple[Any, Optional[int]]] = {}

    def is_new(self, evt: NormalizedEvent) -> bool:
        """Check if event is new (not a duplicate)."""
        fingerprint = evt.fingerprint
        if fingerprint in self.set_items:
            score_version = self._score_version(evt)
            if (
                score_version is None
                or self.score_versions.get(fingerprint) == score_version
            ):
                return False
            self.score_versions[fingerprint] = score_version
            return True

        if len(self.items) == self.items.maxlen:
            old = self.items.popleft()
            self.set_items.discard(old)
            self.score_versions.pop(old, None)

        self.items.append(fingerprint)
        self.set_items.add(fingerprint)
        score_version = self._score_version(evt)
        if score_version is not None:
            self.score_versions[fingerprint] = score_version
        return True

    @staticmethod
    def _score_version(
        event: NormalizedEvent,
    ) -> Optional[tuple[Any, Optional[int]]]:
        if event.kind != "shot":
            return None
        return event.team, event.points


class ScoreTracker:
    def __init__(
        self,
        announce_every: int = 4,
        stoppage_announce_every: int = 3,
        cooldown_seconds: float = 20.0,
    ) -> None:
        self.home_score = 0
        self.away_score = 0
        self.scoring_events = 0
        self.stoppage_events = 0
        self.announce_every = announce_every
        self.stoppage_announce_every = stoppage_announce_every
        self.cooldown_seconds = cooldown_seconds
        self.last_score_spoken_at: Optional[float] = None
        self.score_announcements: list[dict[str, object]] = []
        self.scoring_actions: dict[str, tuple[Any, int]] = {}

    def update(self, event: NormalizedEvent, announce: bool = True) -> None:
        event.score_announcement = False
        event.score_time_announcement = False
        event.home_score = self.home_score
        event.away_score = self.away_score

        if event.kind == "shot":
            previous_team, previous_points = self.scoring_actions.get(
                event.fingerprint, (None, 0)
            )
            current_points = event.points or 0

            if previous_team == "H":
                self.home_score -= previous_points
            elif previous_team == "A":
                self.away_score -= previous_points

            if event.team == "H":
                self.home_score += current_points
            elif event.team == "A":
                self.away_score += current_points

            was_scoring = previous_team in {"H", "A"} and previous_points > 0
            is_scoring = event.team in {"H", "A"} and current_points > 0
            self.scoring_events += int(is_scoring) - int(was_scoring)
            self.scoring_actions[event.fingerprint] = (
                event.team,
                current_points,
            )
            event.home_score = self.home_score
            event.away_score = self.away_score
            score_changed = (previous_team, previous_points) != (
                event.team,
                current_points,
            )
            if (
                score_changed
                and is_scoring
                and self.scoring_events % self.announce_every == 0
            ):
                event.score_announcement = self._schedule_announcement(event, announce)
        elif event.kind == "timer" and event.subtype == "stop":
            self.stoppage_events += 1
            event.score_time_announcement = self._schedule_announcement(event, announce)
        elif event.kind == "match" and event.subtype == "end":
            event.final_summary = True

    def _schedule_announcement(self, event: NormalizedEvent, announce: bool) -> bool:
        if not announce:
            return False
        now = time.monotonic()
        if (
            self.last_score_spoken_at is not None
            and now - self.last_score_spoken_at < self.cooldown_seconds
        ):
            return False
        self.last_score_spoken_at = now
        self.score_announcements.append(
            {
                "timestamp": time.time(),
                "event_id": cast(dict[str, Any], event.raw).get("Id"),
                "home_score": self.home_score,
                "away_score": self.away_score,
                "period": event.period,
                "clock": event.clock,
                "reason": "stoppage" if event.kind == "timer" else "score",
            }
        )
        return True


# =========================
# PubNub listener
# =========================


class MatchFeedListener(SubscribeCallback):
    def __init__(
        self,
        normalizer: GeniusBasketballNormalizer,
        deduper: RecentEventDeduper,
        tts: Optional[BaseTTS],
        game_clock: GameClock,
        match_id: int,
        commentary_engine: Optional[BufferedCommentaryEngine] = None,
        language: str = "no",
    ):
        super().__init__()
        self.normalizer = normalizer
        self.deduper = deduper
        self.game_clock = game_clock
        self.tts = tts
        self.language = language
        self.metadata: Optional[MatchMetadata] = None
        self.commentary_engine = commentary_engine
        self.score_tracker = ScoreTracker()
        self.game_summary = GameSummary()
        self.summary_written = False
        self.match_introduction_announced = False
        self.startup_status_announced = False
        self.match_started = False
        self.match_ended = False
        self.last_event: Optional[NormalizedEvent] = None
        self.lineups: dict[str, dict[int, str]] = {}
        self.match_finished_at: Optional[float] = None
        self.match_finish_grace_period = 60.0
        self.match_dir = Path("matchdata") / str(match_id)
        self.match_dir.mkdir(parents=True, exist_ok=True)
        self.summary_path = self.match_dir / "summary.md"

        # Open log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = str(self.match_dir / f"raw_events_{timestamp}.jsonl")
        self.log_fp = open(self.log_file, "w", encoding="utf-8")
        print(f"[log] Writing raw events to: {self.log_file}")
        self.error_log_file = str(self.match_dir / f"errors_{timestamp}.log")
        self.error_log_fp = open(self.error_log_file, "a", encoding="utf-8")
        print(f"[log] Writing errors to: {self.error_log_file}")

        # Connection state
        self.is_connected = False
        self.reconnect_count = 0
        self.last_event_time = time.time()

    def get_metadata(self) -> Optional[MatchMetadata]:
        return self.metadata

    def _log_error(self, context: str, error: BaseException):
        timestamp = datetime.now().isoformat(timespec="seconds")
        self.error_log_fp.write(f"[{timestamp}] {context}: {error}\n")
        traceback.print_exception(
            type(error), error, error.__traceback__, file=self.error_log_fp
        )
        self.error_log_fp.flush()

    def _cache_match_metadata(self, raw_msg: dict):
        self.metadata = MatchMetadata.from_raw(raw_msg)
        metadata_path = self.match_dir / "metadata.json"
        with metadata_path.open("w", encoding="utf-8") as metadata_fp:
            json.dump(raw_msg, metadata_fp, ensure_ascii=False, indent=2)
            metadata_fp.write("\n")

        print(f"[log] Cached match metadata in: {metadata_path}")

    def _announce_match_introduction(self):
        if self.match_introduction_announced or self.metadata is None:
            return

        self.match_introduction_announced = True
        home_name = self.metadata.get_team_name("H")
        away_name = self.metadata.get_team_name("A")
        venue = self.metadata.activity_area.strip() or self.metadata.venue_no
        home_coaches = (
            ", ".join(coach.full_name for coach in self.metadata.home_coaches)
            or "ingen registrerte"
        )
        away_coaches = (
            ", ".join(coach.full_name for coach in self.metadata.away_coaches)
            or "ingen registrerte"
        )

        print("\n" + "=" * 60)
        print("MATCH DATA")
        print("=" * 60)
        print(f"Home: {home_name}")
        print(f"Away: {away_name}")
        print(f"Venue: {venue}")
        print(f"Home coaches: {home_coaches}")
        print(f"Away coaches: {away_coaches}")
        print("=" * 60 + "\n")

        spoken = f"Vi følger med kampen mellom {home_name} og {away_name} på {venue}."
        if self.tts:
            print(f"[audio] Speaking: {spoken}")
            self.tts.speak(spoken)

    def _announce_startup_status(self) -> None:
        if self.startup_status_announced:
            return

        self.startup_status_announced = True
        if self.metadata:
            home_name = self.metadata.get_team_name("H")
            away_name = self.metadata.get_team_name("A")
        elif self.language == "en":
            home_name, away_name = "the home team", "the away team"
        else:
            home_name, away_name = "hjemmelaget", "bortelaget"

        if not self.match_started:
            if self.language == "en":
                spoken = (
                    f"The game between {home_name} and {away_name} "
                    "has not started yet."
                )
            else:
                spoken = (
                    f"Kampen mellom {home_name} og {away_name} "
                    "har ikke startet ennå."
                )
        elif self.match_ended:
            if self.language == "en":
                spoken = (
                    f"The game is over. The final score between {home_name} "
                    f"and {away_name} is {self.score_tracker.home_score}-"
                    f"{self.score_tracker.away_score}."
                )
            else:
                spoken = (
                    f"Kampen er slutt. Sluttstillingen mellom {home_name} "
                    f"og {away_name} er {self.score_tracker.home_score}-"
                    f"{self.score_tracker.away_score}."
                )
        else:
            last_commentary = (
                get_commentary(
                    self.last_event,
                    metadata=self.metadata,
                    language=self.language,
                )
                if self.last_event
                else None
            )
            if self.language == "en":
                spoken = (
                    f"The game is underway. The score between {home_name} "
                    f"and {away_name} is {self.score_tracker.home_score}-"
                    f"{self.score_tracker.away_score}."
                )
                last_prefix = " Last event: "
                unavailable = " Last event is unavailable."
            else:
                spoken = (
                    f"Kampen er i gang. Stillingen mellom {home_name} "
                    f"og {away_name} er {self.score_tracker.home_score}-"
                    f"{self.score_tracker.away_score}."
                )
                last_prefix = " Siste hendelse: "
                unavailable = " Siste hendelse er ikke tilgjengelig."
            spoken += (
                f"{last_prefix}{last_commentary}" if last_commentary else unavailable
            )

        print(f"[startup] {spoken}")
        if self.tts:
            self.tts.speak(spoken)

    def status(self, pubnub, status):
        """Handle connection status changes."""
        try:
            category = status.category
            network_issue_categories = tuple(
                category_type
                for category_type in (
                    getattr(PNStatusCategory, "PNNetworkIssuesCategory", None),
                    getattr(PNStatusCategory, "PNConnectionError", None),
                )
                if category_type is not None
            )

            if category == PNStatusCategory.PNConnectedCategory:
                self.is_connected = True
                if self.reconnect_count > 0:
                    print(
                        f"\n✅ [network] Reconnected successfully (attempt #{self.reconnect_count})"
                    )
                else:
                    print("✅ [network] Connected to PubNub")
                self.reconnect_count = 0

            elif category == PNStatusCategory.PNReconnectedCategory:
                self.is_connected = True
                print("\n✅ [network] Reconnected to PubNub")

            elif category == PNStatusCategory.PNDisconnectedCategory:
                self.is_connected = False
                print("\n⚠️  [network] Disconnected from PubNub")

            elif category == PNStatusCategory.PNUnexpectedDisconnectCategory:
                self.is_connected = False
                print(
                    "\n❌ [network] Unexpected disconnection - PubNub will auto-reconnect"
                )

            elif category in network_issue_categories:
                self.is_connected = False
                self.reconnect_count += 1
                print(
                    f"\n❌ [network] Connection error (attempt #{self.reconnect_count})"
                )

            elif category == PNStatusCategory.PNAccessDeniedCategory:
                print("\n❌ [network] Access denied - check your PubNub credentials")

            elif category == PNStatusCategory.PNTimeoutCategory:
                print("\n⚠️  [network] Request timeout")

            print(f"[status] {getattr(category, 'name', category)}")
        except Exception as error:
            self._log_error("PubNub status handling failed", error)
            print(f"[error] PubNub status handling failed: {error}")

    def presence(self, pubnub, presence):
        pass

    def message(self, pubnub, message):
        """Handle incoming messages with heartbeat monitoring."""
        self.last_event_time = time.time()

        try:
            self._process_raw_message(message.message, announce=True)

        except Exception as e:
            print(f"[error] message handling failed: {e}")
            self._log_error("Message handling failed", e)

    def bootstrap_history(self, pubnub: PubNub, channel: str):
        """Load channel history before subscribing so metadata and score are ready."""
        print(f"[history] Loading prior events for {channel}...")
        start_token = None
        events_loaded = 0

        try:
            while True:
                history_request = (
                    pubnub.history().channel(channel).reverse(True).count(100)
                )
                if start_token is not None:
                    history_request = history_request.start(start_token)

                result = history_request.sync().result
                messages = result.messages
                for history_item in messages:
                    if not isinstance(history_item.entry, dict):
                        continue
                    try:
                        self._process_raw_message(history_item.entry, announce=False)
                        events_loaded += 1
                    except Exception as error:
                        self._log_error("History event handling failed", error)

                if len(messages) < 100:
                    break

                next_start_token = result.end_timetoken
                if not next_start_token or next_start_token == start_token:
                    break
                start_token = next_start_token

            print(f"[history] Loaded {events_loaded} prior events")
        except Exception as error:
            self._log_error("History loading failed", error)
            print(f"[history] Could not load prior events: {error}")
        self._announce_startup_status()

    def _process_raw_message(self, raw_msg: dict, announce: bool):
        self.log_fp.write(json.dumps(raw_msg, ensure_ascii=False) + "\n")
        self.log_fp.flush()

        if raw_msg.get("MatchEventType") == "MatchData":
            self._handle_match_data(raw_msg, announce=announce)
            return

        evt = self.normalizer.normalize(raw_msg)
        if evt is None:
            if announce:
                print("[normalize] skipped: could not parse payload")
            return

        self.game_summary.update(evt)
        if not self.deduper.is_new(evt):
            if self.match_ended:
                self._write_game_summary()
            if announce:
                print(f"[dedupe] skipped duplicate: {evt.fingerprint}")
            return

        if evt.kind == "lineup":
            lineup_changed = self._update_lineup(evt)
            if not lineup_changed:
                return

        self.score_tracker.update(evt, announce=announce)

        if evt.kind == "match":
            if evt.subtype == "start":
                self.match_started = True
                self.match_ended = False
            elif evt.subtype == "end":
                self.match_started = True
                self.match_ended = True

        if not (
            evt.kind in {"match_data", "lineup", "unknown"}
            or evt.kind == "timer"
            and evt.subtype == "update"
        ):
            self.last_event = evt

        if evt.final_summary and self.match_finished_at is None:
            self.match_finished_at = time.monotonic() + self.match_finish_grace_period
            if announce:
                print(
                    f"[match] Finished; shutting down in "
                    f"{int(self.match_finish_grace_period)} seconds"
                )

        if evt.kind == "period":
            if evt.subtype == "start":
                self.game_clock.start_period(evt.period or 1)
            elif evt.subtype == "end":
                self.game_clock.end_period()
        elif evt.kind == "timer" and evt.clock:
            self.game_clock.update_clock(evt.clock)

        if self.match_ended:
            self._write_game_summary()

        if not announce:
            return

        print(f"\n[event] {evt.kind} | {evt.subtype or ''}")
        if evt.description:
            print(f"  {evt.description}")

        if self.metadata and evt.player:
            player_name = self.metadata.get_player_display_name(evt.player)
            print(f"  [player] {player_name}")

        if self.commentary_engine:
            self.commentary_engine.push(evt)

    def _write_game_summary(self) -> None:
        if self.metadata is None:
            return
        self.game_summary.write(self.summary_path, self.metadata)
        if not self.summary_written:
            print(f"[summary] Wrote game summary to: {self.summary_path}")
            self.summary_written = True

    def _update_lineup(self, event: NormalizedEvent) -> bool:
        team = str(event.team or "")
        players = event.raw.get("Players", [])
        current = {
            int(player["Id"]): self._short_player_name(player)
            for player in players
            if player.get("Id") is not None
            and player.get("IsCoach") is not True
            and player.get("IsStarter") is True
        }
        previous = self.lineups.get(team)
        self.lineups[team] = current
        if previous is None:
            return False

        added = [current[player_id] for player_id in current.keys() - previous.keys()]
        removed = [
            previous[player_id] for player_id in previous.keys() - current.keys()
        ]
        if not added and not removed:
            return False

        event.lineup_changes = {"added": sorted(added), "removed": sorted(removed)}
        return True

    @staticmethod
    def _short_player_name(player: dict) -> str:
        first_name = str(player.get("FirstName") or "").strip().split(maxsplit=1)
        last_name = str(player.get("LastName") or "").strip()
        return " ".join(
            part for part in (first_name[0] if first_name else "", last_name) if part
        )

    def _handle_match_data(self, raw_msg: dict, announce: bool = True):
        """Handle MatchData event containing rosters and match info."""
        try:
            self._cache_match_metadata(raw_msg)
            if self.match_ended:
                self._write_game_summary()
            self._announce_match_introduction()
            if not announce:
                return
            print("\n" + "=" * 60)
            print("📋 MATCH METADATA LOADED")
            print("=" * 60)
            print(self.metadata.to_summary())
            print("=" * 60 + "\n")
        except Exception as e:
            print(f"[error] Failed to parse match metadata: {e}")
            self._log_error("Match metadata handling failed", e)

    def get_connection_status(self) -> dict:
        """Get current connection status."""
        time_since_last_event = time.time() - self.last_event_time
        return {
            "connected": self.is_connected,
            "reconnect_count": self.reconnect_count,
            "seconds_since_last_event": int(time_since_last_event),
            "stale": time_since_last_event > 60,
        }

    def should_shutdown_after_match(self) -> bool:
        return (
            self.match_finished_at is not None
            and time.monotonic() >= self.match_finished_at
        )


# =========================
# Connection Monitor
# =========================


class ConnectionMonitor:
    """Monitor connection health and alert on issues."""

    def __init__(self, listener: MatchFeedListener, check_interval: int = 30):
        self.listener = listener
        self.check_interval = check_interval
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _monitor_loop(self):
        while self.running:
            time.sleep(self.check_interval)
            status = self.listener.get_connection_status()

            if not status["connected"]:
                print(
                    f"\n⚠️  [monitor] Not connected (reconnect attempts: {status['reconnect_count']})"
                )
            elif status["stale"]:
                print(
                    f"\n⚠️  [monitor] No events received for {status['seconds_since_last_event']} seconds"
                )


# =========================
# Main
# =========================


def build_pubnub() -> PubNub:
    """Build PubNub client with reconnection settings."""
    config = PNConfiguration()
    config.subscribe_key = SUBSCRIBE_KEY
    config.uuid = f"basketsnakker-{int(time.time())}"

    # Reconnection settings
    config.reconnect_policy = PNReconnectionPolicy.LINEAR
    config.maximum_reconnection_retries = -1  # Infinite retries
    config.subscribe_request_timeout = 310
    config.connect_timeout = 30
    config.non_subscribe_request_timeout = 30
    config.daemon = True

    return PubNub(config)


def create_tts(language: str) -> Optional[BaseTTS]:
    """Create appropriate TTS for the platform."""
    system = platform.system()

    try:
        if system == "Windows":
            from wintts import WindowsTTS

            return WindowsTTS(language=language)
        elif system == "Darwin":  # macOS
            from macostts import MacOSTTS

            return MacOSTTS(language=language)
        elif system == "Linux":
            from linuxtts import LinuxTTS

            return LinuxTTS(
                model_path=None,
                volume=1.0,
                speed=1.0,
                use_cuda=False,
                language=language,
            )
        else:
            print(f"[warning] Unknown platform: {system}")
            return None
    except ImportError as e:
        print(f"[warning] Could not import TTS for {system}: {e}")
        return None


def main(
    match_id: int,
    silent: bool = False,
    language: str = "no",
    use_llm: bool = False,
    llm_model: str = "llama3.2:latest",
    llm_window_ms: int = 1200,
):
    pubnub = build_pubnub()
    normalizer = GeniusBasketballNormalizer()
    deduper = RecentEventDeduper(maxlen=500)
    tts = create_tts(language=language) if not silent else None
    game_clock = GameClock()

    # Listener first, engine after (engine needs metadata getter from listener)
    listener = MatchFeedListener(
        normalizer=normalizer,
        deduper=deduper,
        tts=tts,
        game_clock=game_clock,
        match_id=match_id,
        commentary_engine=None,
        language=language,
    )

    def on_commentary(spoken: str):
        print(f"[commentary] {spoken}")
        if tts:
            tts.speak(spoken)

    commentary_engine = BufferedCommentaryEngine(
        language=language,
        metadata_getter=listener.get_metadata,
        on_commentary=on_commentary,
        use_llm=use_llm,
        llm_model=llm_model,
        flush_window_ms=llm_window_ms,
        max_batch_size=4,
    )
    listener.commentary_engine = commentary_engine
    commentary_engine.start()

    channel = f"match:{match_id}:all"
    listener.bootstrap_history(pubnub, channel)

    pubnub.add_listener(listener)

    # Start connection monitor
    monitor = ConnectionMonitor(listener, check_interval=30)
    monitor.start()

    print(f"Subscribing to channel: {channel}")
    pubnub.subscribe().channels(channel).execute()

    print(f"Subscribed to match: {match_id}")
    print("Listening for events... (Ctrl+C to stop)")
    if use_llm:
        print(f"[llm] model={llm_model} | window={llm_window_ms}ms")

    game_clock.start_display()

    try:
        while True:
            if listener.should_shutdown_after_match():
                print("\n[match] Grace period complete; shutting down...")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        monitor.stop()
        commentary_engine.stop()
        game_clock.stop_display()
        listener.log_fp.close()
        listener.error_log_fp.close()
        pubnub.stop()
        print("Shutdown complete.")


if __name__ == "__main__":
    from argparse import ArgumentParser

    ap = ArgumentParser(
        description="Basketball match event listener and TTS commentator"
    )
    ap.add_argument("match_id", type=int, help="Match ID to subscribe to")
    ap.add_argument("--silent", action="store_true", help="Disable TTS output")
    ap.add_argument(
        "--language",
        type=str,
        default="no",
        choices=["no", "en"],
        help="Language for TTS/commentary (default: no)",
    )
    ap.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable LLM batched commentary using datasette-llm",
    )
    ap.add_argument(
        "--llm-model",
        type=str,
        default="llama3.2:latest",
        help="Model ID for `llm` (default: llama3.2:latest)",
    )
    ap.add_argument(
        "--llm-window-ms",
        type=int,
        default=1200,
        help="Batching window in milliseconds (default: 1200)",
    )

    args = ap.parse_args()
    main(
        match_id=args.match_id,
        silent=args.silent,
        language=args.language,
        use_llm=args.use_llm,
        llm_model=args.llm_model,
        llm_window_ms=args.llm_window_ms,
    )
