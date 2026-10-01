"""Named Mac workspaces: real SQLite in temporary paths, mocked OS/provider calls."""
import json
from unittest.mock import Mock, patch

import pytest

import config
import executor
import main
from actions import workspace
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.brain import AIBrain
from ai.errors import AIPlanningError, TaskExecutionError
from ai.orchestrator import process_natural_language_command
from ai.plan_schema import MAX_ACTIONS, WORKSPACE_ACTIONS, validate_plan
from memory import MemoryManager, MemoryStore
from memory.errors import MemoryStorageError

MUSIC = {"name": "music", "apps": ["brave"], "urls": ["https://music.youtube.com"]}


def action(verb, name="music", **params):
    return {"action": verb, "target": name, "params": params}


def create(name="music", apps=None, urls=None):
    workspace.create_workspace(name, {"apps": ["brave"] if apps is None else apps,
                                      "urls": [] if urls is None else urls})


@pytest.fixture(autouse=True)
def mac():
    with patch("platform.system", return_value="Darwin"), \
         patch("actions.platforms.subprocess.run") as run, \
         patch("subprocess.Popen") as popen, patch("os.system") as shell, \
         patch("webbrowser.open") as web:
        yield run
        popen.assert_not_called()
        shell.assert_not_called()
        web.assert_not_called()


def test_empty_and_sorted_workspace_list_is_persistent(mac, capsys):
    assert workspace.list_workspaces() == []
    assert "none" in capsys.readouterr().out
    create("music")
    workspace.save_workspace("coding")
    assert workspace.list_workspaces() == ["coding", "music"]
    assert "coding, music" in capsys.readouterr().out
    with MemoryManager() as manager:
        assert manager.list_workspaces() == ["coding", "music"]
    mac.assert_not_called()


def test_create_and_load_normalize_names_and_apps_without_launch(mac):
    workspace.create_workspace("Music", {"apps": ["Brave", "Telegram"], "urls": []})
    assert workspace.load_workspace("MUSIC") == {"name": "music", "apps": ["brave", "telegram"], "urls": []}
    mac.assert_not_called()


def test_music_restore_uses_normal_actions_and_policy_before_any_launch(mac):
    create(urls=MUSIC["urls"])
    expected = [action("open", "brave"), action("open", "brave", url=MUSIC["urls"][0])]
    assert workspace.workspace_open_actions(workspace.load_workspace("music")) == expected
    with patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy, \
         patch.object(executor, "execute", wraps=executor.execute) as execute:
        def launch(*args, **kwargs):
            assert any(call.args[1] == expected for call in policy.call_args_list)
        mac.side_effect = launch
        workspace.restore_workspace("music")
        assert [call.args[0] for call in execute.call_args_list] == expected
    assert [call.args[0] for call in mac.call_args_list] == [
        ["/usr/bin/open", "-a", "Brave Browser"],
        ["/usr/bin/open", "-a", "Brave Browser", "https://music.youtube.com"],
    ]
    assert all(call.kwargs == {"check": True} for call in mac.call_args_list)


@pytest.mark.parametrize("apps,browser", [([], "brave"), (["safari", "brave"], "safari")])
def test_url_uses_first_saved_browser_or_configured_default(apps, browser):
    create(apps=apps, urls=[config.SITES["youtube"]])
    actions = workspace.workspace_open_actions(workspace.load_workspace("music"))
    assert actions[-1] == action("open", browser, url=config.SITES["youtube"])


def test_add_remove_telegram_from_legacy_coding_preserves_compatible_opens(mac):
    workspace.save_workspace("coding")
    workspace.update_workspace("coding", {"operation": "add", "app": "Telegram"})
    assert workspace.load_workspace("coding") == {
        "name": "coding", "apps": ["vscode", "brave", "telegram"], "urls": []}
    workspace.update_workspace("coding", {"operation": "remove", "app": "telegram"})
    assert workspace.workspace_open_actions(workspace.load_workspace("coding")) == [
        action("open", "vscode"), action("open", "brave")]
    # The existing explicit save shortcut continues resetting the coding preset.
    workspace.save_workspace("coding")
    assert workspace.load_workspace() == {"name": "coding", "apps": ["vscode", "brave"]}
    mac.assert_not_called()


