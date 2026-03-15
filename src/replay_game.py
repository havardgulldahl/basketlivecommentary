"""
Replay raw event logs for testing purposes.
"""

import json
import time
import sys
from pathlib import Path
from typing import Optional
from dataclasses import asdict

from normalizer import GeniusBasketballNormalizer, NormalizedEvent
from commentary import norwegian_commentary
from match_metadata import MatchMetadata
from tts import BaseTTS
import platform


class EventReplayer:
    """Replay events from a raw log file."""

    def __init__(
        self,
        log_file: str,
        tts: Optional[BaseTTS] = None,
        speed: float = 1.0,
        verbose: bool = True,
    ):
        """
        Initialize replayer.

        Args:
            log_file: Path to raw_events.jsonl file
            tts: Text-to-speech engine (optional)
            speed: Playback speed multiplier (1.0 = real-time, 2.0 = 2x speed, etc.)
            verbose: Print detailed event information
        """
        self.log_file = Path(log_file)
        self.tts = tts
        self.speed = speed
        self.verbose = verbose
        self.normalizer = GeniusBasketballNormalizer()
        self.metadata: Optional[MatchMetadata] = None

        if not self.log_file.exists():
            raise FileNotFoundError(f"Log file not found: {log_file}")

    def replay(self, start_from: int = 0, max_events: Optional[int] = None):
        """
        Replay events from the log file.

        Args:
            start_from: Skip this many events at the beginning
            max_events: Maximum number of events to replay (None = all)
        """
        print(f"\n{'='*60}")
        print(f"Replaying: {self.log_file}")
        print(f"Speed: {self.speed}x")
        if start_from > 0:
            print(f"Starting from event #{start_from}")
        if max_events:
            print(f"Max events: {max_events}")
        print(f"{'='*60}\n")

        events_processed = 0
        events_skipped = 0
        last_timestamp = None

        with open(self.log_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                # Skip empty lines
                if not line.strip():
                    continue

                # Skip events before start_from
                if events_processed + events_skipped < start_from:
                    events_skipped += 1
                    continue

                # Stop if max_events reached
                if max_events and events_processed >= max_events:
                    print(f"\n[replay] Reached max events ({max_events})")
                    break

                try:
                    raw_msg = json.loads(line)

                    # Handle MatchData to load metadata
                    if (
                        isinstance(raw_msg, dict)
                        and raw_msg.get("MatchEventType") == "MatchData"
                    ):
                        self._handle_match_data(raw_msg)
                        events_processed += 1
                        continue

                    # Normalize event
                    evt = self.normalizer.normalize(raw_msg)
                    if evt is None:
                        if self.verbose:
                            print(f"[line {line_num}] Could not parse event")
                        continue

                    # Calculate delay based on timestamps
                    current_timestamp = raw_msg.get("ServerTimeStamp")
                    if last_timestamp and current_timestamp and self.speed > 0:
                        delay = self._calculate_delay(last_timestamp, current_timestamp)
                        if delay > 0:
                            time.sleep(delay / self.speed)
                    last_timestamp = current_timestamp

                    # Display event
                    self._display_event(evt, line_num)

                    # Generate and speak commentary
                    spoken = norwegian_commentary(evt, self.metadata)
                    if spoken:
                        print(f"  💬 {spoken}")
                        if self.tts:
                            self.tts.speak(spoken)

                    events_processed += 1

                except json.JSONDecodeError as e:
                    print(f"[line {line_num}] JSON decode error: {e}")
                except KeyboardInterrupt:
                    print("\n\n[replay] Interrupted by user")
                    break
                except Exception as e:
                    print(f"[line {line_num}] Error processing event: {e}")
                    if self.verbose:
                        import traceback

                        traceback.print_exc()

        print(f"\n{'='*60}")
        print(f"Replay complete!")
        print(f"Events processed: {events_processed}")
        if events_skipped > 0:
            print(f"Events skipped: {events_skipped}")
        print(f"{'='*60}\n")

    def _handle_match_data(self, raw_msg: dict):
        """Handle MatchData event to load metadata."""
        try:
            self.metadata = MatchMetadata.from_raw(raw_msg)
            print("\n" + "=" * 60)
            print("📋 MATCH METADATA LOADED")
            print("=" * 60)
            print(self.metadata.to_summary())
            print("=" * 60 + "\n")
        except Exception as e:
            print(f"[error] Failed to parse match metadata: {e}")

    def _calculate_delay(self, last_ts: str, current_ts: str) -> float:
        """Calculate delay in seconds between two timestamps."""
        try:
            from datetime import datetime

            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"

            # Try with timezone suffix
            if last_ts.endswith("+01:00") or last_ts.endswith("Z"):
                last_ts = last_ts.rstrip("Z").split("+")[0]
                current_ts = current_ts.rstrip("Z").split("+")[0]

            last_dt = datetime.strptime(last_ts.split(".")[0], "%Y-%m-%dT%H:%M:%S")
            current_dt = datetime.strptime(
                current_ts.split(".")[0], "%Y-%m-%dT%H:%M:%S"
            )

            delta = (current_dt - last_dt).total_seconds()
            # Cap delay at 10 seconds to avoid long pauses
            return min(delta, 10.0) if delta > 0 else 0
        except Exception:
            return 0

    def _display_event(self, evt: NormalizedEvent, line_num: int):
        """Display event information."""
        if not self.verbose:
            # Compact display
            time_str = f"[{evt.clock}]" if evt.clock else ""
            period_str = f"P{evt.period}" if evt.period else ""
            player_str = f"#{evt.player}" if evt.player else ""
            team_str = evt.team or ""

            if self.metadata and evt.player:
                player_str = self.metadata.get_player_display_name(evt.player)

            print(
                f"{time_str:8} {period_str:3} {team_str:1} {player_str:25} {evt.kind:10} {evt.subtype or ''}"
            )
        else:
            # Detailed display
            print(f"\n{'─'*60}")
            print(f"Line {line_num}: {evt.kind.upper()}")
            if evt.subtype:
                print(f"  Subtype: {evt.subtype}")
            if evt.team:
                team_name = (
                    self.metadata.get_team_name(evt.team) if self.metadata else evt.team
                )
                print(f"  Team: {team_name}")
            if evt.player:
                player_name = (
                    self.metadata.get_player_display_name(evt.player)
                    if self.metadata
                    else f"Player {evt.player}"
                )
                print(f"  Player: {player_name}")
            if evt.points:
                print(f"  Points: {evt.points}")
            if evt.period:
                print(f"  Period: {evt.period}")
            if evt.clock:
                print(f"  Clock: {evt.clock}")
            print(f"  Description: {evt.description}")


def create_tts() -> Optional[BaseTTS]:
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


def main():
    from argparse import ArgumentParser

    ap = ArgumentParser(description="Replay basketball match events from raw log file")
    ap.add_argument("log_file", type=str, help="Path to raw_events.jsonl file")
    ap.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Playback speed multiplier (1.0 = real-time, 2.0 = 2x, 0 = no delay)",
    )
    ap.add_argument(
        "--start-from",
        type=int,
        default=0,
        help="Skip this many events at the beginning",
    )
    ap.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Maximum number of events to replay",
    )
    ap.add_argument("--silent", action="store_true", help="Disable TTS output")
    ap.add_argument("--compact", action="store_true", help="Use compact output format")

    args = ap.parse_args()

    tts = None if args.silent else create_tts()

    replayer = EventReplayer(
        log_file=args.log_file,
        tts=tts,
        speed=args.speed,
        verbose=not args.compact,
    )

    try:
        replayer.replay(
            start_from=args.start_from,
            max_events=args.max_events,
        )
    except KeyboardInterrupt:
        print("\n\nReplay interrupted by user")
    except Exception as e:
        print(f"\nError during replay: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
