"""Mac fallback tests use fake credentials and mocked SDK calls/transports only."""
import json
import traceback
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from google.genai import errors as genai_errors

# The Groq dependency is intentionally not installed by Windows requirements.
groq = pytest.importorskip("groq")

from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.brain import AIBrain
from ai.errors import AIPlanningError, AIProviderError, TaskExecutionError
from ai.gemini import GeminiProvider, GeminiProviderError
from ai.groq import GroqProvider
from ai.orchestrator import process_natural_language_command
from ai.provider_manager import ProviderManager

PLAN = {"actions": [{"action": "open", "target": "calculator", "params": {}}]}
TEXT = json.dumps(PLAN)
SECRET = "fake-private-test-key"


def completion(text=TEXT, finish_reason="stop", tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish_reason,
        message=SimpleNamespace(content=text, tool_calls=tool_calls),
    )])


@pytest.fixture(autouse=True)
def providers(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    gemini_client = Mock()
    gemini_client.models.generate_content.return_value = SimpleNamespace(text=TEXT)
    groq_client = Mock()
    groq_client.chat.completions.create.return_value = completion()
    monkeypatch.setattr("ai.gemini.genai.Client", Mock(return_value=gemini_client))
    factory = Mock(return_value=groq_client)
    monkeypatch.setattr("ai.groq.Groq", factory)
    return gemini_client.models.generate_content, groq_client.chat.completions.create, factory


def api_error(status):
    return genai_errors.APIError(status, {"error": {"code": status, "message": SECRET}})


def transient(providers):
    providers[0].side_effect = api_error(503)


def run(manager=None, executor=None):
    return process_natural_language_command(
        "Open Calculator", brain=AIBrain(provider_manager=manager or ProviderManager()),
        executor_func=executor if executor is not None else Mock(),
    )


def test_primary_success_does_not_construct_or_call_groq(providers):
    assert run() == PLAN["actions"]
    providers[0].assert_called_once()
    providers[1].assert_not_called()
    providers[2].assert_not_called()


@pytest.mark.parametrize("error", [api_error(code) for code in (408, 500, 502, 503, 504)] + [
    httpx.ReadTimeout(SECRET), httpx.ConnectError(SECRET), httpx.ReadError(SECRET),
    httpx.RemoteProtocolError(SECRET),
])
def test_transient_gemini_failure_uses_one_groq_attempt(error, providers):
    providers[0].side_effect = error
    assert run() == PLAN["actions"]
    providers[0].assert_called_once()
    providers[1].assert_called_once()
    prompt = providers[0].call_args.kwargs["contents"]
    providers[1].assert_called_once_with(model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}], stream=False)
    providers[2].assert_called_once_with(api_key=SECRET, base_url="https://api.groq.com",
        timeout=20.0, max_retries=0)


@pytest.mark.parametrize("error", [api_error(code) for code in (400, 401, 403, 404, 422, 429, 501)] + [
    httpx.UnsupportedProtocol(SECRET), httpx.LocalProtocolError(SECRET),
])
def test_non_transient_gemini_errors_do_not_fallback(error, providers):
    providers[0].side_effect = error
    with pytest.raises(AIProviderError, match="AI service unavailable"):
        run()
    providers[2].assert_not_called()


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_gemini_response_does_not_fallback(text, providers):
    providers[0].return_value = SimpleNamespace(text=text)
    with pytest.raises(AIProviderError):
        run()
    providers[2].assert_not_called()


@pytest.mark.parametrize("source", ["gemini", "groq"])
@pytest.mark.parametrize("text", ["not JSON", '{"actions":', '{"actions":[]}',
    '{"actions":[{"action":"execute","target":"calculator","params":{}}]}',
    '{"actions":[{"action":"open","target":"calculator","params":{"url":12}}]}'])
def test_bad_plans_never_trigger_another_attempt_or_execute(source, text, providers):
    if source == "groq":
        transient(providers)
        providers[1].return_value = completion(text)
    else:
        providers[0].return_value = SimpleNamespace(text=text)
    execute = Mock()
    with pytest.raises(AIPlanningError):
        run(executor=execute)
    execute.assert_not_called()
    assert providers[0].call_count == 1
    assert providers[1].call_count == (1 if source == "groq" else 0)


@pytest.mark.parametrize("source", ["gemini", "groq"])
@pytest.mark.parametrize("target,params", [("unknown-app", {}), ("calculator", {"command": "unsafe"})])
def test_policy_rejection_never_retries(source, target, params, providers):
    text = json.dumps({"actions": [{"action": "open", "target": target, "params": params}]})
    if source == "groq":
        transient(providers)
        providers[1].return_value = completion(text)
    else:
        providers[0].return_value = SimpleNamespace(text=text)
    execute = Mock()
    with pytest.raises(ActionPolicyError):
        run(executor=execute)
    execute.assert_not_called()
    assert providers[0].call_count == 1
    assert providers[1].call_count == (1 if source == "groq" else 0)


def test_fallback_passes_shared_schema_then_policy_before_execution(providers):
    transient(providers)
    manager = ProviderManager()
    execute = Mock()
    from ai.plan_schema import validate_plan
    with patch("ai.brain.validate_plan", wraps=validate_plan) as schema, \
         patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy:
        def dispatch(action):
            schema.assert_called_once_with(PLAN)
            policy.assert_called_once()
            assert action == PLAN["actions"][0]
        execute.side_effect = dispatch
        assert run(manager, execute) == PLAN["actions"]
    execute.assert_called_once()
    assert manager.active_provider == "gemini"
    # A later request starts at Gemini again, even after a successful fallback.
    providers[0].side_effect = None
    assert manager.generate_text("next request") == TEXT
    assert providers[0].call_count == 2
    assert providers[1].call_count == 1