def test_update_retains_urls(mac):
    create(urls=MUSIC["urls"])
    workspace.update_workspace("music", {"operation": "add", "app": "telegram"})
    assert workspace.load_workspace("music")["urls"] == MUSIC["urls"]
    workspace.update_workspace("music", {"operation": "remove", "app": "brave"})
    assert workspace.load_workspace("music")["apps"] == ["telegram"]
    mac.assert_not_called()


def test_delete_only_selected_workspace_not_memory_other_workspaces_or_files(tmp_path, mac):
    create()
    workspace.save_workspace("coding")
    sentinel = tmp_path / "music"
    sentinel.write_text("preserve")
    with MemoryManager() as manager:
        memory_id = manager.add_memory("Preserve this memory", "user_preference")
    executor.execute(action("delete_workspace"))
    assert workspace.list_workspaces() == ["coding"]
    with MemoryManager() as manager:
        assert manager.get_memory(memory_id).content == "Preserve this memory"
    assert sentinel.read_text() == "preserve"
    mac.assert_not_called()


def test_create_duplicate_does_not_overwrite(mac):
    create()
    with pytest.raises(ActionPolicyError, match="already exists"):
        create("MUSIC", apps=["telegram"])
    assert workspace.load_workspace("music")["apps"] == ["brave"]
    mac.assert_not_called()


@pytest.mark.parametrize("operation,app", [("add", "brave"), ("remove", "telegram"), ("remove", "brave")])
def test_duplicate_missing_or_last_app_update_rejected_atomically(operation, app, mac):
    create()
    before = workspace.load_workspace("music")
    with pytest.raises(ActionPolicyError):
        workspace.update_workspace("music", {"operation": operation, "app": app})
    assert workspace.load_workspace("music") == before
    mac.assert_not_called()


@pytest.mark.parametrize("verb,params", [("restore_workspace", {}), ("delete_workspace", {}),
    ("update_workspace", {"operation": "add", "app": "telegram"})])
def test_missing_workspace_fails_safely(verb, params, mac):
    with pytest.raises(ActionPolicyError, match="has not been saved"):
        getattr(workspace, verb)("missing", params)
    mac.assert_not_called()


@pytest.mark.parametrize("app", ["chrome", "Terminal", "Finder", "kernel_task", "123", "/Applications/VS CODE.app",
    "vscode --args", "kill -9", "youtube", "desktop", "https://music.youtube.com"])
def test_unsupported_apps_rejected_by_policy_and_handlers(app, mac):
    for verb, params in [("create_workspace", {"apps": [app], "urls": []}),
                         ("update_workspace", {"operation": "add", "app": app})]:
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([action(verb, **params)])
        with pytest.raises(ActionPolicyError):
            getattr(workspace, verb)("music", params)
    assert workspace.list_workspaces() == []
    mac.assert_not_called()


@pytest.mark.parametrize("url", ["https://unconfigured.example", "http://localhost", "file:///tmp/a",
    "javascript:alert(1)", "https://music.youtube.com/watch?v=x", "https://music.youtube.com/#x",
    "https://user:password@music.youtube.com", "https://music.youtube.com;anything", "--args"])
def test_unconfigured_or_unsafe_urls_rejected_before_persistence(url, mac):
    with pytest.raises(ActionPolicyError):
        create(urls=[url])
    assert workspace.list_workspaces() == []
    mac.assert_not_called()


