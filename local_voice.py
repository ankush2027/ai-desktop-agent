"""One explicit, bounded microphone capture -> local English text. No agent I/O."""

from collections import deque
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock
from time import monotonic

from voice import VoiceInputError, VoiceInputFailure
from voice_model import model_snapshot

SAMPLE_RATE = 16000
BLOCK_SECONDS = 0.02
POLL_SECONDS = 0.05
PRE_ROLL_SECONDS = 0.2
QUEUE_BLOCKS = 50
MIN_SPEECH_SECONDS = 0.1
MIN_SPEECH_RMS = 0.001
INITIAL_NOISE_RMS = 0.0003

# Detect macOS via a well-known filesystem sentinel so that sounddevice's
# platform-specific callback behaviour (Core Audio vs WASAPI/DirectSound) can
# be handled without importing sys, os, or platform — none of which appear in
# the allowed-dependency list for this module (see test_local_voice.py).
_IS_MACOS = Path("/System/Library/CoreServices/SystemVersion.plist").is_file()
# Number of 20 ms audio blocks used as a noise-floor calibration window before
# VAD onset detection begins.  On macOS, Core Audio hardware has a higher
# ambient noise floor than Windows WASAPI/DirectSound (~0.00445 vs <0.001 RMS),
# which causes INITIAL_NOISE_RMS (0.0003) to be too low and immediately
# triggers false speech onset.  300 ms (15 blocks) is enough for noise_rms
# to converge well above INITIAL_NOISE_RMS before any onset gate fires.
# Windows retains 0 (no calibration window, identical to original behaviour).
DEFAULT_CAL_BLOCKS: int = 15 if _IS_MACOS else 0


@dataclass(frozen=True)
class CaptureConfig:
    speech_start_timeout: float = 5.0
    max_utterance_duration: float = 15.0
    silence_duration: float = 0.8
    speech_threshold: float = 0.015  # Upper bound for the adaptive onset threshold.
    # Number of audio blocks consumed as a noise-floor calibration pass before
    # onset detection begins.  On macOS, Core Audio hardware typically has a
    # higher ambient noise floor than Windows WASAPI/DirectSound, so
    # INITIAL_NOISE_RMS (0.0003) underestimates the true floor.  A non-zero
    # value (e.g. 15 = 300 ms at 20 ms/block) lets noise_rms converge before
    # any onset gate is applied.  Default 0 preserves existing behaviour on
    # Windows and in all offline tests that use scripted audio events.
    calibration_blocks: int = 0

    def __post_init__(self):
        for value, maximum in ((self.speech_start_timeout, 30),
                               (self.max_utterance_duration, 60),
                               (self.silence_duration, 5), (self.speech_threshold, 1)):
            if not isfinite(value) or not 0 < value <= maximum:
                raise ValueError("Capture settings must be finite, positive, and within safe bounds.")
        if self.silence_duration >= self.max_utterance_duration:
            raise ValueError("Silence duration must be shorter than the utterance limit.")
        if not isinstance(self.calibration_blocks, int) or not 0 <= self.calibration_blocks <= 500:
            raise ValueError("Capture settings must be finite, positive, and within safe bounds.")


def check_cancel(cancel):
    if cancel.is_set():
        raise VoiceInputError("Listening cancelled.")


