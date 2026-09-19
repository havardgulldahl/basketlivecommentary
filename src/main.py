import json
import time
import threading
import platform
import traceback
from collections import deque
from pathlib import Path
from typing import Optional
from datetime import datetime

from pubnub.callbacks import SubscribeCallback
from pubnub.enums import PNStatusCategory, PNReconnectionPolicy
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub

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
    def __init__(self, maxlen: int = 500):
        self.items = deque(maxlen=maxlen)
        self.set_items = set()

    def is_new(self, evt: NormalizedEvent) -> bool:
        """Check if event is new (not a duplicate)."""
        fingerprint = evt.fingerprint
        if fingerprint in self.set_items:
            return False

        if len(self.items) == self.items.maxlen:
            old = self.items.popleft()
            self.set_items.discard(old)

        self.items.append(fingerprint)
        self.set_items.add(fingerprint)
        return True


class ScoreTracker:
    def __init__(self, announce_every: int = 4):
        self.home_score = 0
        self.away_score = 0
        self.scoring_events = 0
        self.announce_every = announce_every

    def update(self, event: NormalizedEvent):
        if event.kind != "shot" or event.points is None:
            return
        if event.team == "H":
            self.home_score += event.points
        elif event.team == "A":
            self.away_score += event.points
        else:
            return

        self.scoring_events += 1
        event.home_score = self.home_score
        event.away_score = self.away_score
        event.score_announcement = self.scoring_events % self.announce_every == 0


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
        self.match_introduction_announced = False
        self.match_dir = Path("matchdata") / str(match_id)
        self.match_dir.mkdir(parents=True, exist_ok=True)

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

        if not self.deduper.is_new(evt):
            if announce:
                print(f"[dedupe] skipped duplicate: {evt.fingerprint}")
            return

        self.score_tracker.update(evt)

        if evt.kind == "period":
            if evt.subtype == "start":
                self.game_clock.start_period(evt.period or 1)
            elif evt.subtype == "end":
                self.game_clock.end_period()
        elif evt.kind == "timer" and evt.clock:
            self.game_clock.update_clock(evt.clock)

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

    def _handle_match_data(self, raw_msg: dict, announce: bool = True):
        """Handle MatchData event containing rosters and match info."""
        try:
            self._cache_match_metadata(raw_msg)
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
