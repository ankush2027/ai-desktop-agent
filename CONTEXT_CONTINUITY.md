# Context Continuity (V3 phase 2)

`ContextEngine.get_continuity(name=None)` derives a `ContinuityState` from the
existing SQLite episodes, tasks/intentions, notes and explicit memory references.
There are no schema changes, new dependencies, background jobs, or model calls.
The phase-one `continuity_snapshot()` API retains its latest-episode behavior.

## Input and response

The existing shared context event path now recognizes these bounded phrases:

- `I'm working on my AI project.` records a pending intention in the active episode.
- `Remember that I need to finish the browser reliability work.` records a task.
- `Continue what I was doing.`, `Where did I leave off?`, `What was I working on?`,
  `Where was I?`, `Continue my last task.`, and `What was I doing?` retrieve an overview.
- `What was unfinished?` and `What should I continue?` show recorded pending work.
- `What was already completed?` shows recorded completed work.

Case, terminal punctuation and curly apostrophes are handled. The explicit
`before I leave` task grammar still takes precedence and retains its exit trigger.
The new generic work/task phrases use trigger `none`; they do not create exit
reminders implicitly. Tasks/intention creation requires an active episode. Without
one, the user is asked to establish context, and nothing becomes permanent memory.
Ordinary preference commands and unrecognized commands retain existing routing.
Completion remains `complete context task <id>` or the existing manager API.

Continuity only explains stored facts. A closed episode stays closed, pending tasks
stay pending, and no action is dispatched. With no useful state, the response is:
`I don't have enough recent context to determine what you were working on.`
`Where was I?` is a continuity alias, not a request for inferred physical location.

## Core API and state

```python
from context import ContextEngine
from context.events import ContextEvent, ContextEventType
from memory import MemoryManager

with MemoryManager() as manager:
    engine = ContextEngine(manager)
    state = engine.get_continuity()  # ContinuityState or None
    response = engine.handle_event(ContextEvent(ContextEventType.CONTINUE))
    print(response.message)
```

Future interfaces can use these same APIs. `state.to_dict()` and
`response.to_dict()` are JSON-serializable. State contains the selected episode
(including its ID, name, lifecycle timestamps/status and metadata), pending
intentions, pending tasks, completed tasks/intentions, scoped notes, resolved linked
memories, and last recorded activity. Completed items never occur in pending lists.

The deterministic summary separates intentions, unfinished tasks, and completed
work. Overview responses also include the selected episode's notes and linked
memories. Pending/completed question responses omit those additional payloads.
The structured API still returns the selected episode's complete continuity state
for a caller to render; it does not send that state to Gemini.

## Explainable episode selection

Selection examines existing episodes (or an exact context name if supplied) and
returns only one episode's information. Empty arrivals and deleted-reference-only
episodes are skipped. Tasks, notes, valid linked memories, or explicit metadata
make an episode eligible. Candidates rank in this order:

1. Episodes with unfinished tasks or intentions.
2. Within that group, an active episode over a closed episode.
3. Episodes with completed work over notes/reference/metadata-only episodes.
4. Most recent recorded task/note activity, then episode start time, then ID for
   stable ties.

Thus older unfinished project work outranks a newer trivial note or empty arrival.
There is no semantic guess about what a note means. Selection reads candidate
state locally; neither responses nor diagnostics dump unrelated episode histories
or unlinked permanent memories.

Last activity is derived from task creation/completion and note creation timestamps.
If none exist, it uses the episode start/end timestamp. It is not a reconstructed
conversation log and does not claim to track metadata edits, repeated deduplicated
intentions, or external desktop progress. No automatic recency cutoff is applied:
an old pending task may remain the most relevant candidate. All pending intentions
are retained; a new intention does not silently complete an earlier one.

No expiry, free-form semantic matching, LLM summarization, automatic resume,
voice, GUI, phone, location tracking or external service is added. Reference-only
or metadata-only state may provide context without identifying unfinished work;
the response says only what task state actually records.

## Verification

Use the existing isolated B10 test environment:

```text
python -m pytest -q test_context_continuity.py test_context_episodes.py test_memory_manager.py test_context_engine.py test_remember_memory.py
python -m pytest -q
```

New tests cover active/closed continuity, task partitions, episode ranking,
recorded activity, scoped notes/references, empty state, routing variants, the
product flow, no dispatch/provider/history writes, storage failures, and unchanged
legacy snapshot behavior. Existing isolation tests run copied suites against
sentinel databases/history/.env, leaving real user resources untouched.
