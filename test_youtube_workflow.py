"""HP8 contract and integration tests; browser operations are always mocked."""

import json
import subprocess
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

import executor
import main
from actions.browser import open_browser, open_site
from actions.search import search_google
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.brain import AIBrain
from ai.orchestrator import process_natural_language_command
from config import BROWSERS
from context import ContextEngine
from memory import MemoryManager, MemoryStore


@pytest.fixture
def manager(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.db"))
    try:
        yield MemoryManager(store)
    finally:
        store.close()


@pytest.mark.parametrize("query", ["Python tutorials", "C++ #1 / 100%", 'café 日本語 "intro"?'])
def test_youtube_encoding_preserves_query(query):
    with patch("actions.search.open_browser") as launch:
        search_google(query, {"engine": "youtube"})
    browser, url = launch.call_args.args
    assert browser == BROWSERS["preferred"]
    parsed = urlsplit(url)
    assert (parsed.scheme, parsed.netloc, parsed.path, parsed.fragment) == (
        "https", "www.youtube.com", "/results", ""
    )
    assert parse_qs(parsed.query) == {"search_query": [query]}
    assert " " not in url


@pytest.mark.parametrize("browser", ["Brave", "Safari"])
def test_preference_survives_context_limit(manager, browser):
    manager.add_memory(f"I prefer {browser}", "user_preference")
    context = ContextEngine(manager).build_context(query="Python", max_memories=0)
    assert context.system_context["browsers"]["preferred"] == browser.lower()
    assert BROWSERS["preferred"] == "brave"
    with patch("actions.search.open_browser") as launch:
        search_google("Python", {"engine": "youtube", "context": context.to_dict()})
    assert launch.call_args.args[0] == browser.lower()


@pytest.mark.parametrize("browser,app", [("Brave", "Brave Browser"), ("Safari", "Safari")])
def test_full_workflow_through_real_executor(manager, browser, app, capsys):
    manager.add_memory(f"I prefer {browser}", "user_preference")
    engine = ContextEngine(manager)
    command = "Search YouTube for C++ tutorials in my preferred browser"

    class Provider:
        def generate_text(self, prompt):
            assert command in prompt
            assert f"'preferred': '{browser.lower()}'" in prompt
            assert '"engine":"youtube"' in prompt
            return json.dumps({"actions": [
                {"action": "search", "target": "C++ tutorials", "params": {"engine": "youtube"}}
            ]})

    def process(raw):
        return process_natural_language_command(raw, brain=AIBrain(Provider()), context_engine=engine)

    with patch("actions.browser.platform.system", return_value="Darwin"), \
         patch.object(main, "process_natural_language_command", side_effect=process), \
         patch.object(executor, "context_engine", engine), \
         patch.object(executor, "log_action"), \
         patch("actions.browser.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as launch:
        result = main.handle_command(command)

    assert result[0]["action"] == "search"
    launch.assert_called_once_with(
        ["open", "-a", app, "https://www.youtube.com/results?search_query=C%2B%2B+tutorials"],
        check=True,
    )
    assert "page loading is not verified" in capsys.readouterr().out


@pytest.mark.parametrize("failure", [FileNotFoundError("open unavailable"), subprocess.CalledProcessError(1, ["open"])])
def test_launch_failure_stops_task_and_cli_reports_failure(manager, failure, capsys):
    engine = ContextEngine(manager)

    class Brain:
        def plan(self, command, context):
            return {"actions": [
                {"action": "search", "target": "Python", "params": {"engine": "youtube"}},
                {"action": "open", "target": "gmail", "params": {}},
            ]}

    def process(raw):
        return process_natural_language_command(raw, brain=Brain(), context_engine=engine)

    with patch("actions.browser.platform.system", return_value="Darwin"), \
         patch.object(main, "process_natural_language_command", side_effect=process), \
         patch.object(executor, "context_engine", engine), \
         patch.object(executor, "log_action"), \
         patch("actions.browser.subprocess.run", side_effect=failure) as launch, \
         patch("actions.browser.webbrowser.open") as site:
        assert main.handle_command("Search YouTube for Python") == []
    launch.assert_called_once()
    site.assert_not_called()
    output = capsys.readouterr().out
    assert "AI task failed at step 1" in output
    assert "Task succeeded" not in output
    assert "launch request accepted" not in output


def test_valid_youtube_policy_contract():
    actions = [{"action": "search", "target": "C++ #1 / café?", "params": {"engine": "youtube"}}]
    assert ActionPolicy().validate(actions) == actions


@pytest.mark.parametrize("query", ["Python; rm", "a&b", "a|b", "a`b", "a$b", "a\nb", "a\x00b"])
def test_existing_unsafe_query_protections_preserved(query):
    for target, params in [(query, {"engine": "youtube"}), ("Python", {"engine": "youtube", "query": query})]:
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([{"action": "search", "target": target, "params": params}])


@pytest.mark.parametrize("params", [
    {"engine": "https://evil.example"}, {"engine": "youtube", "query": " "},
    {"engine": "youtube", "query": 123}, {"engine": "youtube", "context": {}},
    {"engine": "youtube", "browser": "terminal"},
])
def test_policy_rejects_invalid_search_parameters(params):
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([{"action": "search", "target": "Python", "params": params}])


def test_default_browser_failure_is_reported():
    with patch("webbrowser.open", return_value=False):
        with pytest.raises(RuntimeError):
            search_google("Python")
        with pytest.raises(RuntimeError):
            open_site("youtube")


def test_unsupported_browser_does_not_launch():
    with patch("actions.browser.subprocess.run") as launch:
        with pytest.raises(ValueError):
            open_browser("terminal")
    launch.assert_not_called()


def test_routing_preserves_google_and_routes_youtube_to_ai():
    assert main.route_command("search Python tutorials")[0] == "v1"
    assert main.route_command("Search YouTube for Python tutorials in my preferred browser") == ("ai", None)
    assert main.route_command("find Python tutorials on YouTube") == ("ai", None)
