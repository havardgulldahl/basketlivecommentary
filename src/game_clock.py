from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import threading
import time


@dataclass
class ClockState:
    """Current state of the game clock."""

    match_id: int
    period: int
    period_name: str
    period_time: str  # MM:SS format
    total_match_time: str  # MM:SS format
    time_seconds: int  # Seconds into period
    is_running: bool
    last_update: datetime


class GameClock:
    """
    Manages game clock state and displays running time.
    """

    def __init__(self):
        self.clocks: dict[int, ClockState] = {}
        self.lock = threading.Lock()
        self.display_thread: Optional[threading.Thread] = None
        self.running = False

    def update_from_timer_event(self, event: dict):
        """
        Update clock state from a Timer event.

        Expected fields:
        - MatchId
        - Period
        - PeriodName
        - PeriodTime (MM:SS)
        - TotalMatchTime (MM:SS)
        - Time (seconds)
        - Type (1=Start, 2=Stop, 3=Update)
        """
        if event.get("MatchEventType") != "Timer":
            return

        match_id = event.get("MatchId")
        if not match_id:
            return

        timer_type = event.get("Type")
        is_running = timer_type == 1  # 1 = Start, 2 = Stop

        with self.lock:
            self.clocks[match_id] = ClockState(
                match_id=match_id,
                period=event.get("Period", 0),
                period_name=event.get("PeriodName", ""),
                period_time=event.get("PeriodTime", "00:00"),
                total_match_time=event.get("TotalMatchTime", "00:00"),
                time_seconds=event.get("Time", 0),
                is_running=is_running,
                last_update=datetime.now(),
            )

    def get_current_time(self, match_id: int) -> Optional[str]:
        """Get current running time for a match."""
        with self.lock:
            clock = self.clocks.get(match_id)
            if not clock:
                return None

            if not clock.is_running:
                return clock.period_time

            # Calculate elapsed time since last update
            elapsed = (datetime.now() - clock.last_update).total_seconds()
            current_seconds = clock.time_seconds + int(elapsed)

            # Format as MM:SS
            minutes = current_seconds // 60
            seconds = current_seconds % 60
            return f"{minutes:02d}:{seconds:02d}"

    def start_display(self):
        """Start background thread to display clock updates."""
        if self.running:
            return

        self.running = True
        self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
        self.display_thread.start()

    def stop_display(self):
        """Stop the display thread."""
        self.running = False
        if self.display_thread:
            self.display_thread.join()

    def _display_loop(self):
        """Background loop to display running clocks."""
        while self.running:
            self._print_clocks()
            time.sleep(1)  # Update every second

    def _print_clocks(self):
        """Print current state of all clocks."""
        with self.lock:
            if not self.clocks:
                return

            # Clear screen (optional - comment out if you don't want this)
            # print("\033[2J\033[H", end="")

            print("\n" + "=" * 60)
            print("GAME CLOCKS")
            print("=" * 60)

            for match_id, clock in self.clocks.items():
                current_time = self.get_current_time(match_id)
                status = "▶ RUNNING" if clock.is_running else "⏸ STOPPED"

                print(f"\nMatch {match_id} - {clock.period_name}")
                print(f"  Period Time: {current_time} {status}")
                print(f"  Total Time:  {clock.total_match_time}")

            print("=" * 60 + "\n")

    def display_summary(self):
        """Display a one-time summary of all clocks."""
        self._print_clocks()
