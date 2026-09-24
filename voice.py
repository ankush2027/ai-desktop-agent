"""Replaceable, opt-in speech boundaries. No audio backend is installed here."""

from threading import Event
from typing import Protocol


class VoiceInputError(RuntimeError):
    """Recognition could not produce usable text."""


class VoiceOutputError(RuntimeError):
    """Speech output failed; the visible response must remain available."""


class VoiceInputProvider(Protocol):
    def recognize(self, cancel: Event) -> str:
        """Capture one explicitly requested utterance and return ordinary text.

        Implementations must bound capture time, honor cancellation, and release
        the microphone in a finally block. Never persist audio or log transcripts.
        No hardware access is allowed during construction/import. A cancelled
        capture must not dispatch a command, even if recognition completes late.
        """
        ...


class VoiceOutputProvider(Protocol):
    def speak(self, response: str) -> None:
        """Speak only the final response, with bounded duration and no storage."""
        ...


class UnavailableVoiceInput:
    def recognize(self, cancel: Event) -> str:
        raise VoiceInputError("Voice input is not configured.")


class UnavailableVoiceOutput:
    def speak(self, response: str) -> None:
        raise VoiceOutputError("Voice output is not configured.")
