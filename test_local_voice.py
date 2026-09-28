"""Offline provider tests: fake model, audio device, arrays, and clock."""

import math
import subprocess
import sys
from pathlib import Path
from queue import Empty
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import local_voice as lv
import voice_model as vm
from interaction import AgentReply, InteractionController, InteractionState
from voice import VoiceInputError, VoiceInputFailure


@pytest.fixture
def backend(monkeypatch):
    model = Mock()
    model.transcribe.side_effect = lambda *a, **k: (iter([SimpleNamespace(text="help")]), None)
    factory = Mock(return_value=model)
    sd = Mock()
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=factory))
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace())
    snapshot = Mock(return_value=Path("cached-snapshot"))
    monkeypatch.setattr(lv, "model_snapshot", snapshot)
    provider = lv.LocalVoiceInput()
    capture = Mock(return_value="in-memory-audio")
    monkeypatch.setattr(provider, "_capture", capture)
    return SimpleNamespace(model=model, factory=factory, sd=sd, snapshot=snapshot,
                           provider=provider, capture=capture)


def test_import_and_construction_do_not_import_optional_libraries():
    script = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in ('numpy', 'sounddevice', 'faster_whisper', 'huggingface_hub'):
        raise AssertionError('Optional import at startup')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import local_voice, provision_voice