@pytest.mark.parametrize("source", ["gemini", "groq"])
def test_execution_failure_does_not_retry_provider(source, providers):
    if source == "groq":
        transient(providers)
    with pytest.raises(TaskExecutionError):
        run(executor=Mock(side_effect=RuntimeError("application failed")))
    assert providers[0].call_count == 1
    assert providers[1].call_count == (1 if source == "groq" else 0)


def test_invalid_command_never_calls_either_provider(providers):
    with pytest.raises(ValueError):
        AIBrain().plan(" ")
    providers[0].assert_not_called()
    providers[2].assert_not_called()


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_fallback_key_is_controlled_and_lazy(key, monkeypatch, providers):
    if key is None:
        monkeypatch.delenv("GROQ_API_KEY")
    else:
        monkeypatch.setenv("GROQ_API_KEY", key)
    assert run() == PLAN["actions"]
    transient(providers)
    with pytest.raises(AIProviderError, match="AI service unavailable"):
        run()
    providers[2].assert_not_called()


def test_missing_gemini_key_does_not_promote_groq(monkeypatch, providers):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(AIProviderError):
        ProviderManager()
    providers[2].assert_not_called()


def test_groq_dotenv_precedence_and_explicit_key(tmp_path, monkeypatch, providers):
    (tmp_path / ".env").write_text("GROQ_API_KEY=fake-dotenv-key\n")
    monkeypatch.delenv("GROQ_API_KEY")
    GroqProvider()
    assert providers[2].call_args.kwargs["api_key"] == "fake-dotenv-key"
    monkeypatch.setenv("GROQ_API_KEY", "fake-shell-key")
    GroqProvider()
    assert providers[2].call_args.kwargs["api_key"] == "fake-shell-key"
    GroqProvider(api_key="fake-explicit-key")
    assert providers[2].call_args.kwargs["api_key"] == "fake-explicit-key"
    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(AIProviderError):
        GroqProvider()


@pytest.mark.parametrize("system", ["Windows", "Linux"])
def test_no_fallback_outside_macos(system, monkeypatch, providers):
    monkeypatch.setattr("platform.system", lambda: system)
    transient(providers)
    with pytest.raises(AIProviderError):
        run()
    providers[2].assert_not_called()


@pytest.mark.parametrize("error", [TimeoutError(SECRET), ConnectionError(SECRET),
                                   AIProviderError(SECRET, transient=True)])
def test_explicit_provider_injection_stays_isolated_unless_fallback_supplied(error, providers):
    primary = Mock(generate_text=Mock(side_effect=error))
    with pytest.raises(AIProviderError):
        ProviderManager(provider=primary).generate_text("prompt")
    providers[2].assert_not_called()
    fallback = Mock(generate_text=Mock(return_value=TEXT))
    assert ProviderManager(provider=primary, fallback_provider=fallback).generate_text("prompt") == TEXT
    fallback.generate_text.assert_called_once_with("prompt")


@pytest.mark.parametrize("response", [SimpleNamespace(choices=[]), completion(None), completion(" "),
    completion(finish_reason="length"), completion(finish_reason="tool_calls"),
    completion(tool_calls=[{"function": "anything"}])])
def test_groq_incomplete_or_tool_response_rejected_without_execution(response, providers):
    transient(providers)
    providers[1].return_value = response
    execute = Mock()
    with pytest.raises(AIProviderError):
        run(executor=execute)
    execute.assert_not_called()
    assert providers[1].call_count == 1


@pytest.mark.parametrize("status", [200, 400, 401, 429, 503, "timeout", "connection"])
def test_real_groq_sdk_serialization_no_retries_and_sanitized_errors(status, monkeypatch, providers, capsys, caplog):
    requests = []
    def respond(request):
        requests.append(request)
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        assert request.extensions["timeout"]["read"] == 20.0
        assert json.loads(request.content) == {
            "model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": "private prompt"}],
            "stream": False,
        }
        if status == "timeout":
            raise httpx.ReadTimeout(SECRET, request=request)
        if status == "connection":
            raise httpx.ConnectError(SECRET, request=request)
        if status == 200:
            return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0,
                "model": GroqProvider.MODEL, "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": TEXT}}]})
        return httpx.Response(status, json={"error": {"message": SECRET}})

    def client(**kwargs):
        return groq.Groq(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr("ai.groq.Groq", client)
    provider = GroqProvider()
    try:
        if status == 200:
            assert provider.generate_text("private prompt") == TEXT
        else:
            with pytest.raises(AIProviderError) as error:
                provider.generate_text("private prompt")
            assert SECRET not in "".join(traceback.format_exception(error.value))
    finally:
        provider.client.close()
    assert len(requests) == 1
    output = capsys.readouterr().out + caplog.text
    assert SECRET not in output and "private prompt" not in output


def test_fallback_failure_is_final_and_diagnostics_are_sanitized(providers, capsys, caplog):
    transient(providers)
    providers[1].side_effect = groq.APIConnectionError(message=SECRET, request=httpx.Request("POST", "https://api.groq.com"))
    with pytest.raises(AIProviderError) as error:
        run()
    assert providers[0].call_count == providers[1].call_count == 1
    assert SECRET not in "".join(traceback.format_exception(error.value))
    assert SECRET not in capsys.readouterr().out + caplog.text
