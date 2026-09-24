"""Voice/controller checks with fake providers and the existing isolated core."""

import ast
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock, patch

import pytest

import main
from interaction import AgentReply, InteractionController, InteractionState, run_existing_core
from voice import UnavailableVoiceInput, UnavailableVoiceOutput, VoiceInputError, VoiceOutputError


def make_controller(**kwargs):
    updates = []
    return InteractionController(updates.append, **kwargs), updates


@pytest.mark.parametrize("voice", [False, True])
def test_input_sources_share_the_identical_core_and_text(voice):
    text = "  I'm here.  "
    core = Mock(return_value=AgentReply("Current context: current_place."))
    microphone = Mock()
    microphone.recognize.return_value = text
    controller, updates = make_controller(core=core, voice_input=microphone)
    microphone.recognize.assert_not_called()
    if voice:
        assert controller.submit_voice()
        assert isinstance(microphone.recognize.call_args.args[0], Event)
    else:
        assert controller.submit_text(text)
        microphone.recognize.assert_not_called()
    core.assert_called_once_with(text)
    states = [u.state for u in updates]
    assert states == ([InteractionState.LISTENING] if voice else []) + [
        InteractionState.PROCESSING, InteractionState.RESPONDING, InteractionState.IDLE]
    assert updates[-1].response == "Current context: current_place."


@pytest.mark.parametrize("text", ["", "  ", None, b"audio", {"transcript": "help"}])
@pytest.mark.parametrize("voice", [False, True])
def test_empty_or_nontext_input_never_reaches_core(text, voice):
    core = Mock()
    microphone = Mock()
    microphone.recognize.return_value = text
    controller, updates = make_controller(core=core, voice_input=microphone)
    assert not (controller.submit_voice() if voice else controller.submit_text(text))
    core.assert_not_called()
    assert updates[-1].state == InteractionState.ERROR


@pytest.mark.parametrize("error", [VoiceInputError("private transcript"), OSError("device secret"), TimeoutError("private")])
def test_input_failure_is_controlled_and_private(error, capsys):
    microphone = Mock()
    microphone.recognize.side_effect = error
    core = Mock()
    controller, updates = make_controller(core=core, voice_input=microphone)
    assert not controller.submit_voice()
    core.assert_not_called()
    assert updates[-1].notice == "Voice input is unavailable. Type your command instead."
    assert not capsys.readouterr().out


def test_unconfigured_input_is_an_explicit_failure():
    with pytest.raises(VoiceInputError):
        UnavailableVoiceInput().recognize(Event())
    controller, updates = make_controller(core=Mock())
    assert not controller.submit_voice()
    assert updates[-1].state == InteractionState.ERROR


def test_output_receives_only_final_response_after_display():
    events = []
    speaker = Mock()
    speaker.speak.side_effect = lambda text: events.append(("speech", text))
    controller = InteractionController(lambda u: events.append(("ui", u)), voice_output=speaker,
                                       core=lambda text: AgentReply("Result text"))
    assert controller.submit_text("private request", speak=True)
    speaker.speak.assert_called_once_with("Result text")
    speech_index = next(i for i, e in enumerate(events) if e[0] == "speech")
    assert events[speech_index - 1][1].response == "Result text"
    assert events[speech_index - 1][1].state == InteractionState.RESPONDING


@pytest.mark.parametrize("provider", [None, UnavailableVoiceOutput(), Mock(speak=Mock(side_effect=OSError("secret")))])
def test_output_failure_or_absence_preserves_text_and_action_success(provider):
    controller, updates = make_controller(core=lambda text: AgentReply("Done safely."), voice_output=provider)
    assert controller.submit_text("help", speak=True)
    assert updates[-1].response == "Done safely."
    assert "Voice output" in updates[-1].notice
    assert "secret" not in repr(updates)


def test_output_is_opt_in():
    speaker = Mock()
    controller, _ = make_controller(core=lambda text: AgentReply("Done."), voice_output=speaker)
    assert controller.submit_text("help")
    speaker.speak.assert_not_called()
    with pytest.raises(VoiceOutputError):
        UnavailableVoiceOutput().speak("reply")


@pytest.mark.parametrize("reply", [AgentReply("Action failed.", False), None])
def test_agent_failure_is_controlled(reply):
    speaker = Mock()
    controller, updates = make_controller(core=lambda text: reply, voice_output=speaker)
    assert not controller.submit_text("help", speak=True)
    assert updates[-1].state == InteractionState.ERROR
    speaker.speak.assert_not_called()


def test_unexpected_agent_exception_is_not_disclosed():
    controller, updates = make_controller(core=Mock(side_effect=RuntimeError("private path or key")))
    assert not controller.submit_text("help")
    assert updates[-1].response == "The agent could not complete that request."


def test_cancelled_late_recognition_cannot_execute():
    entered, release = Event(), Event()
    microphone = Mock()
    def recognize(cancel):
        entered.set()
        assert release.wait(3)
        assert cancel.is_set()
        return "open calculator"
    microphone.recognize.side_effect = recognize
    core = Mock()
    controller, updates = make_controller(core=core, voice_input=microphone)
    worker = Thread(target=controller.submit_voice)
    worker.start()
    try:
        assert entered.wait(3)
        assert not controller.submit_text("second command")
        controller.cancel_listening()
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    core.assert_not_called()
    assert updates[-1].notice == "Listening cancelled."


