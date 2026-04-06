import subprocess
import threading
import queue

from tts import BaseTTS


class MacOSTTS(BaseTTS):
    def __init__(self, language: str = "no", test_mode: bool = False):
        """
        Initialize macOS TTS.

        Args:
            language: Language code ("no" for Norwegian uses Nora voice, "en" for English uses Alex voice)
            test_mode: If True, print debug info but don't actually speak
        """
        self.voice = "Nora" if language == "no" else "Alex"
        self.language = language
        self.test_mode = test_mode

        if test_mode:
            print("[macostts] TEST MODE - will not actually speak")

        self.audio_queue = queue.Queue()
        self.running = True
        self.player_thread = threading.Thread(target=self._play_loop, daemon=True)
        self.player_thread.start()

    def speak(self, text: str):
        """Queue text for speaking."""
        self.audio_queue.put(text)

    def _play_loop(self):
        """Background thread that processes the audio queue."""
        while self.running:
            try:
                text = self.audio_queue.get(timeout=1)
                if self.test_mode:
                    print(f"[macostts] TEST MODE - would speak: '{text}'")
                else:
                    print(f"[audio] Speaking: {text}")
                    subprocess.run(["say", "-v", self.voice, text])
                self.audio_queue.task_done()
            except queue.Empty:
                continue

    def stop(self):
        """Stop the TTS engine."""
        self.running = False


def test_tts():
    """Test the TTS engine with diagnostic output."""
    import time

    print("\n" + "=" * 60)
    print("macOS TTS Test")
    print("=" * 60 + "\n")

    print("Testing in TEST MODE:\n")
    tts = MacOSTTS(test_mode=True)

    test_phrases = [
        "Testing one two three",
        "Skudd fra Johnsen",
        "Tre poeng for laget",
    ]

    for phrase in test_phrases:
        print(f"\n>>> Queuing: '{phrase}'")
        tts.speak(phrase)

    print("\n>>> Waiting for queue to finish (max 10 seconds)...")

    start = time.time()
    while not tts.audio_queue.empty() and time.time() - start < 10:
        time.sleep(0.5)

    if tts.audio_queue.empty():
        print(">>> ✓ All phrases completed!\n")
    else:
        print(">>> ✗ Timeout waiting for queue\n")

    tts.stop()
    time.sleep(0.5)

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    test_tts()
