import json
import re
import sys
import threading
import time
from typing import Callable, List, Optional

from commentary import get_commentary, get_score_commentary
from match_metadata import MatchMetadata
from normalizer import NormalizedEvent

# Markers the local instruct model sometimes emits when it keeps generating
# past the answer (special tokens, or a hallucinated new conversation turn).
_STOP_MARKERS = [
    "<|endoftext|>",
    "<|im_end|>",
    "<|im_start|>",
    "\nHuman:",
    "\nUser:",
    "\nSystem:",
    "Human:",
    "User:",
]


_gpt4all_suppress_output_patched = False


def _patch_gpt4all_suppress_output() -> None:
    """
    Work around a llm-gpt4all bug: SuppressOutput.__enter__ wraps duplicated
    stdout/stderr file descriptors in TextIOWrapper objects (which take
    ownership of the fd and close it when garbage collected), then
    __exit__ *also* closes those same raw fds directly via os.close(). The
    resulting double-close makes Python print a harmless but noisy
    "Exception ignored while finalizing file ... Bad file descriptor" once
    the wrapper is later garbage collected. Closing the wrapper itself
    (which closes its fd exactly once) instead of calling os.close() again
    avoids the double close.
    """
    global _gpt4all_suppress_output_patched
    if _gpt4all_suppress_output_patched:
        return
    _gpt4all_suppress_output_patched = True

    try:
        import os

        import llm_gpt4all  # type: ignore
    except Exception:
        return

    suppress_cls = getattr(llm_gpt4all, "SuppressOutput", None)
    if suppress_cls is None:
        return

    def patched_exit(self, exc_type, exc_val, exc_tb):
        # Restore the real stdout/stderr file descriptors first.
        os.dup2(self.stdout_fd, 1)
        os.dup2(self.stderr_fd, 2)

        # Close the duplicated fds via the wrappers that already own them,
        # instead of the original os.close(self.stdout_fd/self.stderr_fd),
        # which would close an fd a live TextIOWrapper still thinks it owns.
        for wrapper in (sys.stdout, sys.stderr):
            try:
                wrapper.close()
            except Exception:
                pass

        os.close(self.devnull_fd)

        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

    suppress_cls.__exit__ = patched_exit


def _clean_llm_output(text: str) -> Optional[str]:
    """Trim model chatter/control tokens down to a single spoken line."""
    cleaned = text
    for marker in _STOP_MARKERS:
        idx = cleaned.find(marker)
        if idx != -1:
            cleaned = cleaned[:idx]

    # Only the first line is ever spoken.
    cleaned = cleaned.strip().splitlines()[0] if cleaned.strip() else ""
    cleaned = cleaned.strip().strip('"').strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    # The small local model tends to ramble past the requested single
    # sentence; keep only the first one instead of the whole continuation.
    match = re.match(r"(.{8,}?[.!?])(\s|$)", cleaned)
    if match:
        cleaned = match.group(1)

    return cleaned or None


class LLMBatchCommentator:
    """
    Generate one natural commentary line for a short sequence of events
    using https://llm.datasette.io/ Python API.
    """

    def __init__(self, language: str = "no", model: str = "qwen2-1_5b-instruct-q4_0"):
        self.language = language
        self.model_id = model
        self.enabled = False
        self.model = None
        self.llm = None

        try:
            import llm  # type: ignore

            self.llm = llm
            self.model = llm.get_model(self.model_id)
            self._patch_chat_template(self.model)
            _patch_gpt4all_suppress_output()
            self.enabled = True
            print(f"[llm] enabled via datasette-llm, model={self.model_id}")
        except Exception as e:
            print(f"[llm] could not initialize model '{self.model_id}': {e}")
            print("[llm] LLM commentary disabled; deterministic fallback will be used.")

    @staticmethod
    def _patch_chat_template(model) -> None:
        """
        Work around a llm-gpt4all bug: for ChatML-style templates (containing
        a "%2" placeholder for the not-yet-generated assistant reply), the
        plugin leaves the literal "%2<|im_end|>" in the prompt sent to the
        model. That premature end-of-turn token confuses the model into
        immediately hallucinating a new conversation instead of answering.
        Truncating the template at "%2" fixes single-turn (non-conversation)
        prompts, which is all this class uses.
        """
        prompt_template = getattr(model, "prompt_template", None)
        if not callable(prompt_template):
            return
        try:
            template = prompt_template()
        except Exception:
            return
        if "%2" not in template:
            return
        fixed_template = template.split("%2")[0]
        model.prompt_template = lambda: fixed_template

    def _event_to_context(
        self, evt: NormalizedEvent, metadata: Optional[MatchMetadata]
    ) -> dict:
        # Only send fields that are safe/useful to speak. In particular,
        # omit the raw numeric player id, the raw "H"/"A" team code, and the
        # untranslated raw payload dict, so the model has nothing copyable
        # to leak instead of the resolved player_name/team_name.
        payload = {
            "kind": evt.kind,
            "subtype": evt.subtype,
            "points": evt.points,
            "period": evt.period,
            "clock": evt.clock,
            "player_name": (
                metadata.get_player_display_name(evt.player)
                if metadata and evt.player
                else None
            ),
            "team_name": (
                metadata.get_team_name(evt.team) if metadata and evt.team else None
            ),
        }
        return payload

    def generate(
        self, events: List[NormalizedEvent], metadata: Optional[MatchMetadata]
    ) -> Optional[str]:
        if not self.enabled or not self.model or not events:
            return None

        language_label = "Norwegian" if self.language == "no" else "English"
        events_payload = [self._event_to_context(e, metadata) for e in events]

        system_prompt = (
            f"You are a live basketball commentator. Respond only in {language_label}. "
            "You receive a SHORT sequence of consecutive structured events as JSON. "
            "Return EXACTLY ONE short natural spoken sentence that combines them coherently. "
            "Keep it concise and vivid, one sentence, under 25 words. "
            "Do not invent facts not present in the events. "
            "Never speak raw player IDs, team codes, or jersey numbers; "
            "use player_name/team_name only if provided, otherwise omit the name. "
            "If events are causally linked (e.g., missed free throw and rebound), "
            "merge them naturally into one line. "
            "Reply with the sentence only: no JSON, no labels, no quotes, no bullet points, "
            "no repeating the input, and do not continue the conversation afterwards."
        )

        user_prompt = json.dumps(
            {
                "language": language_label,
                "task": "Generate one short live commentary sentence.",
                "events": events_payload,
            },
            ensure_ascii=False,
        )
        # Small local models follow a language instruction placed right at
        # the end of the prompt far more reliably than one buried earlier.
        language_cue = (
            "\n\nSkriv svaret kun på norsk:"
            if self.language == "no"
            else "\n\nReply only in English:"
        )
        user_prompt += language_cue

        try:
            response = self.model.prompt(
                user_prompt,
                system=system_prompt,
                temp=0.4,
                max_tokens=45,
            )
            raw_text = (
                response.text().strip()
                if hasattr(response, "text")
                else str(response).strip()
            )
            return _clean_llm_output(raw_text) if raw_text else None
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
        llm_model: str = "qwen2-1_5b-instruct-q4_0",
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
            (
                event
                for event in reversed(batch)
                if event.score_announcement
                or event.score_time_announcement
                or event.final_summary
            ),
            None,
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
