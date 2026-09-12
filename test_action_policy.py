from ai.action_policy import ActionPolicy, ActionPolicyError


def assert_policy_rejects(actions):
    try:
        ActionPolicy().validate(actions)
        assert False, "Expected ActionPolicyError"
    except ActionPolicyError:
        pass


def test_safe_open_plan_is_allowed():
    actions = [{"action": "open", "target": "brave", "params": {}}]
    assert ActionPolicy().validate(actions) == actions


def test_browser_aware_open_plan_is_allowed():
    actions = [
        {
            "action": "open",
            "target": "youtube",
            "params": {
                "browser": "brave",
                "url": "https://www.youtube.com",
            },
        },
        {
            "action": "open",
            "target": "brave",
            "params": {"browser": "brave"},
        },
    ]
    assert ActionPolicy().validate(actions) == actions


def test_realistic_youtube_search_plan_is_allowed():
    actions = [
        {
            "action": "open",
            "target": "brave",
            "params": {
                "theme": "dark",
                "url": "https://www.youtube.com/results?search_query=Python",
            },
        }
    ]
    assert ActionPolicy().validate(actions) == actions


def test_realistic_preferred_browser_plan_is_allowed():
    actions = [
        {
            "action": "open",
            "target": "brave",
            "params": {"mode": "dark"},
        }
    ]
    assert ActionPolicy().validate(actions) == actions


def test_safe_search_plan_is_allowed():
    actions = [
        {
            "action": "search",
            "target": "Python",
            "params": {"engine": "google", "query": "Python"},
        }
    ]
    assert ActionPolicy().validate(actions) == actions


def test_safe_list_and_help_plans_are_allowed():
    actions = [
        {"action": "list", "target": "sites", "params": {}},
        {"action": "help", "target": "help", "params": {}},
    ]
    assert ActionPolicy().validate(actions) == actions


def test_delete_plan_is_rejected():
    actions = [{"action": "delete", "target": "notes.txt", "params": {"type": "file"}}]
    assert_policy_rejects(actions)


def test_unsupported_and_mutating_actions_are_rejected():
    for action_name in ("execute", "create", "rename", "copy", "move"):
        actions = [{"action": action_name, "target": "notes.txt", "params": {}}]
        assert_policy_rejects(actions)


def test_unsafe_parameters_are_rejected():
    actions = [{"action": "open", "target": "brave", "params": {"command": "rm -rf /"}}]
    assert_policy_rejects(actions)


def test_unsafe_search_query_is_rejected():
    actions = [
        {
            "action": "search",
            "target": "Python",
            "params": {"query": "Python; rm -rf /"},
        }
    ]
    assert_policy_rejects(actions)


def test_malformed_parameter_type_is_rejected():
    actions = [{"action": "open", "target": "brave", "params": {"url": 123}}]
    assert_policy_rejects(actions)


def test_unsupported_browser_parameter_is_rejected():
    actions = [{"action": "open", "target": "brave", "params": {"browser": "terminal"}}]
    assert_policy_rejects(actions)


def test_unsupported_theme_parameter_is_rejected():
    actions = [{"action": "open", "target": "brave", "params": {"theme": "terminal"}}]
    assert_policy_rejects(actions)


def test_unsupported_mode_parameter_is_rejected():
    actions = [{"action": "open", "target": "brave", "params": {"mode": "terminal"}}]
    assert_policy_rejects(actions)


def test_unsafe_open_target_is_rejected():
    actions = [{"action": "open", "target": "brave; rm -rf /", "params": {}}]
    assert_policy_rejects(actions)


def test_unsupported_open_target_is_rejected():
    actions = [{"action": "open", "target": "unknown application", "params": {}}]
    assert_policy_rejects(actions)
