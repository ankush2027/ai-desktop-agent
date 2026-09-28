"""V1 argument fidelity; OS operations are mocked or confined to test resources."""

if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))

from unittest.mock import patch

import pytest

import main
from parser import parse_command


@pytest.mark.parametrize("verb", ["create", "delete"])
@pytest.mark.parametrize("target", [
    "A.txt", "MyReport.txt", "the notes.txt", "a an to me.txt",
    "My  Report.txt", "My\tReport.txt", "please keep me.txt",
    "O'Brien.txt", "café 日本語.txt", r"C:\Users\Someone\My Documents\A.txt",
])
def test_single_file_argument_preserved(verb, target):
    expected = {"action": verb, "target": target, "params": {"type": "file"}}
    assert parse_command(f"{verb.upper()} FILE {target}") == [expected]
    assert main.route_command(f"{verb} file {target}") == ("v1", [expected])


@pytest.mark.parametrize("verb,key", [("rename", "new_name"), ("copy", "destination"), ("move", "destination")])
@pytest.mark.parametrize("source,destination", [("MyReport.txt", "YourReport.txt"), ("the", "to"), ("A.txt", r"Folder\B.txt")])
def test_two_arguments_preserved(verb, key, source, destination):
    assert parse_command(f"{verb} file {source} {destination}") == [
        {"action": verb, "target": source, "params": {"type": "file", key: destination}},
    ]


@pytest.mark.parametrize("verb,key", [("rename", "new_name"), ("copy", "destination"), ("move", "destination")])
def test_quoted_two_arguments_and_windows_backslashes(verb, key):
    source = r"C:\My Documents\the Report.txt"
    destination = r"D:\To Me\Research and Notes.txt"
    command = f'{verb} file "{source}" "{destination}"'
    assert parse_command(command) == [
        {"action": verb, "target": source, "params": {"type": "file", key: destination}},
    ]


@pytest.mark.parametrize("quote", ['"', "'"])
@pytest.mark.parametrize("target", ["Research and Notes.txt", "  A  B.txt  ", "and"])
def test_quoted_single_argument(quote, target):
    assert parse_command(f"delete file {quote}{target}{quote}")[0]["target"] == target


@pytest.mark.parametrize("command", [
    "rename file MyReport.txt", "copy file A.txt", "move file A.txt",
    "rename file My Report.txt New Report.txt", "move file A B C",
    "copy file A to B", 'delete file "unfinished', 'delete file "A"B',
    'delete file "A" B', 'delete file ""', "delete file Research and Notes.txt",
    "delete file A and", "delete file A and and delete file B", "delete file",
    "create file A\ndelete file B", "delete file A\x00B",
    "create file A.txt and rename file B.txt",
])
def test_invalid_file_syntax_executes_nothing_and_never_calls_ai(command):
    assert parse_command(command) is None
    with patch.object(main, "execute") as execute, patch.object(main, "process_natural_language_command") as ai:
        assert main.handle_command(command) == []
    execute.assert_not_called()
    ai.assert_not_called()


def test_chain_validated_in_full_and_argument_and_is_quoted():
    commands = parse_command('create file "Research and Notes.txt" and delete file the Old.txt')
    assert [(item["action"], item["target"]) for item in commands] == [
        ("create", "Research and Notes.txt"), ("delete", "the Old.txt"),
    ]
    assert main.route_command('create file "Research and Notes.txt" and delete file the Old.txt')[0] == "v1"
    assert parse_command("create file A.txt and rename file B.txt") is None
    assert main.route_command("create file A.txt and open file A.txt")[0] == "v1"


@pytest.mark.parametrize("command,action,target,params", [
    ("open yt", "open", "yt", {}), ("Open MyReport.txt", "open", "MyReport.txt", {}),
    ("search The Python Guide", "search", "The Python Guide", {}),
    ("create folder Projects", "create", "Projects", {"type": "folder"}),
    ("remove file Old.txt", "delete", "Old.txt", {"type": "file"}),
    ("list sites", "list", "sites", {}), ("HELP", "help", "", {}),
    ("exit", "exit", "", {}),
])
def test_existing_contracts(command, action, target, params):
    assert parse_command(command) == [{"action": action, "target": target, "params": params}]


def test_natural_language_routing_is_preserved():
    assert main.route_command("Make me a plan") == ("ai", None)
    assert main.route_command("Please open my preferred browser") == ("ai", None)


@pytest.mark.parametrize("punctuation", [".", "?", "!", "?!", "..."])
@pytest.mark.parametrize("verb,target", [("Open", "YouTube"), ("Open", "Calculator"),
                                        ("Open", "Google"), ("launch", "yt"),
                                        ("start", "brave"), ("open", "downloads")])
