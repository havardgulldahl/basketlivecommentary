import pyttsx3
import threading
import queue


class WindowsTTS:
    def __init__(self):
        self.engine = pyttsx3.init()
        # Try to find Norwegian voice
        voices = self.engine.getProperty("voices")
        for voice in voices:
            if "norwegian" in voice.name.lower() or "norsk" in voice.name.lower():
                self.engine.setProperty("voice", voice.id)
                break

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
                self.engine.say(text)
                self.engine.runAndWait()
                self.audio_queue.task_done()
            except queue.Empty:
                continue
