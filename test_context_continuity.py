"""Structured continuity uses isolated storage, never a live AI provider."""

if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import main
import logger
from context import ContextEngine
from context.events import ContextEvent, ContextEventType, parse_context_event
from context.continuity import NO_CONTINUITY
from memory import MemoryManager, MemoryStore
from memory.episodes import ContextStateError
from memory.errors import MemoryStorageError


@pytest.fixture
def core():
    with MemoryManager() as manager:
        yield ContextEngine(manager)


def test_active_state_separates_pending_completed_and_intentions(core):
    manager = core.memory_manager
    episode = manager.start_episode("project")
    intention = manager.add_context_task("AI project", kind="intention", trigger="none")
    pending = manager.add_context_task("browser reliability")
    done = manager.add_context_task("Gmail workflow")
    manager.complete_context_task(done.id)
    state = core.get_continuity()
    assert state.episode['id'] == episode.id and state.episode['status'] == 'active'
    assert [item['id'] for item in state.active_intentions] == [intention.id]
    assert [item['id'] for item in state.pending_tasks] == [pending.id]
    assert [item['id'] for item in state.completed_tasks] == [done.id]
    assert state.last_activity['kind'] == 'task_completed'
    assert state.last_activity['item_id'] == done.id
    assert 'browser reliability' in state.summary()
    assert 'Already completed: Gmail workflow' in state.summary()
    json.dumps(state.to_dict())


def test_closed_state_persists_without_reopening_or_replaying(core):
    manager = core.memory_manager
    episode = manager.start_episode("college")
    task = manager.add_context_task("submit project")
    manager.close_episode()
    before = manager.store.db_path.read_bytes()
    state = core.get_continuity()
    assert state.episode['id'] == episode.id and state.episode['status'] == 'closed'
    assert state.episode['ended_at']
    assert state.pending_tasks[0]['id'] == task.id
    assert manager.get_active_episode() is None
    assert manager.store.db_path.read_bytes() == before
    with MemoryStore(manager.store.db_path) as store:
        assert ContextEngine(MemoryManager(store)).get_continuity().to_dict() == state.to_dict()


def test_older_unfinished_work_beats_newer_trivial_note(core):
    manager = core.memory_manager
    old = manager.start_episode("project")
    manager.add_context_task("finish tests")
    manager.close_episode()
    manager.start_episode("break")
    manager.add_context_note("tea")
    assert core.get_continuity().episode['id'] == old.id
    assert 'tea' not in core.get_continuity().summary()


def test_empty_active_episode_does_not_hide_previous_work(core):
    manager = core.memory_manager
    old = manager.start_episode("project")
    manager.add_context_task("finish tests")
    manager.close_episode()
    manager.start_episode()
    assert core.get_continuity().episode['id'] == old.id


def test_active_unfinished_work_beats_closed_unfinished_work(core):
    manager = core.memory_manager
    manager.start_episode("old")
    manager.add_context_task("old task")
    manager.close_episode()
    current = manager.start_episode("current")
    manager.add_context_task("current intention", kind="intention")
    assert core.get_continuity().episode['id'] == current.id


def test_completed_work_beats_note_only_episode(core):
    manager = core.memory_manager
    work = manager.start_episode("work")
    task = manager.add_context_task("finished task")
    manager.complete_context_task(task.id)
    manager.close_episode()
    manager.start_episode("break")
    manager.add_context_note("tea")
    state = core.get_continuity()
    assert state.episode['id'] == work.id
    assert not state.pending_tasks and not state.active_intentions
    assert "No unfinished" in state.summary()