def test_terminal_punctuation_on_configured_open_targets(verb, target, punctuation):
    command = f"  {verb} {target}{punctuation}  "
    expected = [{"action": "open", "target": target, "params": {}}]
    assert main.route_command(command) == ("v1", expected)
    # Normalization belongs to routing; direct parsing still preserves operands.
    assert parse_command(command)[0]["target"] == target + punctuation


@pytest.mark.parametrize("voice", [False, True])
@pytest.mark.parametrize("command,target,action", [("Open YouTube.", "YouTube", "open"),
                                                  ("Open Calculator!", "Calculator", "open"),
                                                  ("Open Google?", "Google", "open"),
                                                  ("Search Python?", "Python?", "search")])
def test_punctuated_controller_commands_never_call_ai(voice, command, target, action):
    from unittest.mock import Mock
    from interaction import InteractionController
    controller = InteractionController(lambda update: None,
        voice_input=Mock(recognize=Mock(return_value=command)))
    with patch.object(main, "execute") as execute, \
         patch.object(main, "process_natural_language_command") as ai:
        assert controller.submit_voice() if voice else controller.submit_text(command)
    execute.assert_called_once_with({"action": action, "target": target, "params": {}})
    ai.assert_not_called()


@pytest.mark.parametrize("command", [
    'open "youtube."', "open 'calculator!'", "open UnknownApp!",
    "open report.txt.", r"open C:\Reports\youtube.", "open https://youtube.com/watch?v=test!",
    "Please open YouTube.", "open youtube and open calculator.",
])
def test_ambiguous_open_and_ai_commands_are_not_rewritten(command):
    with patch.object(main, "process_natural_language_command", return_value=[]) as ai, \
         patch.object(main, "execute") as execute:
        main.handle_command(command)
    ai.assert_called_once_with(command)
    execute.assert_not_called()


@pytest.mark.parametrize("command,target,params", [
    ('open file youtube.', 'file youtube.', {}),
    ('open folder calculator!', 'folder calculator!', {}),
    ('create file youtube.', 'youtube.', {'type': 'file'}),
    ('rename file old.txt new.txt!', 'old.txt', {'type': 'file', 'new_name': 'new.txt!'}),
    ('copy file old.txt new.txt?', 'old.txt', {'type': 'file', 'destination': 'new.txt?'}),
    ('search "Python?"', 'Python?', {}),
    ('search https://example.com/path?q=Python?', 'https://example.com/path?q=Python?', {}),
    ('search release-3.12!', 'release-3.12!', {}),
])
def test_literal_argument_and_parameter_punctuation_preserved(command, target, params):
    route, parsed = main.route_command(command)
    assert route == "v1"
    assert parsed[0]["target"] == target
    assert parsed[0]["params"] == params


def test_existing_literal_path_wins_over_punctuation_normalization(monkeypatch):
    monkeypatch.setattr(main.os.path, "exists", lambda path: path == "youtube.")
    assert main.route_command("open youtube.") == (
        "v1", [{"action": "open", "target": "youtube.", "params": {}}])


def test_whitespace_before_terminal_punctuation():
    assert main.route_command("Open YouTube .") == (
        "v1", [{"action": "open", "target": "YouTube", "params": {}}])


@pytest.mark.parametrize("verb", ["copy", "move"])
def test_copy_move_dispatch_keeps_existing_destination_contract(verb):
    # Handler destination/new_name alignment is a separate audit issue.
    with patch.object(main, "execute") as execute:
        main.handle_command(f'{verb} file "the My Report.txt" "To Me.txt"')
    execute.assert_called_once_with({
        "action": verb, "target": "the My Report.txt",
        "params": {"type": "file", "destination": "To Me.txt"},
    })


@pytest.mark.parametrize("command,expected", [
    ("delete file the notes.txt", "the notes.txt"),
    ("create file A.txt", "A.txt"),
    ('rename file "My Report.txt" "New Report.txt"', "My Report.txt"),
])
def test_cli_to_real_executor_preserves_os_arguments(command, expected, tmp_path):
    if command.startswith("rename"):
        (tmp_path / expected).write_text("temporary source")
    with patch("actions.delete_file.os.remove") as remove, \
         patch("actions.files.open", create=True) as create, \
         patch("actions.rename_file.os.rename") as rename:
        main.handle_command(command)
    if command.startswith("delete"):
        remove.assert_called_once_with(expected)
    elif command.startswith("create"):
        create.assert_called_once_with(expected, "x")
    else:
        rename.assert_called_once_with(expected, "New Report.txt")
