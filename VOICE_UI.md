# V3 Phase 3: Voice + Instant Context Interface

Phase 3 adds a small, transient command surface to the existing personal agent:
**summon → act → disappear**. Open the surface, type a request, read the result,
then dismiss it. There is no chat-history browser, dashboard, account system,
wake word, or continuously running microphone.

## Architecture

```text
Desktop UI → Interaction Controller → main.handle_command → existing Agent Core
                                                            ├─ context / memory
                                                            ├─ deterministic commands
                                                            └─ AI fallback
                                                               → existing planning
                                                               → schema validation
                                                               → ActionPolicy
                                                               → TaskExecution
                                                               → executor
                                                               → Windows/macOS actions
```

The existing routing distinctions remain: deterministic commands use the existing
parser/executor; explicit context and memory requests use their existing core
handlers; AI plans pass through ActionPolicy and TaskExecution. The UI does not
force every command through AI and does not create a second execution path.

| File | Responsibility |
| --- | --- |
| `desktop_ui.py` | Compact Tkinter window, input, Microphone/Send buttons, response, status, optional Read reply checkbox, dismissal; queues worker updates onto the Tk thread. |
| `interaction.py` | Accepts typed or recognized text, calls the existing `main.handle_command`, presents its result, and optionally passes the final successful response to a voice output provider. |
| `voice.py` | Replaceable input/output protocols, controlled error types, and unavailable-provider stubs. |

The compatibility bridge captures the core's existing printed response, excluding
`[AI]` and `[LOG]` diagnostics. It does not parse commands, summarize plans, access
SQLite, call Gemini, instantiate a ContextEngine, or execute actions itself.
Because stdout capture is process-global, use the desktop entry point as a
standalone process rather than embedding it alongside unrelated stdout writers.
One interaction runs at a time; Tk widgets remain on the UI thread.

## Running and invocation

