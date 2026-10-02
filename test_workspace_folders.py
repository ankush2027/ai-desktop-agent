"""Trusted workspace folder aliases; launches mocked, filesystem confined to tmp."""
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import config
import executor
import main
from actions import workspace
from actions.workspace_definition import resolve_workspace_folder
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.brain import AIBrain
from ai.errors import AIPlanningError
from ai.orchestrator import process_natural_language_command
from ai.plan_schema import validate_plan
from memory import MemoryManager


@pytest.fixture(autouse=True)
def folders(tmp_path):
    paths = {"ai-desktop-agent": tmp_path / "ai-desktop-agent", "projects": tmp_path / "Test"}
    for path in paths.values():
        path.mkdir()
    with patch("platform.system", return_value="Darwin"), \
         patch.object(Path, "home", return_value=tmp_path), \
         patch.dict(config.WORKSPACE_FOLDERS, {key: str(value) for key, value in paths.items()}, clear=True), \
         patch("actions.platforms.subprocess.run") as run, \
         patch("subprocess.Popen") as popen, patch("os.system") as shell:
        yield paths, run
        popen.assert_not_called()
        shell.assert_not_called()


def item(verb="create_workspace", target="coding2", **params):
    return {"action": verb, "target": target, "params": params}


def create(folders=None):
    workspace.create_workspace("coding2", {"apps": ["vscode"], "urls": [],
                                          "folders": ["ai-desktop-agent"] if folders is None else folders})


def test_schema_accepts_flat_folder_alias_list_and_copies():
    original = item(apps=["vscode"], urls=[], folders=["ai-desktop-agent"])
    copied = validate_plan({"actions": [original]})["actions"][0]
    copied["params"]["folders"].append("projects")
    assert original["params"]["folders"] == ["ai-desktop-agent"]


@pytest.mark.parametrize("params", [
    {"apps": ["vscode"], "folders": ["ai-desktop-agent"]},
    {"apps": ["vscode"]},
    {"apps": ["vscode"], "urls": ["https://github.com"], "folders": ["ai-desktop-agent"]},
    {"apps": ["vscode"], "urls": ["https://github.com"]},
])
def test_planner_normalizes_workspace_urls_before_policy(params, folders):
    payload = {"actions": [item(**params)]}
    raw = json.dumps(payload)
    brain = AIBrain(provider=Mock(generate_text=Mock(return_value=raw)))
    plan = brain.plan("Create a workspace called coding2")
    expected = {"actions": [item(**{**params, "urls": params.get("urls", [])})]}
    assert plan == expected
    assert ActionPolicy().validate(plan["actions"]) == expected["actions"]
    assert json.dumps(payload) == raw
    assert brain.validate_action_plan(payload) == expected
    assert json.dumps(payload) == raw
    folders[1].assert_not_called()


@pytest.mark.parametrize("alias", ["unknown", "/tmp", "~/Documents", "../projects"])
def test_default_urls_does_not_bypass_folder_policy(alias):
    brain = AIBrain(provider=Mock())
    plan = brain.validate_action_plan({"actions": [item(apps=["vscode"], folders=[alias])]})
    assert plan["actions"][0]["params"]["urls"] == []
    with pytest.raises(ActionPolicyError, match="trusted configured alias"):
        ActionPolicy().validate(plan["actions"])


def test_default_urls_keeps_apps_required_and_direct_policy_strict():
    brain = AIBrain(provider=Mock())
    plan = brain.validate_action_plan({"actions": [item(folders=["projects"])]})
    with pytest.raises(ActionPolicyError, match="requires apps and urls"):
        ActionPolicy().validate(plan["actions"])
    with pytest.raises(ActionPolicyError, match="requires apps and urls"):
        ActionPolicy().validate([item(apps=["vscode"], folders=["projects"])])


@pytest.mark.parametrize("urls", [None, "", {}, [None]])
def test_planner_does_not_default_explicit_invalid_urls(urls):
    with pytest.raises(AIPlanningError):
        AIBrain(provider=Mock()).validate_action_plan({"actions": [item(apps=["vscode"], urls=urls)]})


def test_create_persists_aliases_not_paths_and_does_not_launch(folders):
    create()
    expected = {"name": "coding2", "apps": ["vscode"], "urls": [], "folders": ["ai-desktop-agent"]}
    assert workspace.load_workspace("coding2") == expected
    with MemoryManager() as manager:
        assert json.loads(manager.load_workspace("coding2")) == expected
    folders[1].assert_not_called()


