# wintts.py
import threading
import queue

try:
    import pyttsx3
except ImportError:
    raise RuntimeError("pyttsx3 required for Windows TTS:\n" "  pip install pyttsx3")

from tts import BaseTTS


class WindowsTTS(BaseTTS):
    def __init__(self, test_mode: bool = False):
        """
        Initialize Windows TTS.

        Args:
            test_mode: If True, print debug info but don't actually speak
        """
        self.test_mode = test_mode
        self.voice_id = None

        if not test_mode:
            try:
                # Initialize once just to get voice info
                engine = pyttsx3.init()
                voices = engine.getProperty("voices")
                print(f"[wintts] Found {len(voices)} voices:")
                for i, voice in enumerate(voices):
                    print(f"  [{i}] {voice.name}")

                # Try to find Norwegian voice
                for voice in voices:
                    if (
                        "norwegian" in voice.name.lower()
                        or "norsk" in voice.name.lower()
                    ):
                        self.voice_id = voice.id
                        print(f"[wintts] Using Norwegian voice: {voice.name}")
                        break

                if not self.voice_id:
                    print("[wintts] No Norwegian voice found, using default")
                    self.voice_id = voices[0].id if voices else None

                # Clean up the test engine
                del engine

            except Exception as e:
                print(f"[wintts] Failed to initialize: {e}")
        else:
            print("[wintts] TEST MODE - will not actually speak")

        self.audio_queue = queue.Queue()
        self.running = True
        self.player_thread = threading.Thread(target=self._play_loop, daemon=True)
        self.player_thread.start()

    def speak(self, text: str):
        """Queue text for speaking."""
        self.audio_queue.put(text)

    def _play_loop(self):
        """Background thread that processes the audio queue."""
        print("[wintts] Play loop started")

        while self.running:
            try:
                text = self.audio_queue.get(timeout=1)
                print(f"[wintts] Got from queue: '{text}'")

                if self.test_mode:
                    print(f"[wintts] TEST MODE - would speak: '{text}'")
                else:
                    try:
                        import time

                        # Create fresh engine for each phrase
                        print(f"[wintts] Creating engine...")
                        engine = pyttsx3.init()

                        if self.voice_id:
                            engine.setProperty("voice", self.voice_id)

                        print(f"[wintts] Speaking: '{text}'")
                        engine.say(text)
                        engine.runAndWait()

                        # Wait a bit before destroying engine to avoid cut-off
                        time.sleep(0.3)  # 300ms buffer

                        # Clean up engine
                        del engine

                        print(f"[wintts] ✓ Finished speaking")
                    except Exception as e:
                        print(f"[wintts] ✗ Error during speech: {e}")
                        import traceback

                        traceback.print_exc()

                self.audio_queue.task_done()
                print(f"[wintts] Queue size: {self.audio_queue.qsize()}")

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[wintts] Error in play loop: {e}")
                import traceback

                traceback.print_exc()

        print("[wintts] Play loop exited")

    def stop(self):
        """Stop the TTS engine."""
        self.running = False


def test_tts():
    """Test the TTS engine with diagnostic output."""
    import time

    print("\n" + "=" * 60)
    print("Windows TTS Test")
    print("=" * 60 + "\n")

    print("Testing in NORMAL mode:\n")
    tts = WindowsTTS(test_mode=False)

    test_phrases = [
        "Testing one two three",
        "Skudd fra Johnsen",
        "Tre poeng for laget",
    ]

    for phrase in test_phrases:
        print(f"\n>>> Queuing: '{phrase}'")
        tts.speak(phrase)

    print("\n>>> Waiting for queue to finish (max 30 seconds)...")

    # Wait with timeout to avoid hanging forever
    start = time.time()
    while not tts.audio_queue.empty() and time.time() - start < 30:
        time.sleep(0.5)

    if tts.audio_queue.empty():
        print(">>> ✓ All phrases completed!\n")
    else:
        print(">>> ✗ Timeout waiting for queue\n")

    tts.stop()
    time.sleep(1)  # Give thread time to exit

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    test_tts()
