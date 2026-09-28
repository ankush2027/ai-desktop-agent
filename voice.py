"""Replaceable, opt-in speech boundaries. No audio backend is installed here."""

from threading import Event
from typing import Protocol


class VoiceInputError(RuntimeError):
    """Recognition could not produce usable text."""


class VoiceInputFailure(VoiceInputError):
    """Fixed public notices; never expose backend exception text to the UI."""

    NOTICES = {
        "dependencies": "Install requirements-voice.txt to enable local voice. See VOICE_SETUP.md.",
        "model": "Voice model missing or incomplete. Run python provision_voice.py with your venv. See VOICE_SETUP.md.",
        "cache": "The voice model cache must be outside the repository. See VOICE_SETUP.md.",
        "load": "The local voice model could not load. Check the voice installation and model cache.",
        "device": "Microphone unavailable or unsupported. Check the default input device and microphone permission.",
        "audio": "Microphone audio was interrupted. Check the device and try again.",
        "empty": "No speech recognized. Try again or type your command.",
        "duration": "Speech exceeded the capture limit. Try a shorter command.",
        "transcription": "Local transcription failed. Try again or type your command.",
        "busy": "A voice request is already running.",
    }

    def __init__(self, code):
        self.notice = self.NOTICES.get(code, "Voice input is unavailable. Type your command instead.")
        super().__init__(self.notice)


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
