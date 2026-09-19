import json
import threading
import time
from dataclasses import asdict
from typing import Callable, List, Optional

from commentary import get_commentary, get_score_commentary
from match_metadata import MatchMetadata
from normalizer import NormalizedEvent


class LLMBatchCommentator:
    """
    Generate one natural commentary line for a short sequence of events
    using https://llm.datasette.io/ Python API.
    """

    def __init__(self, language: str = "no", model: str = "llama3.2:latest"):
        self.language = language
        self.model_id = model
        self.enabled = False
        self.model = None
        self.llm = None

        try:
            import llm  # type: ignore

            self.llm = llm
            self.model = llm.get_model(self.model_id)
            self.enabled = True
            print(f"[llm] enabled via datasette-llm, model={self.model_id}")
        except Exception as e:
            print(f"[llm] could not initialize model '{self.model_id}': {e}")
            print("[llm] LLM commentary disabled; deterministic fallback will be used.")

    def _event_to_context(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> dict:
        payload = asdict(evt)

        # Enrich with display names to improve phrasing quality
        if metadata and evt.player:
            payload["player_name"] = metadata.get_player_display_name(evt.player)
        else:
            payload["player_name"] = None

        if metadata and evt.team:
            payload["team_name"] = metadata.get_team_name(evt.team)
        else:
            payload["team_name"] = None

        return payload

    def generate(
        self, events: List[NormalizedEvent], metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        if not self.enabled or not self.model or not events:
            return None

        language_label = "Norwegian" if self.language == "no" else "English"
        events_payload = [self._event_to_context(e, metadata) for e in events]

        system_prompt = (
            "You are a live basketball commentator. "
            "You receive a SHORT sequence of consecutive structured events. "
            "Return EXACTLY ONE natural spoken line that combines them coherently. "
            "Keep it concise and vivid. "
            "Do not invent facts not present in the events. "
            "Never speak raw player IDs or jersey numbers unless a verified player_name is provided. "
            "If events are causally linked (e.g., missed free throw and timer start), "
            "merge them naturally into one line. "
            "No bullet points. No surrounding quotes."
        )

        user_prompt = json.dumps(
            {
                "language": language_label,
                "task": "Generate one short live commentary sentence.",
                "events": events_payload,
            },
            ensure_ascii=False,
        )

        try:
            response = self.model.prompt(
                user_prompt,
                system=system_prompt,
            )
            text = (
                response.text().strip()
                if hasattr(response, "text")
                else str(response).strip()
            )
            return text or None
        except Exception as e:
            print(f"[llm] generation failed ({self.model_id}): {e}")
            return None


class BufferedCommentaryEngine:
    """
    Micro-batches events over a short window so commentary can combine
    related events into one natural line.
    """

    def __init__(
        self,
        language: str,
        metadata_getter: Callable[[], Optional[MatchMetadata]],
        on_commentary: Callable[[str], None],
        use_llm: bool = False,
        llm_model: str = "llama3.2:latest",
        flush_window_ms: int = 1200,
        max_batch_size: int = 4,
    ):
        self.language = language
        self.metadata_getter = metadata_getter
        self.on_commentary = on_commentary

        self.use_llm = use_llm
        self.flush_window_ms = flush_window_ms
        self.max_batch_size = max_batch_size

        self.llm = (
            LLMBatchCommentator(language=language, model=llm_model) if use_llm else None
        )

        self.buffer: List[NormalizedEvent] = []
        self.last_event_ts = 0.0
        self.lock = threading.Lock()
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.flush_now()

    def push(self, evt: NormalizedEvent):
        batch = None
        with self.lock:
            self.buffer.append(evt)
            self.last_event_ts = time.time()

            if len(self.buffer) >= self.max_batch_size:
                batch = self.buffer[:]
                self.buffer.clear()

        if batch:
            self._emit_batch(batch)

    def flush_now(self):
        with self.lock:
            if not self.buffer:
                return
            batch = self.buffer[:]
            self.buffer.clear()
        self._emit_batch(batch)

    def _loop(self):
        while self.running:
            time.sleep(0.05)

            with self.lock:
                if not self.buffer:
                    continue

                elapsed_ms = (time.time() - self.last_event_ts) * 1000.0
                if elapsed_ms < self.flush_window_ms:
                    continue

                batch = self.buffer[:]
                self.buffer.clear()

            self._emit_batch(batch)

    def _emit_batch(self, batch: List[NormalizedEvent]):
        metadata = self.metadata_getter()

        spoken = None

        # 1) LLM line over the full batch
        if self.use_llm and self.llm:
            spoken = self.llm.generate(batch, metadata)

        # 2) Deterministic fallback from existing commentary.py
        if not spoken:
            lines = []
            for evt in batch:
                line = get_commentary(evt, metadata=metadata, language=self.language)
                if line:
                    if not lines or lines[-1] != line:
                        lines.append(line)
            if lines:
                spoken = " ".join(lines)

        score_event = next(
            (event for event in reversed(batch) if event.score_announcement), None
        )
        if score_event:
            score_line = get_score_commentary(
                score_event, metadata=metadata, language=self.language
            )
            if score_line and (not spoken or score_line not in spoken):
                spoken = f"{spoken} {score_line}" if spoken else score_line

        if spoken:
            self.on_commentary(spoken)
        else:
            print("[commentary] no spoken line for this batch")