@pytest.mark.parametrize("verb,params", [
    ("create_workspace", {}), ("create_workspace", {"apps": "brave", "urls": []}),
    ("create_workspace", {"apps": ["brave"], "urls": [], "command": "anything"}),
    ("create_workspace", {"apps": [["brave"]], "urls": []}),
    ("create_workspace", {"apps": [], "urls": []}),
    ("create_workspace", {"apps": ["brave", "BRAVE"], "urls": []}),
    ("create_workspace", {"apps": [], "urls": ["https://music.youtube.com"] * 2}),
    ("create_workspace", {"apps": ["brave"] * (MAX_ACTIONS + 1), "urls": []}),
    ("update_workspace", {"operation": "force-close", "app": "brave"}),
    ("update_workspace", {"operation": "add", "app": "brave", "pid": "1"}),
    ("update_workspace", {"operation": "add", "app": ["brave"]}),
    ("update_workspace", {"operation": "add", "url": "https://music.youtube.com"}),
    ("restore_workspace", {"force": "true"}), ("delete_workspace", {"path": "/tmp/music"}),
    ("list_workspaces", {"command": "anything"}),
])
def test_invalid_parameters_rejected(verb, params, mac):
    target = "workspaces" if verb == "list_workspaces" else "music"
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([action(verb, target, **params)])
    with pytest.raises(ActionPolicyError):
        getattr(workspace, verb)(target, params)
    mac.assert_not_called()


@pytest.mark.parametrize("name", ["", "../music", "/tmp/music", "music;command", "a" * 33, "123", "my music", "music\n"])
@pytest.mark.parametrize("verb", ["create_workspace", "restore_workspace", "update_workspace", "delete_workspace"])
def test_names_are_bounded_identifiers(name, verb):
    params = ({"apps": ["brave"], "urls": []} if verb == "create_workspace" else
              {"operation": "add", "app": "brave"} if verb == "update_workspace" else {})
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([action(verb, name, **params)])


def test_schema_allows_flat_lists_only_for_workspace_creation():
    original = action("create_workspace", apps=["brave"], urls=[])
    validated = validate_plan({"actions": [original]})
    validated["actions"][0]["params"]["apps"].append("telegram")
    assert original["params"]["apps"] == ["brave"]
    for verb in ("open", "search", "restore_workspace", "update_workspace"):
        with pytest.raises(AIPlanningError):
            validate_plan({"actions": [action(verb, apps=["brave"])]})


def test_all_restored_items_rechecked_after_configuration_change(mac):
    create(urls=MUSIC["urls"])
    with patch.dict(config.WORKSPACE_URLS, {}, clear=True), pytest.raises(ActionPolicyError):
        workspace.restore_workspace("music")
    mac.assert_not_called()


@pytest.mark.parametrize("definition", [
    {"name": "other", "apps": ["brave"], "urls": []},
    {"name": "music", "apps": ["brave", "chrome"], "urls": []},
    {"name": "music", "apps": ["brave"], "urls": ["https://unconfigured.example"]},
    {"name": "music", "apps": ["brave"], "urls": [], "command": "anything"},
])
def test_tampered_named_record_rejected_before_first_launch(definition, mac):
    with MemoryManager() as manager:
        manager.save_workspace("music", json.dumps(definition))
    with pytest.raises(ActionPolicyError):
        workspace.restore_workspace("music")
    mac.assert_not_called()


def test_action_policy_can_block_open_list_before_save_or_restore(mac):
    create(urls=MUSIC["urls"])
    original = ActionPolicy.validate
    def reject_opens(self, actions, **kwargs):
        if any(item["action"] == "open" for item in actions):
            raise ActionPolicyError("Open denied")
        return original(self, actions, **kwargs)
    with patch.object(ActionPolicy, "validate", reject_opens):
        with pytest.raises(ActionPolicyError):
            create("new")
        with pytest.raises(ActionPolicyError):
            workspace.restore_workspace("music")
        with pytest.raises(ActionPolicyError):
            workspace.update_workspace("music", {"operation": "add", "app": "telegram"})
    assert workspace.list_workspaces() == ["music"]
    assert workspace.load_workspace("music") == MUSIC
    mac.assert_not_called()


def test_legacy_table_migration_preserves_rows_and_other_memory(tmp_path, mac):
    with MemoryManager() as manager:
        store = manager.store
        memory_id = manager.add_memory("Keep me", "user_preference")
        legacy = json.dumps({"name": "coding", "apps": ["vscode", "brave"]})
        with store.transaction():
            store._execute("CREATE TABLE workspaces (name TEXT PRIMARY KEY CHECK(name = 'coding'), definition TEXT NOT NULL)")
            store._execute("INSERT INTO workspaces VALUES (?, ?)", ("coding", legacy))
    assert workspace.load_workspace() == json.loads(legacy)
    create()
    with MemoryManager() as manager:
        assert manager.load_workspace("coding") == legacy
        assert manager.list_workspaces() == ["coding", "music"]
        assert manager.get_memory(memory_id).content == "Keep me"
        assert not manager.store._execute("SELECT name FROM sqlite_master WHERE name='workspaces_upgrade'", rows=True)
    workspace.restore_workspace("coding")
    assert mac.call_count == 2


