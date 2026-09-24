"""Headless view tests: fake Tk widgets, real controller, no display/audio/OS I/O."""

import sys
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from desktop_ui import InstantSurface, main
from interaction import AgentReply, InteractionController, InteractionState, Presentation


class Widget:
    def __init__(self, *args, **kwargs):
        self.options = kwargs
        self.value = ""
        self.owner = get_ident()
        self.bindings = {}

    def pack(self, **kwargs): pass

    def configure(self, **kwargs):
        assert get_ident() == self.owner
        self.options.update(kwargs)

    def bind(self, key, callback): self.bindings[key] = callback
    def delete(self, *args): self.value = ""
    def insert(self, position, text): self.value = text
    def get(self): return self.value
    def focus_set(self): pass


class Value:
    def __init__(self, value): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


@pytest.fixture
def fake_tk(monkeypatch):
    ttk = SimpleNamespace(**{name: Widget for name in ("Frame", "Label", "Entry", "Button", "Checkbutton")})
    tk = SimpleNamespace(Text=Widget, StringVar=Value, BooleanVar=Value, ttk=ttk,
                         TclError=RuntimeError, Tk=Mock())
    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.ttk", ttk)
    return tk


def surface(core=None, microphone=None, speaker=None):
    root = Mock()
    core = core if core is not None else Mock(return_value=AgentReply("Result"))
    view = InstantSurface(root, controller_factory=lambda publish: InteractionController(
        publish, core=core, voice_input=microphone, voice_output=speaker))
    return view, root, core


def finish(view):
    view._worker.join(3)
    assert not view._worker.is_alive()
    view._poll()


def test_construct_and_summon_never_activate_core_or_microphone(fake_tk):
    microphone = Mock()
    view, root, core = surface(microphone=microphone)
    view.summon()
    root.deiconify.assert_called_once()
    root.lift.assert_called_once()
    core.assert_not_called()
    microphone.recognize.assert_not_called()
    assert not view.read_reply.get()
    assert view.status.get() == "Ready"


def test_enter_sends_once_and_presents_result_on_ui_thread(fake_tk):
    view, root, core = surface()
    view.entry.value = "I'm here."
    view.entry.bindings["<Return>"](None)
    finish(view)
    core.assert_called_once_with("I'm here.")
    assert view.response.value == "Result"
    assert view.entry.options["state"] == "normal"
    assert view.response.options["state"] == "disabled"


def test_microphone_is_explicit_and_uses_same_core(fake_tk):
    mic = Mock(recognize=Mock(return_value="help"))
    view, _, core = surface(microphone=mic)
    view.listen()
    finish(view)
    mic.recognize.assert_called_once()
    core.assert_called_once_with("help")


def test_speech_failure_keeps_visible_result(fake_tk):
    speaker = Mock(speak=Mock(side_effect=RuntimeError("secret")))
    view, _, _ = surface(speaker=speaker)
    view.entry.value = "help"
    view.read_reply.set(True)
    view.send()
    finish(view)
    assert view.response.value == "Result"
    assert "text result is still available" in view.status.get()


@pytest.mark.parametrize("outcome", ["unavailable", "empty", "failure", "cancelled"])
def test_failed_voice_input_preserves_previous_text_result(fake_tk, outcome):
    mic = None if outcome == "unavailable" else Mock()
    view, _, core = surface(microphone=mic)
    view._present(Presentation(InteractionState.RESPONDING, "Previous result"))
    if outcome == "empty":
        mic.recognize.return_value = " "
    elif outcome == "failure":
        mic.recognize.side_effect = OSError("private microphone details")
    elif outcome == "cancelled":
        def recognize(cancel):
            cancel.set()
            return "must not execute"
        mic.recognize.side_effect = recognize
    view.listen()
    finish(view)
    assert view.response.value == "Previous result"
    core.assert_not_called()
    assert view._state == (InteractionState.IDLE if outcome == "cancelled" else InteractionState.ERROR)


def test_response_is_replaced_not_appended_as_history(fake_tk):
    view, _, _ = surface()
    view._present(Presentation(InteractionState.RESPONDING, "First"))
    view._present(Presentation(InteractionState.RESPONDING, "Second"))
    assert view.response.value == "Second"


def test_dismiss_idle_destroys_window_and_cancels_poll(fake_tk):
    view, root, _ = surface()
    view.dismiss()
    root.destroy.assert_called_once()
    root.after_cancel.assert_called_once()
    view.dismiss()
    root.destroy.assert_called_once()


def test_dismiss_processing_hides_but_does_not_abandon_work(fake_tk):
    entered, release = Event(), Event()
    def core(text):
        entered.set()
        assert release.wait(3)
        return AgentReply("Finished")
    view, root, _ = surface(core=core)
    view.entry.value = "help"
    view.send()
    try:
        assert entered.wait(3)
        worker = view._worker
        view.send()
        assert view._worker is worker
        view.dismiss()
        root.withdraw.assert_called_once()
        root.destroy.assert_not_called()
    finally:
        release.set()
        finish(view)
    root.destroy.assert_called_once()
    assert view.response.value == ""


def test_listening_can_be_cancelled_without_dispatch(fake_tk):
    entered, release = Event(), Event()
    mic = Mock()
    def recognize(cancel):
        entered.set()
        assert release.wait(3)
        assert cancel.is_set()
        return "help"
    mic.recognize.side_effect = recognize
    view, _, core = surface(microphone=mic)
    view.listen()
    try:
        assert entered.wait(3)
        view._poll()
        assert view.mic.options["text"] == "Cancel"
        view.listen()
    finally:
        release.set()
        finish(view)
    core.assert_not_called()
    assert view.status.get() == "Listening cancelled."


def test_no_display_is_controlled(fake_tk, capsys):
    fake_tk.Tk.side_effect = RuntimeError("private display details")
    assert main() == 1
    text = capsys.readouterr().out
    assert "could not open a display" in text
    assert "private" not in text


def test_core_exit_closes_without_touching_destroyed_widgets(fake_tk):
    view, root, _ = surface(core=lambda text: AgentReply("Goodbye!", dismiss=True))
    view.entry.value = "exit"
    view.send()
    view._worker.join(3)
    view._set_enabled = Mock()
    view._poll()
    root.destroy.assert_called_once()
    view._set_enabled.assert_not_called()


def test_missing_tk_is_controlled(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "tkinter", None)
    assert main() == 1
    assert "requires Python with Tk support" in capsys.readouterr().out