def test_selection_uses_task_activity_not_just_episode_creation(core, monkeypatch):
    manager = core.memory_manager
    monkeypatch.setattr('memory.manager.now', lambda: '2026-09-20T10:00:00+00:00')
    older = manager.start_episode("older")
    task = manager.add_context_task("older task")
    manager.close_episode()
    monkeypatch.setattr('memory.manager.now', lambda: '2026-09-21T10:00:00+00:00')
    newer = manager.start_episode("newer")
    next_task = manager.add_context_task("newer task")
    manager.complete_context_task(next_task.id)
    manager.close_episode()
    assert core.get_continuity().episode['id'] == older.id  # unfinished first
    monkeypatch.setattr('memory.manager.now', lambda: '2026-09-22T10:00:00+00:00')
    manager.complete_context_task(task.id)
    state = core.get_continuity()
    assert state.episode['id'] == older.id != newer.id
    assert state.last_activity['at'] == '2026-09-22T10:00:00+00:00'


def test_scoped_notes_and_only_explicit_memory_refs_are_retrieved(core):
    manager = core.memory_manager
    episode = manager.start_episode("project")
    linked = manager.add_memory("Python preference", "user_preference")
    manager.add_memory("unrelated private memory", "user_preference")
    manager.update_episode(memory_ids=[linked])
    manager.add_context_note("current progress", category="contextual")
    note = manager.add_context_note("temporary hint", category="temporary")
    state = core.get_continuity()
    assert state.episode['id'] == episode.id
    assert len(state.relevant_notes) == 2
    assert state.last_activity['item_id'] == note.id
    assert [item['id'] for item in state.relevant_memories] == [linked]
    assert 'unrelated private' not in json.dumps(state.to_dict())
    assert 'unrelated private' not in state.summary()
    manager.delete_memory(linked)
    assert core.get_continuity().relevant_memories == []


def test_memory_reference_only_and_deleted_reference_behavior(core):
    manager = core.memory_manager
    manager.start_episode()
    linked = manager.add_memory("linked info", "fact")
    manager.update_episode(memory_ids=[linked])
    assert core.get_continuity().relevant_memories[0]['id'] == linked
    manager.delete_memory(linked)
    assert core.get_continuity() is None


def test_exact_name_filter_and_legacy_snapshot_are_preserved(core):
    manager = core.memory_manager
    old = manager.start_episode("project")
    manager.add_context_task("unfinished")
    manager.close_episode()
    latest = manager.start_episode("break")
    manager.add_context_note("tea")
    assert core.continuity_snapshot()['episode']['id'] == latest.id
    assert core.get_continuity().episode['id'] == old.id
    assert core.get_continuity("break").episode['id'] == latest.id
    assert core.get_continuity("missing") is None


@pytest.mark.parametrize('closed', [False, True])
def test_empty_episode_is_not_evidence_of_work(core, closed):
    assert core.get_continuity() is None
    core.memory_manager.start_episode("college")
    if closed:
        core.memory_manager.close_episode()
    assert core.get_continuity() is None
    result = core.handle_event(ContextEvent(ContextEventType.CONTINUE))
    assert result.message == NO_CONTINUITY and result.continuity is None


@pytest.mark.parametrize('phrase', [
    'Continue what I was doing.', 'Where did I leave off?', 'What was I working on?',
    'Where was I?', 'Continue my last task.', 'What was I doing?',
    'What was unfinished?', 'What was already completed?', 'What should I continue?',
])
def test_continuity_variants_route_without_ai_or_execution(phrase, monkeypatch, capsys):
    ai = Mock(side_effect=AssertionError('no Gemini'))
    execute = Mock(side_effect=AssertionError('no execution'))
    monkeypatch.setattr(main, 'process_natural_language_command', ai)
    monkeypatch.setattr(main, 'execute', execute)
    assert main.route_command(phrase)[0] == 'context'
    result = main.handle_command(phrase)
    assert result[0]['message'] == NO_CONTINUITY
    assert capsys.readouterr().out.strip() == NO_CONTINUITY
    ai.assert_not_called()
    execute.assert_not_called()
    assert not Path(logger.LOG_FILE).exists()


@pytest.mark.parametrize('phrase', ["I'm working on my AI project.", "I am currently working on my AI project.", "I’m working on my AI project!"])
def test_working_on_becomes_intention(core, phrase):
    core.memory_manager.start_episode()
    result = core.handle_event(parse_context_event(phrase))
    assert result.task.kind == 'intention' and result.task.trigger == 'none'
    assert result.task.description == 'my AI project'
    assert core.memory_manager.get_memory_count() == 0