def test_migration_failure_rolls_back_original_table_and_definition():
    with MemoryStore() as store:
        legacy = json.dumps({"name": "coding", "apps": ["vscode", "brave"]})
        with store.transaction():
            store._execute("CREATE TABLE workspaces (name TEXT PRIMARY KEY CHECK(name = 'coding'), definition TEXT NOT NULL)")
            store._execute("INSERT INTO workspaces VALUES (?, ?)", ("coding", legacy))
        original = store._execute
        def fail(sql, *args, **kwargs):
            if sql.startswith("ALTER TABLE"):
                raise MemoryStorageError("Injected migration failure")
            return original(sql, *args, **kwargs)
        with patch.object(store, "_execute", fail), pytest.raises(MemoryStorageError):
            store.list_workspaces()
        assert store._execute("SELECT definition FROM workspaces", rows=True)[0]["definition"] == legacy
        assert "CHECK" in store._execute("SELECT sql FROM sqlite_master WHERE name='workspaces'", rows=True)[0]["sql"]
        assert not store._execute("SELECT name FROM sqlite_master WHERE name='workspaces_upgrade'", rows=True)


@pytest.mark.parametrize("command", ["List my workspaces", "list workspaces"])
def test_existing_list_route_delegates_to_workspace_policy(command, capsys, mac):
    create()
    with patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy, \
         patch.object(main, "process_natural_language_command") as ai:
        assert main.handle_command(command)
    ai.assert_not_called()
    assert any(call.args[1] == [action("list_workspaces", "workspaces")] for call in policy.call_args_list)
    assert "Saved workspaces: music" in capsys.readouterr().out
    mac.assert_not_called()


@pytest.mark.parametrize("command,item", [
    ("Create a workspace called music with Brave and YouTube Music", action("create_workspace", **{k:v for k,v in MUSIC.items() if k != "name"})),
    ("Restore my music workspace", action("restore_workspace")),
    ("Add Telegram to my coding workspace", action("update_workspace", "coding", operation="add", app="telegram")),
    ("Remove Telegram from my coding workspace", action("update_workspace", "coding", operation="remove", app="telegram")),
    ("Delete my music workspace", action("delete_workspace")),
    ("Please list my workspaces", action("list_workspaces", "workspaces")),
])
def test_natural_language_management_pipeline(command, item, mac):
    workspace.save_workspace("coding")
    workspace.update_workspace("coding", {"operation": "add", "app": "telegram"})
    if item["action"] != "create_workspace":
        create(urls=MUSIC["urls"])
    if item["params"].get("operation") == "add":
        workspace.update_workspace("coding", {"operation": "remove", "app": "telegram"})
    provider = Mock(generate_text=Mock(return_value=json.dumps({"actions": [item]})))
    assert main.route_command(command) == ("ai", None)
    result = process_natural_language_command(command, brain=AIBrain(provider=provider))
    assert result == [item]
    assert mac.call_count == (2 if item["action"] == "restore_workspace" else 0)
    prompt = provider.generate_text.call_args.args[0]
    assert "create_workspace" in prompt and "https://music.youtube.com" in prompt


@pytest.mark.parametrize("system", ["Windows", "Linux"])
def test_workspace_actions_remain_unavailable_off_mac(system, mac):
    with patch("platform.system", return_value=system):
        for verb in WORKSPACE_ACTIONS:
            with pytest.raises(ActionPolicyError):
                getattr(workspace, verb)("music", {})
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([action("open", "brave", url=MUSIC["urls"][0])])
        assert main.handle_command("List my workspaces") == []
        with MemoryStore() as store:
            assert not store._execute("SELECT name FROM sqlite_master WHERE name='workspaces'", rows=True)
    mac.assert_not_called()
