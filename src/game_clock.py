from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import threading
import time
import sys


@dataclass
class ClockState:
    """Current state of the game clock."""

    period: int
    period_name: str
    clock_display: str  # MM:SS format
    clock_seconds: int  # Seconds remaining in period
    is_running: bool
    last_update: datetime


class GameClock:
    """
    Manages game clock state and displays running time.
    Tracks single match clock.
    """

    # Period ID to name mapping
    PERIOD_NAMES = {
        1: "Q1",
        2: "Q2",
        3: "Q3",
        4: "Q4",
        5: "OT1",
        6: "OT2",
    }

    def __init__(self):
        self.state: Optional[ClockState] = None
        self.lock = threading.Lock()
        self.display_thread: Optional[threading.Thread] = None
        self.running = False
        self.last_display_line = ""

    def start_period(self, period: int):
        """Start a new period."""
        with self.lock:
            period_name = self.PERIOD_NAMES.get(period, f"Period {period}")
            self.state = ClockState(
                period=period,
                period_name=period_name,
                clock_display="10:00",
                clock_seconds=600,
                is_running=True,
                last_update=datetime.now(),
            )
            print(f"\n🏀 [{period_name}] Period started")

    def end_period(self):
        """End the current period."""
        with self.lock:
            if self.state:
                self.state.is_running = False
                print(f"\n⏸️  [{self.state.period_name}] Period ended")

    def update_clock(self, clock_str: str):
        """
        Update clock from event (format: "MM:SS" or "M:SS").

        Args:
            clock_str: Clock string like "9:45" or "09:45"
        """
        with self.lock:
            if not self.state:
                return

            try:
                # Parse MM:SS format
                parts = clock_str.split(":")
                if len(parts) == 2:
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    total_seconds = minutes * 60 + seconds

                    self.state.clock_display = f"{minutes:02d}:{seconds:02d}"
                    self.state.clock_seconds = total_seconds
                    self.state.last_update = datetime.now()
                    self.state.is_running = True
            except (ValueError, IndexError) as e:
                print(f"[clock] Failed to parse clock: {clock_str} - {e}")

    def pause(self):
        """Pause the clock."""
        with self.lock:
            if self.state:
                self.state.is_running = False

    def resume(self):
        """Resume the clock."""
        with self.lock:
            if self.state:
                self.state.is_running = True
                self.state.last_update = datetime.now()

    def get_current_time(self) -> Optional[str]:
        """Get current clock display with running time calculation."""
        with self.lock:
            if not self.state:
                return None

            if not self.state.is_running:
                return self.state.clock_display

            # Calculate elapsed time since last update (clock counts DOWN)
            elapsed = (datetime.now() - self.state.last_update).total_seconds()
            current_seconds = max(0, self.state.clock_seconds - int(elapsed))

            # Format as MM:SS
            minutes = current_seconds // 60
            seconds = current_seconds % 60
            return f"{minutes:02d}:{seconds:02d}"

    def get_period(self) -> Optional[int]:
        """Get current period number."""
        with self.lock:
            return self.state.period if self.state else None

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
            self.display_thread.join(timeout=2)

        # Clear the last display line
        if self.last_display_line:
            print("\r" + " " * len(self.last_display_line) + "\r", end="", flush=True)

    def _display_loop(self):
        """Background loop to display running clock."""
        while self.running:
            self._print_clock()
            time.sleep(1)  # Update every second

    def _print_clock(self):
        """Print current clock state on single line (updates in place)."""
        with self.lock:
            if not self.state:
                return

            current_time = self.get_current_time()
            status = "▶️ " if self.state.is_running else "⏸️ "

            # Build display line
            display = f"🏀 [{self.state.period_name}] {status}{current_time}"

            # Clear previous line and print new one
            clear_space = " " * max(0, len(self.last_display_line) - len(display))
            print(f"\r{display}{clear_space}", end="", flush=True)

            self.last_display_line = display

    def display_summary(self):
        """Display a one-time summary of the clock."""
        with self.lock:
            if not self.state:
                print("⏰ No game clock data")
                return

            current_time = self.get_current_time()
            status = "RUNNING" if self.state.is_running else "STOPPED"

            print("\n" + "=" * 40)
            print(f"🏀 Game Clock - {self.state.period_name}")
            print("=" * 40)
            print(f"  Time:   {current_time}")
            print(f"  Status: {status}")
            print("=" * 40 + "\n")
