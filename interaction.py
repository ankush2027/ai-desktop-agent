"""Presentation adapter for the existing text entry point; no agent logic."""

from contextlib import redirect_stdout
from dataclasses import dataclass
from enum import Enum
from io import StringIO
from threading import Event, Lock
from typing import Callable

from voice import UnavailableVoiceInput, VoiceInputProvider, VoiceOutputProvider


class InteractionState(str, Enum):
    IDLE = "Idle"
    LISTENING = "Listening"
    PROCESSING = "Processing"
    RESPONDING = "Responding"
    ERROR = "Error"


@dataclass(frozen=True)
class AgentReply:
    text: str
    succeeded: bool = True
    dismiss: bool = False


@dataclass(frozen=True)
class Presentation:
    state: InteractionState
    response: str = ""
    notice: str = ""
    dismiss: bool = False


# The legacy CLI prints its results. Serialize this compatibility bridge because
# redirect_stdout is process-global. Run the desktop UI as its own process.
_CORE_OUTPUT_LOCK = Lock()


def run_existing_core(text: str) -> AgentReply:
    """Invoke the public core once and adapt its existing terminal presentation.

    Diagnostic lines are not assistant responses. Do not serialize action plans,
    fabricate summaries, or reinterpret user input here. Memory/context replies
    already come from the core, including explicit user-requested retrieval.
    """
    from main import handle_command

    with _CORE_OUTPUT_LOCK, StringIO() as output, redirect_stdout(output):
        try:
            result = handle_command(text)
        except SystemExit as exc:
            return AgentReply("Goodbye!", dismiss=True) if exc.code in (None, 0) else AgentReply(
                "The agent could not complete that request.", False)
        except Exception:
            return AgentReply("The agent could not complete that request.", False)
        lines = [line for line in output.getvalue().splitlines()
                 if not line.startswith(("[AI]", "[LOG]"))]
        response = "\n".join(lines).strip()
        succeeded = bool(result)
        return AgentReply(response or ("Done." if succeeded else "The request did not complete."), succeeded)


class InteractionController:
    """One input at a time, one core entry point, transient presentation only.

    publish runs on the caller's thread. Desktop views must queue updates for
    their UI thread. Provider/core injection is for embedding and isolated tests.
    """

    def __init__(self, publish: Callable[[Presentation], None], *,
                 voice_input: VoiceInputProvider | None = None,
                 voice_output: VoiceOutputProvider | None = None,
                 core: Callable[[str], AgentReply] = run_existing_core):
        self._publish = publish
        self._voice_input = voice_input if voice_input is not None else UnavailableVoiceInput()
        self._voice_output = voice_output
        self._core = core
        self._busy = Lock()
        self._cancel = Event()
        self._dismissed = Event()

    def cancel_listening(self):
        """Also suppresses late transcripts; cannot undo already dispatched work."""
        self._cancel.set()

    def dismiss(self):
        """Close this interaction session, including captures not started yet."""
        self._dismissed.set()
        self._cancel.set()

    def submit_text(self, text: str, *, speak: bool = False):
        if not self._busy.acquire(blocking=False):
            return False
        try:
            return self._submit(text, speak)
        finally:
            self._busy.release()

    def submit_voice(self, *, speak: bool = False):
        if not self._busy.acquire(blocking=False):
            return False
        try:
            self._cancel.clear()
            if self._dismissed.is_set():
                return False
            self._publish(Presentation(InteractionState.LISTENING))
            try:
                text = self._voice_input.recognize(self._cancel)
            except Exception:
                if self._cancel.is_set():
                    self._publish(Presentation(InteractionState.IDLE, notice="Listening cancelled."))
                else:
                    self._publish(Presentation(InteractionState.ERROR,
                                               notice="Voice input is unavailable. Type your command instead."))
                return False
            if self._cancel.is_set() or self._dismissed.is_set():
                self._publish(Presentation(InteractionState.IDLE, notice="Listening cancelled."))
                return False
            return self._submit(text, speak)
        finally:
            self._busy.release()

    def _submit(self, text, speak):
        if self._dismissed.is_set():
            return False
        if not isinstance(text, str) or not text.strip():
            self._publish(Presentation(InteractionState.ERROR, notice="Enter a command or try speaking again."))
            return False
        self._publish(Presentation(InteractionState.PROCESSING))
        if self._dismissed.is_set():
            return False
        try:
            reply = self._core(text)  # Identical path and unchanged text for both sources.
            if not isinstance(reply, AgentReply) or not isinstance(reply.text, str):
                raise TypeError("Invalid core reply")
        except Exception:
            reply = AgentReply("The agent could not complete that request.", False)
        if not reply.succeeded:
            self._publish(Presentation(InteractionState.ERROR, response=reply.text))
            return False
        self._publish(Presentation(InteractionState.RESPONDING, response=reply.text))
        if self._dismissed.is_set():
            return reply.succeeded
        if speak and self._voice_output is not None:
            try:
                self._voice_output.speak(reply.text)
            except Exception:
                self._publish(Presentation(InteractionState.ERROR, response=reply.text,
                                           notice="Voice output failed. Your text result is still available.",
                                           dismiss=reply.dismiss))
                return True  # Action success is independent of optional speech.
        elif speak:
            self._publish(Presentation(InteractionState.IDLE, response=reply.text,
                                       notice="Voice output is not configured.", dismiss=reply.dismiss))
            return True
        self._publish(Presentation(InteractionState.IDLE, response=reply.text, dismiss=reply.dismiss))
        return True