Use Python 3.12 with working Tcl/Tk support and the existing project environment.
No dependency was added. From the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -B desktop_ui.py
```

On macOS, the corresponding entry point is `.venv/bin/python -B desktop_ui.py`;
native macOS UI behavior has not yet been validated. The original one-command
CLI remains available through `main.py`.

Launch the entry point to summon the surface. `InvocationSurface` defines a small
summon/dismiss boundary; no global hotkey registration, tray service, or resident
launcher is implemented. Enter or Send submits text. Escape, Dismiss, and window
close dismiss the surface. Relaunch to summon a fresh window.

Dismissal cancels pending recognition and blocks late transcripts. An already
dispatched core operation is allowed to finish while the window is hidden; it is
not killed midway through an action or database write. The process then closes.

## States and presentation

| State | Meaning |
| --- | --- |
| Idle | Ready for input; displayed as Ready. |
| Listening | An explicitly requested recognition call is in progress; the microphone control becomes Cancel. |
| Processing | Ordinary text has reached the existing core. |
| Responding | The final successful response is available; optional speech may run. |
| Error | Input, core, or optional output failed in a controlled way. |

There is one replaceable response area, not a conversation history. Failed,
empty, unavailable, or cancelled microphone input preserves the previous result.
Output-provider failure also preserves the successful text response and does not
reclassify the completed core action as failed. Brief states may transition
within one UI polling interval.

## Current voice status

**Actual microphone speech recognition and actual text-to-speech are deferred.**
The shipped UI does not record or play audio.

- `VoiceInputProvider.recognize(cancel)` is an interface for one explicit capture
  returning ordinary text. The default `UnavailableVoiceInput` reports a controlled
  failure; the UI invites the user to type instead. Successful recognition is
  exercised only with mock providers in tests.
- `VoiceOutputProvider.speak(response)` receives only the final successful
  assistant response, never the input, action plan, or diagnostics. Output is
  opt-in and absent by default; `UnavailableVoiceOutput` is an explicit stub.
  Read reply without a configured provider displays a notice and retains text.
- Future provider implementations must bound capture/output duration, honor
  recognition cancellation, release microphone resources, and avoid audio storage.
  These are provider contracts, not implemented hardware integrations or enforced
  termination of arbitrary third-party code.

There is no installed speech stack, cloud voice service, wake-word listener, or
background microphone monitoring. No provider is constructed that opens hardware
at startup. Providers are injected in code; no settings system was added.

## Context continuity

The UI forwards these existing commands unchanged:

```text
I'm here.
Remember that I need to submit my assignment before I leave.
I'm leaving.
Continue what I was doing.
```

The existing core establishes the episode, records the task, reports pending work
on departure, and retrieves continuity. A fresh controller can recover that state
through the existing memory system; the UI contains no continuity rules or second
database. See [CONTEXT_EPISODES.md](CONTEXT_EPISODES.md) and
[CONTEXT_CONTINUITY.md](CONTEXT_CONTINUITY.md).

## Safety and privacy

UI and controller code contain no shell execution, direct desktop dispatch, SQL,
planner, or provider calls. Existing schema validation, AI action policy, path/URL
restrictions, platform mappings, and failure handling are unchanged.

The interaction layer does not persist audio, transcripts, or conversation history.
No raw audio enters memory, the database, or logs; no sensitive audio is logged.
Recognized text would immediately become ordinary command text. Explicit remember
requests can therefore persist their text through the existing memory semantics,
and AI fallback can send text/context to the existing Gemini provider. This phase
does not change those boundaries or the existing `.env` behavior. Optional spoken
responses could be audible to nearby people once a real provider is implemented.

## Validation

Windows validation on 2026-09-24 used Python 3.12.14:

- Full suite: **636 passed, 0 failed, 0 errors, 0 skipped** (61.44 seconds in the
  final documentation/cleanup validation).
- Focused Phase 3 suite: **55 passed, 0 failed, 0 errors, 0 skipped** (3.18 seconds
  in that validation).
- All five Phase 3 Python files compiled; pip consistency checks passed and all
  36 pinned dependency entries matched. No dependency manifests changed.
- Native Tk validation outside the sandbox exercised summon, mapped controls,
  text submission, deterministic site listing, the complete context sequence,
  all five states, microphone-unavailable handling, and clean dismissal. Speech
  providers remained stubs; no hardware speech or live Gemini call was tested.
- Focused tests cover shared typed/voice dispatch, policy-before-task ordering,
  controlled failures, cancellation, response preservation, and headless Tk
  presentation. Full regressions cover B10, context episodes/continuity, memory,
  and Phase 2.5 platform behavior.

Safe test commands (using an existing disposable temp root if required by Windows
permissions):

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider test_interaction.py test_desktop_ui.py
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m pip check
```

Tk could import inside the restricted sandbox but could not load `init.tcl` there;
the same runtime opened the native window outside it. This does not establish
native macOS parity. Actual macOS UI and platform-specific behavior still require
native testing. The known AI credential limitation was not investigated or changed.

### Database validation incident

The first native harness changed its working directory but used the original core,
whose default database is anchored to the repository's `memory.db`. It therefore
added one smoke-test episode/task to that database. Those exact timestamp-verified
records were removed; the corrected harness ran from a disposable source copy.

Cleanup inspection found zero context episodes/tasks/notes, an intact existing
memory row matching the recovery copy in every column, no foreign-key violations,
and a passing SQLite integrity check. The schema is identical to the recovery
copy and matches the current core definition apart from SQL whitespace. The copy
was made after the smoke write; it was not an exact pre-test recovery snapshot.
No old database was restored. Available logical evidence supports the cleanup,
but cannot reconstruct a byte-for-byte pre-test file.

After comparison, the temporary post-smoke recovery copy was removed. It is not
project data or a required project dependency.

The earlier native test left SQLite metadata/file-level changes even though the
test's logical state was removed. Subsequent cleanup leaves `memory.db` alone.
Future native tests must use an isolated source copy or the existing test storage
fixtures; changing the working directory alone is insufficient.