def test_dismiss_before_capture_prevents_late_start():
    core, microphone = Mock(), Mock()
    controller, _ = make_controller(core=core, voice_input=microphone)
    controller.dismiss()
    assert not controller.submit_voice()
    assert not controller.submit_text("help")
    microphone.recognize.assert_not_called()
    core.assert_not_called()


def test_dismiss_during_core_does_not_speak_or_undo_action():
    speaker = Mock()
    controller, _ = make_controller(voice_output=speaker)
    def core(text):
        controller.dismiss()
        return AgentReply("Completed")
    controller._core = core
    assert controller.submit_text("help", speak=True)
    speaker.speak.assert_not_called()


def test_bridge_calls_only_public_entry_point_and_filters_diagnostics(capsys):
    def handle(text):
        print("[AI] diagnostic")
        print("[LOG] diagnostic")
        print("User-visible response.")
        return [{"private": "plan must not reach output"}]
    with patch.object(main, "handle_command", side_effect=handle) as core:
        reply = run_existing_core("unaltered input")
    core.assert_called_once_with("unaltered input")
    assert reply == AgentReply("User-visible response.")
    assert not capsys.readouterr().out


@pytest.mark.parametrize("result,printed,expected", [
    ([], "AI service unavailable.", AgentReply("AI service unavailable.", False)),
    ([{}], "", AgentReply("Done.")), ([], "", AgentReply("The request did not complete.", False)),
])
def test_bridge_preserves_core_outcome(result, printed, expected):
    def handle(text):
        print(printed)
        return result
    with patch.object(main, "handle_command", side_effect=handle):
        assert run_existing_core("request") == expected


@pytest.mark.parametrize("error", [RuntimeError("secret"), SystemExit(1)])
def test_bridge_controls_unexpected_failures(error):
    with patch.object(main, "handle_command", side_effect=error):
        assert run_existing_core("request") == AgentReply("The agent could not complete that request.", False)


def test_exit_uses_existing_core_and_requests_dismissal():
    assert run_existing_core("exit") == AgentReply("Goodbye!", dismiss=True)


def test_real_context_sequence_and_continuity_use_existing_core():
    controller, updates = make_controller()
    with patch("ai.brain.AIBrain.plan", side_effect=AssertionError("Unexpected AI call")), \
         patch("executor.execute", side_effect=AssertionError("Unexpected desktop action")):
        assert controller.submit_text("I'm here.")
        assert controller.submit_text("Remember that I need to submit my assignment before I leave.")
        assert controller.submit_text("I'm leaving.")
        assert "Before you leave, still pending: submit my assignment" in updates[-1].response
        # A new surface reuses persisted core continuity, not controller history.
        new_controller, new_updates = make_controller()
        assert new_controller.submit_text("Continue what I was doing.")
        assert "submit my assignment" in new_updates[-1].response
        assert "(closed)" in new_updates[-1].response


@pytest.mark.parametrize("voice", [False, True])
@pytest.mark.parametrize("valid", [False, True])
def test_real_ai_boundary_still_invokes_policy_then_task_execution(voice, valid):
    from ai.action_policy import ActionPolicy
    from ai import orchestrator
    from ai.orchestrator import process_natural_language_command
    brain = Mock()
    actions = [{"action": "open", "target": "brave", "params": {}}]
    if not valid:
        actions.append({"action": "open", "target": "brave", "params": {"url": "https://unconfigured.example"}})
    brain.plan.return_value = {"actions": actions}
    microphone = Mock(recognize=Mock(return_value="please open brave"))
    controller, updates = make_controller(voice_input=microphone)
    with patch("platform.system", return_value="Windows"), \
         patch.object(main, "process_natural_language_command", side_effect=lambda text: process_natural_language_command(text, brain=brain)), \
         patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy, \
         patch.object(orchestrator, "execute_task", wraps=orchestrator.execute_task) as task, \
         patch("actions.platforms.WindowsAdapter._brave", return_value="fixed-brave.exe"), \
         patch("actions.platforms.subprocess.Popen") as launch:
        result = controller.submit_voice() if voice else controller.submit_text("please open brave")
    policy.assert_called_once()
    assert result == valid
    if valid:
        task.assert_called_once()
        launch.assert_called_once_with(["fixed-brave.exe"])
    else:
        task.assert_not_called()
        launch.assert_not_called()
        assert updates[-1].state == InteractionState.ERROR


def test_interaction_modules_have_no_alternate_agent_dependencies():
    root = Path(__file__).parent
    allowed = {"__future__", "contextlib", "dataclasses", "enum", "io", "threading", "typing",
               "queue", "tkinter", "interaction", "voice", "main"}
    for filename in ("interaction.py", "voice.py", "desktop_ui.py"):
        tree = ast.parse((root / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split('.')[0] in allowed for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.module.split('.')[0] in allowed
                if node.module == "main":
                    assert [alias.name for alias in node.names] == ["handle_command"]