def test_product_flow_reports_pending_and_completed_without_actions(monkeypatch, capsys):
    monkeypatch.setattr(main, 'execute', Mock(side_effect=AssertionError('no dispatch')))
    monkeypatch.setattr(main, 'process_natural_language_command', Mock(side_effect=AssertionError('no AI')))
    main.handle_command("I'm here.")
    main.handle_command("I'm working on my AI project.")
    main.handle_command("Remember that I need to finish the browser reliability work.")
    done = main.handle_command("Remember that I need to finish the Gmail workflow.")
    main.handle_command('complete context task ' + done[0]['task']['id'])
    main.handle_command("I'm leaving.")
    capsys.readouterr()
    result = main.handle_command('Continue what I was doing.')[0]
    output = capsys.readouterr().out
    assert 'my AI project' in output
    assert 'Unfinished: finish the browser reliability work' in output
    assert 'Already completed: finish the Gmail workflow' in output
    assert result['continuity']['episode']['status'] == 'closed'
    with MemoryManager() as manager:
        assert manager.get_active_episode() is None and manager.get_memory_count() == 0
    assert not Path(logger.LOG_FILE).exists()


def test_focused_views_omit_other_payloads(core):
    manager = core.memory_manager
    manager.start_episode()
    manager.add_context_task('pending item')
    done = manager.add_context_task('completed item')
    manager.complete_context_task(done.id)
    manager.add_context_note('private note')
    pending = core.handle_event(parse_context_event('What was unfinished?')).message
    completed = core.handle_event(parse_context_event('What was already completed?')).message
    assert 'pending item' in pending and 'completed item' not in pending
    assert 'completed item' in completed and 'pending item' not in completed
    assert 'private note' not in pending + completed


@pytest.mark.parametrize('phrase', ["I'm working on a project.", 'Remember that I need to finish tests.'])
def test_missing_active_episode_does_not_make_permanent_memory(phrase, capsys):
    assert main.handle_command(phrase) == []
    assert 'No active context' in capsys.readouterr().out
    with MemoryManager() as manager:
        assert manager.get_memory_count() == 0 and manager.get_active_episode() is None


@pytest.mark.parametrize('phrase,route', [('remember that I prefer Python', 'memory'),
    ('open yt', 'v1'), ('search where was I', 'v1'), ('please continue deployment', 'ai')])
def test_existing_routing_still_applies(phrase, route):
    assert main.route_command(phrase)[0] == route


def test_completed_intention_not_active_and_reads_do_not_change_state(core):
    manager = core.memory_manager
    manager.start_episode()
    task = manager.add_context_task('intention', kind='intention')
    manager.complete_context_task(task.id)
    before = core.continuity_snapshot()
    state = core.get_continuity()
    assert not state.active_intentions and not state.pending_tasks
    assert state.completed_tasks[0]['id'] == task.id
    assert core.continuity_snapshot() == before


def test_storage_failure_is_sanitized_and_does_not_fallback(core, monkeypatch, capsys):
    monkeypatch.setattr(main, 'MemoryManager', lambda: MemoryManager(core.memory_manager.store))
    monkeypatch.setattr(core.memory_manager, 'get_episodes', Mock(side_effect=MemoryStorageError('unavailable')))
    with pytest.raises(MemoryStorageError):
        core.get_continuity()
    monkeypatch.setattr(core.memory_manager.store, 'get_episodes', Mock(side_effect=MemoryStorageError('unavailable')))
    assert main.handle_command('Where did I leave off?') == []
    assert 'storage is unavailable' in capsys.readouterr().out


def test_isolation_and_invalid_view(core, isolated_resources):
    assert isolated_resources.permits(core.memory_manager.store.db_path)
    assert core.get_continuity() is None
    with pytest.raises(ContextStateError):
        core.handle_event(ContextEvent(ContextEventType.CONTINUE, view='execute'))
