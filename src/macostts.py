import subprocess
import threading
import queue

from tts import BaseTTS


class MacOSTTS(BaseTTS):
    def __init__(self, language: str = "no"):  # Nora is Norwegian voice
        self.voice = "Nora" if language == "no" else "Alex"
        self.language = language
        self.audio_queue = queue.Queue()
        self.player_thread = threading.Thread(target=self._play_loop, daemon=True)
        self.player_thread.start()

    def speak(self, text: str):
        self.audio_queue.put(text)

    def _play_loop(self):
        while True:
            try:
                text = self.audio_queue.get(timeout=1)
                print(f"[audio] Speaking: {text}")
                subprocess.run(["say", "-v", self.voice, text])
                self.audio_queue.task_done()
            except queue.Empty:
                continue