def test_restore_apps_urls_folders_uses_normal_policy_and_executor(folders):
    paths, run = folders
    workspace.create_workspace("coding2", {"apps": ["vscode", "brave"], "urls": ["https://github.com"],
                                          "folders": ["ai-desktop-agent", "projects"]})
    with patch.object(ActionPolicy, "validate", autospec=True, side_effect=ActionPolicy.validate) as policy, \
         patch.object(executor, "execute", wraps=executor.execute) as execute:
        def launching(*args, **kwargs):
            assert any(len(call.args[1]) == 5 and all(a["action"] == "open" for a in call.args[1])
                       for call in policy.call_args_list)
        run.side_effect = launching
        workspace.restore_workspace("coding2")
        assert len(execute.call_args_list) == 5
        assert all(call.args[0]["action"] == "open" for call in execute.call_args_list)
    assert [call.args[0] for call in run.call_args_list] == [
        ["/usr/bin/open", "-a", "/Applications/VS CODE.app"],
        ["/usr/bin/open", "-a", "Brave Browser"],
        ["/usr/bin/open", "-a", "Brave Browser", "https://github.com"],
        ["/usr/bin/open", str(paths["ai-desktop-agent"])],
        ["/usr/bin/open", str(paths["projects"])],
    ]
    assert all(call.kwargs == {"check": True} for call in run.call_args_list)


def test_add_remove_folder_preserves_apps_urls_and_directory(folders):
    create()
    workspace.update_workspace("coding2", {"operation": "add", "folder": "PROJECTS"})
    assert workspace.load_workspace("coding2")["folders"] == ["ai-desktop-agent", "projects"]
    workspace.update_workspace("coding2", {"operation": "remove", "folder": "projects"})
    saved = workspace.load_workspace("coding2")
    assert saved == {"name": "coding2", "apps": ["vscode"], "urls": [], "folders": ["ai-desktop-agent"]}
    assert folders[0]["projects"].is_dir()
    folders[1].assert_not_called()


@pytest.mark.parametrize("definition", [
    {"name": "coding", "apps": ["vscode", "brave"]},
    {"name": "music", "apps": ["brave"], "urls": ["https://music.youtube.com"]},
    {"name": "test", "apps": ["telegram"], "urls": []},
])
def test_no_folder_legacy_records_unchanged(definition):
    with MemoryManager() as manager:
        manager.save_workspace(definition["name"], json.dumps(definition))
    assert workspace.load_workspace(definition["name"]) == definition
    assert all(not action["target"].startswith("folder ")
               for action in workspace.workspace_open_actions(definition))


def test_folder_update_on_legacy_coding():
    workspace.save_workspace("coding")
    workspace.update_workspace("coding", {"operation": "add", "folder": "projects"})
    assert workspace.load_workspace() == {"name": "coding", "apps": ["vscode", "brave"],
                                         "urls": [], "folders": ["projects"]}


@pytest.mark.parametrize("alias", ["unknown", "../projects", "projects/..", "/tmp", "~/Desktop/Test",
    "folder projects", "projects; command", "$(anything)", "projects\n", "123", "", "C:\\Test"])
def test_paths_traversal_and_unknown_aliases_rejected(alias, folders):
    for command in [item(apps=["vscode"], urls=[], folders=[alias]),
                    item("update_workspace", operation="add", folder=alias),
                    item("update_workspace", operation="remove", folder=alias)]:
        with pytest.raises(ActionPolicyError):
            ActionPolicy().validate([command])
    folders[1].assert_not_called()


def test_even_exact_catalog_path_cannot_be_supplied_by_ai(folders):
    with pytest.raises(ActionPolicyError):
        create([str(folders[0]["projects"])])


@pytest.mark.parametrize("value", ["projects", None, 1, {}, [["projects"]], [{"alias": "projects"}], [1]])
def test_invalid_folder_field_rejected_by_schema(value):
    with pytest.raises(AIPlanningError):
        validate_plan({"actions": [item(apps=[], urls=[], folders=value)]})


@pytest.mark.parametrize("params", [
    {"operation": "add", "folder": "projects", "app": "vscode"},
    {"operation": "add", "folder": ["projects"]},
    {"operation": "delete", "folder": "projects"},
    {"operation": "move", "folder": "projects"},
    {"operation": "add", "folder": "projects", "path": "/tmp"},
    {"operation": "add", "folder": "projects", "force": "true"},
    {"operation": "add", "folders": ["projects"]},
])
def test_invalid_folder_updates_rejected(params):
    with pytest.raises(ActionPolicyError):
        workspace.update_workspace("coding2", params)


def test_duplicate_and_total_item_limit():
    with pytest.raises(ActionPolicyError):
        create(["projects", "PROJECTS"])
    with pytest.raises(ActionPolicyError):
        create(["projects"] * 11)
    with pytest.raises(ActionPolicyError):
        ActionPolicy().validate([item(apps=["vscode"] * 9, urls=["https://github.com"], folders=["projects"])])


