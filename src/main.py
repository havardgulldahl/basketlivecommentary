import json
import signal
import sys
import time
import threading
import platform
from collections import deque
from dataclasses import asdict
from typing import Optional
from datetime import datetime

from pubnub.callbacks import SubscribeCallback
from pubnub.enums import PNStatusCategory, PNReconnectionPolicy
from pubnub.pnconfig import PNConfiguration  # Fixed import
from pubnub.pubnub import PubNub

from normalizer import GeniusBasketballNormalizer, NormalizedEvent
from commentary import get_commentary
from game_clock import GameClock
from match_metadata import MatchMetadata
from tts import BaseTTS


# =========================
# Config
# =========================

SUBSCRIBE_KEY = "sub-c-fd40e2e6-8f2f-11e5-bd2a-02ee2ddab7fe"


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
        language: str = "no",
    ):
        super().__init__()
        self.normalizer = normalizer
        self.deduper = deduper
        self.game_clock = game_clock
        self.tts = tts
        self.language = language
        self.metadata: Optional[MatchMetadata] = None

        # Open log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = f"raw_events_{timestamp}.jsonl"
        self.log_fp = open(self.log_file, "w", encoding="utf-8")
        print(f"[log] Writing raw events to: {self.log_file}")

        # Connection state
        self.is_connected = False
        self.reconnect_count = 0
        self.last_event_time = time.time()

    def status(self, pubnub, status):
        """Handle connection status changes."""
        category = status.category

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
            print(f"\n✅ [network] Reconnected to PubNub")

        elif category == PNStatusCategory.PNDisconnectedCategory:
            self.is_connected = False
            print(f"\n⚠️  [network] Disconnected from PubNub")

        elif category == PNStatusCategory.PNUnexpectedDisconnectCategory:
            self.is_connected = False
            print(
                f"\n❌ [network] Unexpected disconnection - PubNub will auto-reconnect"
            )

        elif category == PNStatusCategory.PNConnectionError:
            self.is_connected = False
            self.reconnect_count += 1
            print(f"\n❌ [network] Connection error (attempt #{self.reconnect_count})")

        elif category == PNStatusCategory.PNReconnectionAttemptsExhausted:
            self.is_connected = False
            print(
                f"\n❌ [network] Reconnection attempts exhausted - manual restart may be needed"
            )

        elif category == PNStatusCategory.PNAccessDeniedCategory:
            print(f"\n❌ [network] Access denied - check your PubNub credentials")

        elif category == PNStatusCategory.PNTimeoutCategory:
            print(f"\n⚠️  [network] Request timeout")

        # Log all status events for debugging
        print(f"[status] {category.name}")

    def presence(self, pubnub, presence):
        pass

    def message(self, pubnub, message):
        """Handle incoming messages with heartbeat monitoring."""
        self.last_event_time = time.time()

        try:
            raw_msg = message.message

            # Log raw event
            self.log_fp.write(json.dumps(raw_msg, ensure_ascii=False) + "\n")
            self.log_fp.flush()

            # Check if this is match metadata
            if (
                isinstance(raw_msg, dict)
                and raw_msg.get("MatchEventType") == "MatchData"
            ):
                self._handle_match_data(raw_msg)
                return  # Don't process MatchData as regular event

            # Normalize event
            evt = self.normalizer.normalize(raw_msg)
            if evt is None:
                print("[normalize] skipped: could not parse payload")
                return

            # Deduplicate
            if not self.deduper.is_new(evt):
                print(f"[dedupe] skipped duplicate: {evt.fingerprint}")
                return

            # Update game clock
            if evt.kind == "period":
                if evt.subtype == "start":
                    self.game_clock.start_period(evt.period or 1)
                elif evt.subtype == "end":
                    self.game_clock.end_period()
            elif evt.kind == "timer" and evt.clock:
                self.game_clock.update_clock(evt.clock)

            # Display event
            print(f"\n[event] {evt.kind} | {evt.subtype or ''}")
            if evt.description:
                print(f"  {evt.description}")

            # Enrich event with player names if metadata available
            if self.metadata and evt.player:
                player_name = self.metadata.get_player_display_name(evt.player)
                print(f"  [player] {player_name}")

            # Generate commentary
            spoken = get_commentary(evt, metadata=self.metadata, language=self.language)
            if spoken:
                print(f"[commentary] {spoken}")
                if self.tts:
                    self.tts.speak(spoken)
            else:
                print("[commentary] no spoken line for this event")

        except Exception as e:
            print(f"[error] message handling failed: {e}")
            import traceback

            traceback.print_exc()

    def _handle_match_data(self, raw_msg: dict):
        """Handle MatchData event containing rosters and match info."""
        try:
            self.metadata = MatchMetadata.from_raw(raw_msg)
            print("\n" + "=" * 60)
            print("📋 MATCH METADATA LOADED")
            print("=" * 60)
            print(self.metadata.to_summary())
            print("=" * 60 + "\n")
        except Exception as e:
            print(f"[error] Failed to parse match metadata: {e}")
            import traceback

            traceback.print_exc()

    def get_connection_status(self) -> dict:
        """Get current connection status."""
        time_since_last_event = time.time() - self.last_event_time
        return {
            "connected": self.is_connected,
            "reconnect_count": self.reconnect_count,
            "seconds_since_last_event": int(time_since_last_event),
            "stale": time_since_last_event > 60,  # No events for 60 seconds
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
        """Start monitoring in background thread."""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _monitor_loop(self):
        """Monitor connection status periodically."""
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


def main(match_id: int, silent: bool = False, language: str = "no"):
    pubnub = build_pubnub()
    normalizer = GeniusBasketballNormalizer()
    deduper = RecentEventDeduper(maxlen=500)
    tts = create_tts(language=language) if not silent else None
    game_clock = GameClock()
    listener = MatchFeedListener(normalizer, deduper, tts, game_clock, language=language)

    pubnub.add_listener(listener)

    # Start connection monitor
    monitor = ConnectionMonitor(listener, check_interval=30)
    monitor.start()

    channel = f"match:{match_id}:all"
    print(f"Subscribing to channel: {channel}")
    pubnub.subscribe().channels(channel).execute()

    print(f"Subscribed to match: {match_id}")
    print("Listening for events... (Ctrl+C to stop)")

    # Start clock display
    game_clock.start_display()

    try:
        # Keep main thread alive without blocking
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        monitor.stop()
        game_clock.stop_display()
        listener.log_fp.close()
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
        help="Language for TTS (default: no)",
    )
    args = ap.parse_args()
    main(args.match_id, silent=args.silent, language=args.language)