class LocalVoiceInput:
    def __init__(self, config=None):
        self.config = config if config is not None else CaptureConfig()
        self._model = None
        self._busy = Lock()

    def recognize(self, cancel):
        check_cancel(cancel)
        if not self._busy.acquire(blocking=False):
            raise VoiceInputFailure("busy")
        try:
            try:
                import numpy as np
                import sounddevice as sd
                from faster_whisper import WhisperModel
            except Exception:
                raise VoiceInputFailure("dependencies") from None
            check_cancel(cancel)
            if self._model is None:
                path = model_snapshot()
                check_cancel(cancel)
            audio = self._capture(cancel, sd, np)
            check_cancel(cancel)
            if self._model is None:
                try:
                    self._model = WhisperModel(str(path), device="cpu", compute_type="int8",
                                               local_files_only=True, num_workers=1)
                except Exception:
                    raise VoiceInputFailure("load") from None
            check_cancel(cancel)
            try:
                segments, _ = self._model.transcribe(
                    audio, language="en", task="transcribe", beam_size=5,
                    vad_filter=True, condition_on_previous_text=False,
                )
                text = []
                for segment in segments:  # Native inference is lazy, inside this iterator.
                    check_cancel(cancel)
                    text.append(segment.text)
                check_cancel(cancel)
                result = " ".join(text).strip()
            except VoiceInputError:
                raise
            except Exception:
                raise VoiceInputFailure("transcription") from None
            if not result:
                raise VoiceInputFailure("empty")
            return result
        finally:
            self._busy.release()

    def _capture(self, cancel, sd, np):
        cfg = self.config
        blocks = Queue(maxsize=QUEUE_BLOCKS)
        failed = Event()
        frames = int(SAMPLE_RATE * BLOCK_SECONDS)

        def callback(data, count, timing, status):
            # Never block the PortAudio thread or retain its reused input buffer.
            if cancel.is_set() or failed.is_set():
                return
            try:
                if status or count != frames:
                    failed.set()
                    return
                blocks.put_nowait(data[:, 0].copy())
            except Exception:
                failed.set()

        stream = None
        try:
            check_cancel(cancel)
            sd.check_input_settings(channels=1, dtype="float32", samplerate=SAMPLE_RATE)
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                    blocksize=frames, callback=callback)
            check_cancel(cancel)
            stream.start()
            started = monotonic()
            speech_started = None
            silence = 0.0
            captured = []
            pre_roll = deque(maxlen=int(PRE_ROLL_SECONDS / BLOCK_SECONDS))
            speech_frames = 0
            onset_frames = 0
            noise_rms = INITIAL_NOISE_RMS
            end_threshold = None
            calibration_count = 0
            while True:
                check_cancel(cancel)
                if failed.is_set():
                    raise VoiceInputFailure("audio")
                now = monotonic()
                if speech_started is None and now - started >= cfg.speech_start_timeout:
                    raise VoiceInputFailure("empty")
                if speech_started is not None and now - speech_started >= cfg.max_utterance_duration:
                    raise VoiceInputFailure("duration")
                try:
                    block = blocks.get(timeout=POLL_SECONDS)
                except Empty:
                    continue
                if not np.isfinite(block).all():
                    raise VoiceInputFailure("audio")
                rms = float(np.sqrt(np.mean(block * block)))
                # Calibration phase: learn the real ambient noise floor from the
                # first calibration_blocks blocks before enabling onset detection.
                # On macOS, Core Audio hardware has a higher noise floor than
                # Windows WASAPI/DirectSound; without calibration, INITIAL_NOISE_RMS
                # (0.0003) is too low and ambient noise (≈0.00445 RMS) immediately
                # triggers false speech onset that never ends.  calibration_blocks=0
                # (the default) is a no-op, preserving Windows behaviour exactly.
                if calibration_count < cfg.calibration_blocks:
                    pre_roll.append(block)
                    noise_rms = 0.9 * noise_rms + 0.1 * rms
                    calibration_count += 1
                    continue
                # Learn only from quiet blocks so speech cannot raise its own
                # gate. A floor rejects low-level microphone noise; the existing
                # configured threshold remains a ceiling, not a loudness demand.
                start_threshold = min(cfg.speech_threshold, max(MIN_SPEECH_RMS, noise_rms * 3))
                if speech_started is None:
                    pre_roll.append(block)
                    if rms < start_threshold:
                        noise_rms = 0.9 * noise_rms + 0.1 * rms
                        onset_frames = 0
                        continue
                    onset_frames += len(block)
                    # Reject isolated clicks without discarding short commands.
                    # The pre-roll includes all onset-confirmation blocks.
                    if onset_frames < int(MIN_SPEECH_SECONDS * SAMPLE_RATE):
                        continue
                    speech_started = now
                    end_threshold = start_threshold * 0.6
                    captured.extend(pre_roll)
                    speech_frames = sum(len(item) for item in pre_roll) - len(block)
                else:
                    captured.append(block)
                speech_frames += len(block)
                if speech_frames >= int(cfg.max_utterance_duration * SAMPLE_RATE):
                    raise VoiceInputFailure("duration")
                # Hysteresis preserves quieter syllables after speech starts.
                silence = 0.0 if rms >= end_threshold else silence + len(block) / SAMPLE_RATE
                if silence >= cfg.silence_duration:
                    check_cancel(cancel)
                    return np.concatenate(captured).astype("float32", copy=False)
        except VoiceInputError:
            raise
        except Exception:
            raise VoiceInputFailure("device") from None
        finally:
            if stream is not None:
                try:
                    stream.abort()
                except Exception:
                    pass  # close still releases a stream whose abort failed.
                finally:
                    try:
                        stream.close()
                    except Exception:
                        raise VoiceInputFailure("device") from None