def test_missing_configured_directory_rejects_create_and_restore_before_launch(folders):
    create(["projects"])
    folders[0]["projects"].rmdir()
    with pytest.raises(ActionPolicyError):
        workspace.restore_workspace("coding2")
    with pytest.raises(ActionPolicyError):
        workspace.create_workspace("missing", {"apps": [], "urls": [], "folders": ["projects"]})
    # Removing an already missing folder changes only saved data and remains possible.
    workspace.update_workspace("coding2", {"operation": "remove", "folder": "projects"})
    assert workspace.load_workspace("coding2")["folders"] == []
    folders[1].assert_not_called()


@pytest.mark.parametrize("kind", ["file", "bundle", "outside", "traversal", "relative", "shell", "symlink"])
def test_bad_catalog_paths_do_not_bypass_local_open_policy(kind, tmp_path, folders):
    path = tmp_path / "target"
    if kind == "file":
        path = path.with_suffix(".txt")
        path.write_text("keep")
    elif kind == "bundle":
        path = path.with_suffix(".app")
        path.mkdir()
    elif kind == "outside":
        path = tmp_path.parent
    elif kind == "traversal":
        path = folders[0]["projects"] / ".." / "ai-desktop-agent"
    elif kind == "relative":
        path = Path("relative")
    elif kind == "shell":
        path = tmp_path / "bad;path"
    else:
        path.symlink_to(folders[0]["projects"], target_is_directory=True)
    with patch.dict(config.WORKSPACE_FOLDERS, {"projects": str(path)}):
        with pytest.raises(ActionPolicyError):
            create(["projects"])
    folders[1].assert_not_called()


def test_current_folder_catalog_is_rechecked_on_restore(folders):
    create()
    with patch.dict(config.WORKSPACE_FOLDERS, {}, clear=True), pytest.raises(ActionPolicyError):
        workspace.restore_workspace("coding2")
    folders[1].assert_not_called()


def test_stored_arbitrary_paths_rejected(folders):
    with MemoryManager() as manager:
        manager.save_workspace("coding2", json.dumps({"name": "coding2", "apps": ["vscode"], "urls": [],
                                                      "folders": [str(folders[0]["projects"])]}))
    with pytest.raises(ActionPolicyError):
        workspace.restore_workspace("coding2")
    folders[1].assert_not_called()


def test_policy_rejection_blocks_all_workspace_launches(folders):
    create()
    original = ActionPolicy.validate
    def reject(self, actions, **kwargs):
        if any(a["action"] == "open" for a in actions):
            raise ActionPolicyError("Denied")
        return original(self, actions, **kwargs)
    with patch.object(ActionPolicy, "validate", reject), pytest.raises(ActionPolicyError):
        workspace.restore_workspace("coding2")
    folders[1].assert_not_called()


def test_adapter_rechecks_link_replacement_after_policy(folders):
    path = folders[0]["projects"]
    approved = ActionPolicy().validate([{"action": "open", "target": f"folder {resolve_workspace_folder('projects')}", "params": {}}])
    with patch.object(Path, "is_symlink", lambda p: p == path), pytest.raises(ValueError):
        executor.execute(approved[0])
    folders[1].assert_not_called()


@pytest.mark.parametrize("verb,phrase,params", [
    ("create_workspace", "Create a workspace called coding2 with VS Code and the ai-desktop-agent folder",
     {"apps": ["vscode"], "urls": [], "folders": ["ai-desktop-agent"]}),
    ("update_workspace", "Add the projects folder to coding2", {"operation": "add", "folder": "projects"}),
    ("update_workspace", "Remove the projects folder from coding2", {"operation": "remove", "folder": "projects"}),
])
def test_natural_language_planner_schema_policy_pipeline(verb, phrase, params, folders):
    if verb == "update_workspace":
        create(["ai-desktop-agent", "projects"] if params["operation"] == "remove" else None)
    assert main.route_command(phrase) == ("ai", None)
    provider = Mock(generate_text=Mock(return_value=json.dumps({"actions": [item(verb, **params)]})))
    assert process_natural_language_command(phrase, brain=AIBrain(provider=provider)) == [item(verb, **params)]
    prompt = provider.generate_text.call_args.args[0]
    assert "folder=alias" in prompt and "ai-desktop-agent" in prompt
    assert str(folders[0]["projects"]) not in prompt
    folders[1].assert_not_called()


def test_folder_only_workspace_and_last_item_removal():
    workspace.create_workspace("folderonly", {"apps": [], "urls": [], "folders": ["projects"]})
    with pytest.raises(ActionPolicyError):
        workspace.update_workspace("folderonly", {"operation": "remove", "folder": "projects"})
    assert workspace.load_workspace("folderonly")["folders"] == ["projects"]


def test_windows_workspace_rejection_unchanged(folders):
    with patch("platform.system", return_value="Windows"), pytest.raises(ActionPolicyError):
        create()
    folders[1].assert_not_called()
