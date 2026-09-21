# Context Episodes (V3 foundation)

Context events add persistent situational state to the existing MemoryManager,
MemoryStore, and ContextEngine. They do not produce desktop actions. Existing AI
fallback, ActionPolicy, TaskExecution, and B10 dependency/provider work are unchanged.

## Text demonstration

Run `main.py` once for each command, using the same checkout/database:

```text
I'm here.
Remember that I need to submit my assignment before I leave.
I'm leaving.
```

The final response includes `Before you leave, still pending: submit my assignment`
and closes the episode. `I've arrived`, `I'm at college`, `I'm leaving now`, and
`I'm heading out` also produce typed events. Curly apostrophes are supported.
`what is my current context` inspects active state. Task creation returns its ID;
`complete context task <id>` marks it completed. Completed tasks are not reminded
again. Completion is explicit; saying a task was done in arbitrary prose is not
interpreted yet.

With no active episode, departure reports that there is nothing to close. Task
creation asks the user to establish a context; it does not save a permanent
preference or call Gemini. Unrecognized input retains the existing routing.
Recognition uses a bounded, anchored grammar, not a general NLP system.

## Shared core API

```python
from context import ContextEngine
from context.events import ContextEvent, ContextEventType
from memory import MemoryManager

with MemoryManager() as manager:
    engine = ContextEngine(manager)
    arrival = engine.handle_event(ContextEvent(ContextEventType.ARRIVE, name="college"))
    task = engine.handle_event(ContextEvent(
        ContextEventType.ADD_TASK, description="submit my assignment"
    ))
    result = engine.handle_event(ContextEvent(ContextEventType.LEAVE))
    print(result.message)
    state = engine.continuity_snapshot("college")
```

This example writes to the configured store; use `MemoryManager(MemoryStore(path))`
with a caller-owned temporary store for experiments. The default database remains
`memory.db` at the repository root, as defined by MemoryStore (not the current
working directory). No import opens storage. A caller that injects a store owns
and closes it.

Text uses `parse_context_event` then `ContextEngine.handle_event`; future interfaces
can create the same events directly. `ContextResult` returns a message, episode,
optional task, and reminder records; `to_dict()` is JSON-serializable. User-facing
responses can contain requested task content; no context content is written to
history or diagnostic logs.

## State and persistence

Initialization adds three tables and indexes in the existing SQLite transaction.
There was no migration/version framework in V2. This first extension uses
idempotent `CREATE TABLE/INDEX IF NOT EXISTS`; it does not rebuild, copy, delete,
or reclassify rows in `memories`. Failed initialization rolls back its additions.
Future schema changes need explicit migrations, not edits that assume CREATE IF
NOT EXISTS changes existing columns. The real user database is upgraded only when
normal application use opens it; development tests never migrate it.

- Permanent memories/preferences remain in `memories`, with existing APIs unchanged.
- `context_episodes` stores ID, explicit name, UTC timestamps, active/closed status,
  relevant permanent-memory IDs, and explicit JSON metadata.
- `context_tasks` stores episode-bound tasks/intentions, pending/completed status,
  timestamps, and a `context_exit` or `none` reminder trigger.
- `context_notes` stores contextual or temporary information tied to an episode.

A unique partial index permits one active episode. Foreign keys prevent orphaned
tasks/notes. All lifecycle operations use existing nested transactions. Arrival
without a name uses `current_place`; repeated arrivals keep the episode and tasks.
An explicit name refines the active episode, even if it differs from the old name.
To create a separate episode, leave first, then arrive. Nothing infers GPS or
physical location.

Use `MemoryManager.update_episode(name=..., memory_ids=[...], metadata={...})` for
explicit updates; supplied metadata replaces the previous object. Memory references
must exist when attached. `add_context_note(content, category="contextual")` or
`category="temporary"` separates scoped information from permanent preferences.
`add_context_task(description, kind="intention", trigger="none")` records an
intention without an exit reminder. Repeated identical pending tasks deduplicate.
`complete_context_task(id)` is idempotent and can complete a historical task without
reopening its episode. New items may only be attached to the active episode.

The inspectable rule in `context/rules.py` matches departure, episode ID, pending
status, and exit trigger. The engine evaluates reminders before closing, commits,
then returns the response. It never executes or resumes tasks. Failed persistence
returns no success response and leaves the event rolled back. Repeated departure
and later unrelated episodes do not resurface old reminders.

`continuity_snapshot(name=None)` retrieves the latest episode (optionally matching
an exact name), all task states, unfinished tasks/intentions, scoped notes, metadata,
and resolved memory references. Deleted permanent-memory references are omitted
from resolved results. It does not summarize with an LLM or send context to Gemini.

Temporary notes remain archived for explicit continuity lookup after closing;
there is no timed expiry, deletion scheduler, or automatic task-triggered note
expiry. There is no complete natural-language parser for scoped notes or metadata.
`clear_all_memories()` retains its V2 scope: permanent memory rows only, not episode
history. Full conversational continuity, voice, GUI, phone, location integrations,
and a general rule engine are not part of this foundation.

## Validation

Use the B10 virtual environment and isolated test setup:

```text
python -m pytest -q test_context_episodes.py test_memory_manager.py test_context_engine.py test_remember_memory.py
python -m pytest -q
```

The new tests cover the lifecycle and demonstration, phrase variations, scoped
storage and references, completion, reminder rules, old database initialization,
transaction rollback, uniqueness/foreign keys, corruption handling, and no AI,
desktop, or history side effects. Existing suite isolation also copies and repeats
these tests against temporary databases, with real user resources protected.
