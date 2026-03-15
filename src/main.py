import json
import signal
import sys
import time
from collections import deque
from dataclasses import asdict
import platform

from pubnub.callbacks import SubscribeCallback
from pubnub.enums import PNStatusCategory
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub

from normalizer import GeniusBasketballNormalizer, NormalizedEvent
from commentary import norwegian_commentary
from game_clock import GameClock
from tts import BaseTTS


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
# PubNub listener
# =========================


class MatchFeedListener(SubscribeCallback):
    def __init__(
        self,
        normalizer: GeniusBasketballNormalizer,
        deduper: RecentEventDeduper,
        tts: BaseTTS,
        game_clock: GameClock,
        log_file: str = "raw_events.jsonl",
    ):
        self.normalizer = normalizer
        self.deduper = deduper
        self.game_clock = game_clock
        self.tts = tts
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
            self.log_fp.flush()

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
                if self.tts:
                    self.tts.speak(spoken)
            else:
                print("[commentary] no spoken line for this event")

        except Exception as e:
            print(f"[error] message handling failed: {e}")
            import traceback

            traceback.print_exc()


# =========================
# Main
# =========================


def build_pubnub() -> PubNub:
    config = PNConfiguration()
    config.subscribe_key = SUBSCRIBE_KEY
    config.uuid = f"gpt54-listener-{int(time.time())}"
    return PubNub(config)


def create_tts() -> BaseTTS:
    """Create appropriate TTS for the platform."""
    system = platform.system()

    if system == "Windows":
        from wintts import WindowsTTS

        return WindowsTTS()
    elif system == "Darwin":  # macOS
        from macostts import MacOSTTS

        return MacOSTTS()
    elif system == "Linux":
        from linuxtts import LinuxTTS

        return LinuxTTS(
            model_path=None,
            volume=1.0,
            speed=1.0,
            use_cuda=False,
        )
    else:
        print(f"[warning] Unknown platform: {system}")
        return None


def main(match_id: int, silent: bool = False):
    pubnub = build_pubnub()
    normalizer = GeniusBasketballNormalizer()
    deduper = RecentEventDeduper(maxlen=500)
    tts = create_tts() if not silent else None
    game_clock = GameClock()
    listener = MatchFeedListener(normalizer, deduper, tts, game_clock)

    pubnub.add_listener(listener)

    channel = f"match:{match_id}:all"
    print(f"Subscribing to channel: {channel}")
    pubnub.subscribe().channels(channel).execute()

    print(f"Subscribed to match: {match_id}")
    print("Listening for events... (Ctrl+C to stop)")

    # Start clock display
    game_clock.start_display()

    def shutdown_handler(sig, frame):
        print("\nShutting down...")
        pubnub.unsubscribe_all()
        pubnub.stop()
        game_clock.stop_display()
        listener.log_fp.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    from argparse import ArgumentParser

    ap = ArgumentParser(
        description="Basketball match event listener and TTS commentator"
    )
    ap.add_argument("match_id", type=int, help="Match ID to subscribe to")
    ap.add_argument("--silent", action="store_true", help="Disable TTS output")
    args = ap.parse_args()
    main(args.match_id, silent=args.silent)