local_voice.LocalVoiceInput()
'''
    result = subprocess.run([sys.executable, "-B", "-c", script],
                            cwd=Path(__file__).parent, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_lazy_load_success_and_reuse(backend):
    b = backend
    b.factory.assert_not_called()
    b.snapshot.assert_not_called()
    for _ in range(2):
        assert b.provider.recognize(Event()) == "help"
    b.snapshot.assert_called_once_with()
    b.factory.assert_called_once_with(str(Path("cached-snapshot")), device="cpu", compute_type="int8",
                                     local_files_only=True, num_workers=1)
    assert b.model.transcribe.call_count == 2
    assert b.model.transcribe.call_args.kwargs["language"] == "en"
    assert b.model.transcribe.call_args.kwargs["vad_filter"] is True


@pytest.mark.parametrize("texts", [[], ["", "  "]])
def test_empty_transcript(backend, texts):
    backend.model.transcribe.side_effect = lambda *a, **k: (iter(SimpleNamespace(text=t) for t in texts), None)
    with pytest.raises(VoiceInputFailure, match="No speech"):
        backend.provider.recognize(Event())


def test_missing_dependencies_are_controlled(backend, monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    with pytest.raises(VoiceInputFailure, match="requirements-voice"):
        backend.provider.recognize(Event())
    backend.capture.assert_not_called()


@pytest.mark.parametrize("stage,code", [("snapshot", "model"), ("factory", "load")])
def test_model_failures_before_microphone(backend, stage, code):
    target = getattr(backend, stage)
    target.side_effect = VoiceInputFailure(code) if stage == "snapshot" else RuntimeError("private path")
    with pytest.raises(VoiceInputFailure) as error:
        backend.provider.recognize(Event())
    assert error.value.notice == VoiceInputFailure.NOTICES[code]
    assert backend.capture.call_count == (1 if stage == "factory" else 0)


@pytest.mark.parametrize("stage", ["before", "load", "capture", "inference", "iterator"])
def test_cancel_at_each_boundary_suppresses_dispatch(backend, stage):
    b = backend
    updates = []
    core = Mock(return_value=AgentReply("done"))
    controller = InteractionController(updates.append, voice_input=b.provider, core=core)
    cancel = controller._cancel
    if stage == "before":
        def publish(update):
            updates.append(update)
            if update.state == InteractionState.LISTENING:
                cancel.set()
        controller._publish = publish
    elif stage == "load":
        b.factory.side_effect = lambda *a, **k: (cancel.set(), b.model)[1]
    elif stage == "capture":
        b.capture.side_effect = lambda *a: (cancel.set(), "audio")[1]
    elif stage == "inference":
        b.model.transcribe.side_effect = lambda *a, **k: (cancel.set(), (iter([]), None))[1]
    else:
        def segments():
            cancel.set()
            yield SimpleNamespace(text="must not run")
        b.model.transcribe.side_effect = lambda *a, **k: (segments(), None)
    assert not controller.submit_voice()
    core.assert_not_called()
    assert updates[-1].notice == "Listening cancelled."
    if stage == "before":
        b.capture.assert_not_called()


def test_pre_cancelled_request_never_loads_model(backend):
    cancel = Event(); cancel.set()
    with pytest.raises(VoiceInputError, match="cancelled"):
        backend.provider.recognize(cancel)
    backend.factory.assert_not_called()


def test_one_request_at_a_time_and_lock_released_after_failure(backend):
    p = backend.provider
    def capture(cancel, *args):
        with pytest.raises(VoiceInputFailure, match="already running"):
            p.recognize(Event())
        raise VoiceInputFailure("device")
    backend.capture.side_effect = capture
    with pytest.raises(VoiceInputFailure):
        p.recognize(Event())
    backend.capture.side_effect = None
    assert p.recognize(Event()) == "help"


class Vector(list):
    def copy(self): return Vector(self)
    def __mul__(self, other): return Vector(a*b for a, b in zip(self, other))
    def astype(self, *args, **kwargs): return self


class InputData:
    def __init__(self, value): self.value = value
    def __getitem__(self, key): return Vector([self.value] * 320)


@pytest.fixture
def microphone(monkeypatch):
    clock = [0.0]
    events = []
    cancel = Event()
    stream = Mock()
    callback = [None]
    class ScriptedQueue:
        def __init__(self, maxsize): self.pending = []
        def put_nowait(self, data): self.pending.append(data)
        def get(self, timeout):
            clock[0] += lv.BLOCK_SECONDS
            if events:
                event = events.pop(0)
                if callable(event): event()
                elif event is not None: callback[0](InputData(event), 320, None, False)
            if self.pending: return self.pending.pop(0)
            raise Empty
    def create(**kwargs):
        callback[0] = kwargs["callback"]
        return stream
    sd = SimpleNamespace(InputStream=Mock(side_effect=create), check_input_settings=Mock())
    np = SimpleNamespace(
        isfinite=lambda values: SimpleNamespace(all=lambda: all(math.isfinite(x) for x in values)),
        mean=lambda values: sum(values)/len(values), sqrt=math.sqrt,
        concatenate=lambda values: Vector(x for v in values for x in v),
    )
    monkeypatch.setattr(lv, "Queue", ScriptedQueue)
    monkeypatch.setattr(lv, "monotonic", lambda: clock[0])
    provider = lv.LocalVoiceInput(lv.CaptureConfig(speech_start_timeout=.12,
                                                 max_utterance_duration=.3, silence_duration=.06))
    return SimpleNamespace(provider=provider, events=events, cancel=cancel, stream=stream,
                           sd=sd, np=np, callback=callback, clock=clock)


def capture(m): return m.provider._capture(m.cancel, m.sd, m.np)


def test_capture_silence_stop_preroll_and_cleanup(microphone):
    m = microphone
    m.events.extend([0] + [.1]*5 + [0]*3)
    audio = capture(m)
    assert len(audio) == 9 * 320
    assert m.clock[0] < .3
    m.stream.abort.assert_called_once()
    m.stream.close.assert_called_once()
    m.sd.check_input_settings.assert_called_once_with(channels=1, dtype="float32", samplerate=16000)


def normal_capture(m):
    m.provider = lv.LocalVoiceInput()
    return capture(m)


@pytest.mark.parametrize("level", [0, 0.00026873, 0.0007])
def test_background_noise_times_out_without_speech(microphone, level):
    m = microphone
    m.events.extend([level] * 300)
    with pytest.raises(VoiceInputFailure, match="No speech"):
        normal_capture(m)
    assert 5 <= m.clock[0] < 5.1
    m.stream.close.assert_called_once()


@pytest.mark.parametrize("level", [0.002, 0.004, 0.01, 0.07207559])
def test_normal_distance_speech_then_silence_preserves_samples(microphone, level):
    m = microphone
    m.events.extend([0.00026873]*20 + [level]*25 + [0.00026873]*50)
    audio = normal_capture(m)
    assert sum(value == level for value in audio) == 25 * 320
    assert 1.69 <= m.clock[0] <= 1.73
    assert m.events  # Stops on trailing silence, not the maximum duration.
    assert max(audio) == level  # No scaling/quantization in the audio path.


def test_short_command_at_capture_start_is_not_lost(microphone):
    m = microphone
    m.events.extend([0.003]*10 + [0.00026873]*50)
    audio = normal_capture(m)
    assert sum(value == 0.003 for value in audio) == 10 * 320
    assert m.clock[0] < 1.1


def test_quiet_syllables_and_internal_pause_do_not_end_command(microphone):
    m = microphone
    m.events.extend([0.004]*10 + [0.0001]*20 + [0.0007]*50 + [0.0001]*50)
    audio = normal_capture(m)
    assert sum(value == 0.0007 for value in audio) == 50 * 320
    assert 2.39 <= m.clock[0] <= 2.43


def test_noise_relative_gate_rejects_small_noise_rise(microphone):
    m = microphone
    m.events.extend([0.0007]*50 + [0.0015]*10 + [0.0007]*250)
    with pytest.raises(VoiceInputFailure, match="No speech"):
        normal_capture(m)


def test_click_is_not_speech_and_does_not_consume_command(microphone):
    m = microphone
    m.events.extend([0.1] + [0.00026873]*50 + [0.003]*10 + [0.00026873]*50)
    audio = normal_capture(m)
    assert max(audio) == 0.003
    assert sum(value == 0.003 for value in audio) == 10 * 320


def test_isolated_clicks_time_out(microphone):
    m = microphone
    m.events.extend(([0.1] + [0.00026873]*20)*15)
    with pytest.raises(VoiceInputFailure, match="No speech"):
        normal_capture(m)


def test_first_capture_precedes_cold_model_load(backend):
    order = []
    backend.capture.side_effect = lambda *args: (order.append("capture"), "audio")[1]
    backend.factory.side_effect = lambda *args, **kwargs: (order.append("load"), backend.model)[1]
    assert backend.provider.recognize(Event()) == "help"
    assert order == ["capture", "load"]
    assert backend.model.transcribe.call_args.args == ("audio",)


@pytest.mark.parametrize("events,notice", [([0]*20, "No speech"), ([None]*20, "No speech"),
                                          ([.1]*30, "capture limit"), ([float('nan')], "interrupted")])
def test_capture_bounds_and_invalid_audio(microphone, events, notice):
    m = microphone; m.events.extend(events)
    with pytest.raises(VoiceInputFailure, match=notice): capture(m)
    m.stream.close.assert_called_once()
    assert m.clock[0] < .5


@pytest.mark.parametrize("stage", ["settings", "open", "start"])
def test_missing_device_unsupported_format_and_start_failure(microphone, stage):
    m = microphone
    target = {"settings": m.sd.check_input_settings, "open": m.sd.InputStream, "start": m.stream.start}[stage]
    target.side_effect = OSError("private device details")
    with pytest.raises(VoiceInputFailure, match="Microphone unavailable"): capture(m)
    assert m.stream.close.call_count == (1 if stage == "start" else 0)


def test_cancel_during_capture_closes_stream(microphone):
    m = microphone; m.events.extend([.1, m.cancel.set])
    with pytest.raises(VoiceInputError, match="cancelled"): capture(m)
    m.stream.close.assert_called_once()


def test_callback_overflow_is_controlled(microphone):
    m = microphone
    m.events.append(lambda: m.callback[0](InputData(.1), 320, None, True))
    with pytest.raises(VoiceInputFailure, match="interrupted"): capture(m)
    m.stream.close.assert_called_once()


def test_full_audio_queue_fails_without_unbounded_buffering(microphone, monkeypatch):
    from queue import Queue
    m = microphone
    monkeypatch.setattr(lv, "Queue", Queue)
    def burst():
        for _ in range(lv.QUEUE_BLOCKS + 1):
            m.callback[0](InputData(.1), 320, None, False)
    m.stream.start.side_effect = burst
    with pytest.raises(VoiceInputFailure, match="interrupted"): capture(m)
    m.stream.close.assert_called_once()


def test_cancel_during_stream_close_never_transcribes(backend, microphone, monkeypatch):
    b = backend; m = microphone
    m.events.extend([.1]*5 + [0]*3)
    m.stream.close.side_effect = m.cancel.set
    monkeypatch.setattr(b.provider, "_capture", lambda cancel, *args: capture(m))
    with pytest.raises(VoiceInputError, match="cancelled"):
        b.provider.recognize(m.cancel)
    b.model.transcribe.assert_not_called()
    m.stream.close.assert_called_once()


def test_stream_close_failure_is_controlled(microphone):
    m = microphone; m.events.extend([.1]*5 + [0]*3)
    m.stream.close.side_effect = OSError("private device")
    with pytest.raises(VoiceInputFailure, match="Microphone unavailable"): capture(m)


def test_abort_failure_still_closes_stream(microphone):
    m = microphone; m.events.extend([.1]*5 + [0]*3)
    m.stream.abort.side_effect = OSError("device gone")
    capture(m)
    m.stream.close.assert_called_once()


@pytest.mark.parametrize("lazy", [False, True])
def test_transcription_failure_happens_after_stream_closed(backend, microphone, monkeypatch, lazy):
    b = backend; m = microphone; m.events.extend([.1]*5 + [0]*3)
    monkeypatch.setattr(b.provider, "_capture", lambda cancel, *args: capture(m))
    def fail():
        m.stream.close.assert_called_once()
        raise RuntimeError("private audio/transcript")
        yield
    def transcribe(*args, **kwargs):
        m.stream.close.assert_called_once()
        if lazy: return fail(), None
        raise RuntimeError("private audio/transcript")
    b.model.transcribe.side_effect = transcribe
    with pytest.raises(VoiceInputFailure, match="transcription failed"):
        b.provider.recognize(Event())


@pytest.mark.parametrize("kwargs", [{"speech_start_timeout": 0}, {"speech_start_timeout": float('inf')},
                                   {"max_utterance_duration": 61}, {"silence_duration": -1},
                                   {"speech_threshold": float('nan')}, {"speech_threshold": 2},
                                   {"max_utterance_duration": .5, "silence_duration": 1}])
def test_unsafe_capture_config_rejected(kwargs):
    with pytest.raises(ValueError): lv.CaptureConfig(**kwargs)


def test_provider_text_reaches_existing_controller_path(backend):
    core = Mock(return_value=AgentReply("done"))
    updates = []
    controller = InteractionController(updates.append, voice_input=backend.provider, core=core)
    assert controller.submit_voice()
    core.assert_called_once_with("help")
    assert updates[-1].response == "done"


@pytest.mark.parametrize("command,target", [("Open Calculator", "Calculator"),
                                            ("Open Google", "Google"),
                                            ("Open YouTube", "YouTube")])
def test_quiet_capture_transcript_reaches_deterministic_core(backend, microphone, monkeypatch,
                                                           command, target):
    import main
    b = backend
    m = microphone
    m.events.extend([0.003]*10 + [0.00026873]*50)
    monkeypatch.setattr(b.provider, "_capture", lambda *args: normal_capture(m))
    b.model.transcribe.side_effect = lambda *a, **k: (iter([SimpleNamespace(text=command)]), None)
    execute = Mock()
    monkeypatch.setattr(main, "execute", execute)
    fallback = Mock(side_effect=AssertionError("Unexpected AI fallback"))
    monkeypatch.setattr(main, "process_natural_language_command", fallback)
    controller = InteractionController(lambda update: None, voice_input=b.provider)
    assert controller.submit_voice()
    execute.assert_called_once_with({"action": "open", "target": target, "params": {}})
    fallback.assert_not_called()
    assert max(b.model.transcribe.call_args.args[0]) == 0.003


@pytest.fixture
def cache(monkeypatch, tmp_path):
    root = tmp_path / "cache"; root.mkdir()
    snapshot = root / vm.MODEL_REVISION; snapshot.mkdir()
    for name in vm.MODEL_FILES: (snapshot/name).write_text("test placeholder", encoding="utf-8")
    download = Mock(return_value=str(snapshot))
    monkeypatch.setattr(vm, "REPOSITORY_ROOT", tmp_path / "checkout")
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", SimpleNamespace(HF_HUB_CACHE=str(root)))
    return SimpleNamespace(root=root, snapshot=snapshot, download=download)


@pytest.mark.parametrize("provision", [False, True])
def test_pinned_model_cache_contract(cache, provision):
    assert vm.model_snapshot(provision=provision) == cache.snapshot
    cache.download.assert_called_once_with(vm.MODEL_ID, revision=vm.MODEL_REVISION,
        cache_dir=str(cache.root), allow_patterns=list(vm.MODEL_FILES), local_files_only=not provision, token=False)


@pytest.mark.parametrize("name", vm.MODEL_FILES)
def test_incomplete_cache_is_rejected_before_whisper_fallback(cache, name):
    (cache.snapshot/name).unlink()
    with pytest.raises(VoiceInputFailure, match="provision_voice.py"): vm.model_snapshot()


def test_cache_miss_is_controlled(cache):
    cache.download.side_effect = FileNotFoundError("private location")
    with pytest.raises(VoiceInputFailure, match="provision_voice.py"): vm.model_snapshot()


def test_repository_local_cache_rejected_before_download(cache, monkeypatch):
    monkeypatch.setattr(vm, "REPOSITORY_ROOT", cache.root)
    with pytest.raises(VoiceInputFailure, match="outside the repository"): vm.model_snapshot(provision=True)
    cache.download.assert_not_called()


def test_voice_provider_has_no_agent_dependencies():
    import ast
    allowed = {"collections", "dataclasses", "math", "queue", "threading", "time", "pathlib",
               "voice", "voice_model", "numpy", "sounddevice", "faster_whisper", "huggingface_hub"}
    for name in ("local_voice.py", "voice_model.py", "provision_voice.py"):
        tree = ast.parse((Path(__file__).parent/name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split('.')[0] in allowed for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.module.split('.')[0] in allowed


def test_provision_command_is_explicit_and_controlled(cache, monkeypatch, capsys):
    import provision_voice
    assert provision_voice.main() == 0
    assert vm.MODEL_REVISION in capsys.readouterr().out
    assert cache.download.call_args.kwargs["local_files_only"] is False
    cache.download.side_effect = OSError("secret network details")
    assert provision_voice.main() == 1
    assert "secret" not in capsys.readouterr().out
