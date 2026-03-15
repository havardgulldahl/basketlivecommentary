import sys
import wave
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional

help = """
# Install piper-tts
pip install piper-tts

# Download Norwegian voice
python3 -m piper.download_voices no_NO-talesyntese-medium

# Optional: Install pyaudio for streaming (lower latency)
pip install pyaudio

# Install audio player (if not already installed)
sudo apt install alsa-utils  # for aplay

"""
try:
    from piper import PiperVoice
    from piper.voice import SynthesisConfig
except ImportError:
    print(help)
    sys.exit(1)

from tts import BaseTTS


class LinuxTTS(BaseTTS):
    """
    Text-to-speech for Linux using piper-tts Python API.
    """

    def __init__(
        self,
        language: str = "no",
        model_path: Optional[str] = None,
        volume: float = 1.0,
        speed: float = 1.0,
        use_cuda: bool = False,
    ):
        """
        Initialize Linux TTS with Piper.

        Args:
            language: Language code ("no" for Norwegian, "en" for English)
            model_path: Path to .onnx voice model. If None, tries to find Norwegian voice.
            volume: Volume level (0.0 to 1.0+)
            speed: Speech speed multiplier (1.0 = normal, 2.0 = twice as slow)
            use_cuda: Use GPU acceleration if available
        """
        self.language = language
        self.volume = volume
        self.speed = speed

        # Find or use provided model
        if model_path is None:
            model_path = self._find_language_voice(language)

        if not model_path or not os.path.exists(model_path):
            raise RuntimeError(
                f"No Piper voice model found for language '{language}'. Download Norwegian voice:\n"
                "  python3 -m piper.download_voices no_NO-talesyntese-medium\n"
                "Or specify model_path manually."
            )

        print(f"[tts] Loading Piper voice: {model_path}")
        self.voice = PiperVoice.load(model_path, use_cuda=use_cuda)

        # Configure synthesis
        self.syn_config = SynthesisConfig(
            volume=self.volume,
            length_scale=self.speed,
            noise_scale=1.0,
            noise_w_scale=1.0,
            normalize_audio=True,
        )

    def _find_language_voice(self, language: str) -> Optional[str]:
        """Try to find a voice model for the specified language in common locations."""
        # Common installation paths
        possible_paths = [
            Path.home() / ".local" / "share" / "piper-tts" / "voices",
            Path("/usr/share/piper-tts/voices"),
            Path("./voices"),
        ]

        # Look for models matching the specified language
        for base_path in possible_paths:
            if base_path.exists():
                for model_file in base_path.rglob("*.onnx"):
                    if language == "no" and (
                        "no" in model_file.name.lower()
                        or "norwegian" in model_file.name.lower()
                    ):
                        return str(model_file)
                    elif language == "en" and "en" in model_file.name.lower():
                        return str(model_file)

        return None

    def speak(self, text: str):
        """Speak the given text using Piper TTS."""
        if not text:
            return

        try:
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_path = tmp_file.name

            try:
                # Synthesize to WAV file
                with wave.open(tmp_path, "wb") as wav_file:
                    self.voice.synthesize_wav(
                        text, wav_file, syn_config=self.syn_config
                    )

                # Play the WAV file using aplay (or paplay for PulseAudio)
                self._play_wav(tmp_path)

            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            print(f"[tts] Failed to speak: {e}")

    def _play_wav(self, wav_path: str):
        """Play WAV file using available audio player."""
        # Try different audio players
        players = [
            ["aplay", wav_path],  # ALSA
            ["paplay", wav_path],  # PulseAudio
            ["ffplay", "-nodisp", "-autoexit", wav_path],  # ffmpeg
        ]

        for player_cmd in players:
            try:
                subprocess.run(
                    player_cmd,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue

        print("[tts] No audio player found (tried aplay, paplay, ffplay)")


class LinuxTTSStreaming:
    """
    Streaming version using Piper's synthesize method for lower latency.
    Requires pyaudio for audio playback.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        volume: float = 1.0,
        speed: float = 1.0,
        use_cuda: bool = False,
    ):
        """Initialize streaming TTS."""
        try:
            import pyaudio

            self.pyaudio = pyaudio
        except ImportError:
            raise RuntimeError(
                "pyaudio required for streaming TTS:\n"
                "  pip install pyaudio\n"
                "Or use LinuxTTS (non-streaming) instead."
            )

        self.volume = volume
        self.speed = speed

        # Find or use provided model
        if model_path is None:
            model_path = self._find_norwegian_voice()

        if not model_path or not os.path.exists(model_path):
            raise RuntimeError(
                "No Piper voice model found. Download Norwegian voice:\n"
                "  python3 -m piper.download_voices no_NO-talesyntese-medium"
            )

        print(f"[tts] Loading Piper voice: {model_path}")
        self.voice = PiperVoice.load(model_path, use_cuda=use_cuda)

        self.syn_config = SynthesisConfig(
            volume=self.volume,
            length_scale=self.speed,
            noise_scale=1.0,
            noise_w_scale=1.0,
            normalize_audio=True,
        )

        # Initialize audio output
        self.audio = self.pyaudio.PyAudio()
        self.stream = None

    def _find_norwegian_voice(self) -> Optional[str]:
        """Try to find a Norwegian voice model."""
        possible_paths = [
            Path.home() / ".local" / "share" / "piper-tts" / "voices",
            Path("/usr/share/piper-tts/voices"),
            Path("./voices"),
        ]

        for base_path in possible_paths:
            if base_path.exists():
                for model_file in base_path.rglob("*.onnx"):
                    if (
                        "no_" in model_file.name.lower()
                        or "norwegian" in model_file.name.lower()
                    ):
                        return str(model_file)

        return None

    def speak(self, text: str):
        """Speak the given text with streaming."""
        if not text:
            return

        try:
            for chunk in self.voice.synthesize(text, syn_config=self.syn_config):
                # Initialize stream on first chunk
                if self.stream is None:
                    self.stream = self.audio.open(
                        format=self.pyaudio.get_format_from_width(chunk.sample_width),
                        channels=chunk.sample_channels,
                        rate=chunk.sample_rate,
                        output=True,
                    )

                # Write audio data
                self.stream.write(chunk.audio_int16_bytes)

            # Close stream after speaking
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

        except Exception as e:
            print(f"[tts] Failed to speak: {e}")

    def __del__(self):
        """Clean up audio resources."""
        if self.stream:
            self.stream.close()
        if self.audio:
            self.audio.terminate()
