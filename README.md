# AI Desktop Agent

A local Python desktop assistant evolving toward a context-aware personal agent.
V2 combines deterministic commands, SQLite preference memory, context-aware AI
planning, and constrained desktop actions. The laptop is the execution interface;
context episodes, continuity rules, voice, floating UI, and phone clients are future
work and are not implemented in this checkpoint. No Docker or cloud service is needed.

## Architecture

```text
Text CLI (main.py)
  -> deterministic parser -> executor -> existing actions
  -> explicit memory commands -> MemoryManager -> SQLite
  -> natural-language fallback
       -> AIOrchestrator -> ContextEngine + MemoryManager
       -> AIBrain -> ProviderManager -> GeminiProvider
       -> structured JSON plan -> schema validation -> ActionPolicy
       -> TaskExecution -> executor -> existing actions
```

Reasoning, memory, schema validation, and task state are shared Python code.
Platform operations live in `actions/`; policy also checks platform capabilities
before allowing a plan. A future interface can reuse this pipeline without adding
another intelligence system.

```text
main.py, parser.py, executor.py  CLI, deterministic routing, dispatch
config.py                     trusted app/site/browser/folder configuration
ai/                           provider, planning, schema, policy, task execution
context/                      runtime and relevant-memory context
memory/                       SQLite store and MemoryManager
logger.py                     redacted action history
conftest.py, test_*.py         isolated offline regression suite
requirements*.txt             runtime/development dependency entry points
constraints.txt               tested direct and transitive dependency versions
```

## Python and dependencies

Use **CPython 3.12** (validated with 3.12.14 on Windows). `.python-version` records
that minor version; it does not install Python. Other Python versions are unverified.
Install a Python distribution that includes pip, venv, and SQLite.

Runtime dependencies are `google-genai`, `python-dotenv`, and `httpx`; tests add
`pytest`. Both requirements entry points use `constraints.txt` to pin the tested
transitive dependency set. There is no browser-driver or desktop-control framework.
Dependency upgrades must be followed by the full tests; do not regenerate pins
from a global environment. These are version pins, not a hash-verified wheel lock.

## Fresh setup

Clone the repository, then run every command from its root directory. Install
Python first if `py` (Windows) or `python3.12` (macOS) is unavailable.

Windows PowerShell (activation is optional):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe main.py
```

macOS:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python main.py
```

For runtime only, install `requirements.txt` instead. First installation requires
network access to download dependencies. macOS setup and native actions require
validation on an actual Mac; mocked platform tests do not establish native parity.

## Gemini configuration

Obtain a key from [Google AI Studio](https://aistudio.google.com/apikey).
Copy `.env.example` to `.env` only if you do not already have one, then set
`GEMINI_API_KEY` locally. Never commit keys, user memory, or history.
Alternatively set `GEMINI_API_KEY` in your shell environment.
`GEMINI_MODEL` optionally overrides the provider's default `gemini-3.1-flash-lite`.
Model access, availability, billing, and quota depend on your Google account;
this test suite does not verify live model access.

Configuration precedence is explicit provider arguments, then existing environment
variables, then `.env` values. dotenv searches from the current working directory
upward for the nearest `.env` and never overwrites existing shell variables.
Launch from the repository root to select its configuration and data paths.
A missing or blank key produces a controlled `AI service unavailable.` response
when AI is requested. Deterministic commands and explicit memory commands need no
key and do not construct a Gemini client.

The provider uses the official SDK's public `models.generate_content` API, public
error classes, a 20,000 ms HTTP timeout, and one attempt (no automatic retries).
The timeout is a transport timeout, not a hard total wall-clock deadline.
Only response text enters the planner. Empty/blocked output fails in a controlled
way. No tools or executable functions are provided to Gemini.

## Running and commands

`main.py` prompts for **one command per invocation**, then exits. Examples:

```text
help
open yt
search python decorators
create file notes.txt
remember that I prefer brave
what are my preferences
what do you remember about brave
please search youtube for Python tutorials
```

Explicit create/delete/rename/copy/move commands are deterministic local operations.
Quote multiword operands and names containing `and`. These directly requested file
operations can modify files; the AI allowlist is narrower than the CLI command set.
`config.py` enables named applications and browsers; platform adapters contain
their fixed launch mappings. See [CROSS_PLATFORM.md](CROSS_PLATFORM.md) for install
locations and limitations.

## Safety and reliability

AI fallback produces data, never executable code. `AIBrain` validates bounded JSON;
the orchestrator validates again, then `ActionPolicy` approves the entire plan
before `TaskExecution` dispatches any step. Allowed AI actions are open, search,
list, help, and draft_email. Arbitrary shell/scripts, executable launches, file
mutations, unconfigured open URLs, unsupported parameters, and unsupported platform
capabilities are rejected. Local open targets must be supported documents/folders
inside the home directory, with link, bundle, type, and executable checks.

The first failed task step stops later steps. Already completed steps are not
rolled back. Browser launch acceptance does not verify page loading or completion.
Memory-dependent commands fail safely if storage is unavailable; unrelated
commands such as help, ordinary search, and configured site opening remain usable.

## Windows and macOS capabilities

| Capability | Windows | macOS |
| --- | --- | --- |
| Configured sites / ordinary Google search | Default browser | Default browser |
| Named browser, YouTube search, Gmail compose | Brave in supported install locations | Brave or Safari |
| Configured desktop app opening | Fixed supported installation paths | `/usr/bin/open -a` |
| Safe local document/folder opening | Explorer / Notepad / Brave | Finder / TextEdit / Preview |
| Explicit filesystem operations | Python filesystem operations | Python filesystem operations |

Windows Brave discovery checks LOCALAPPDATA, PROGRAMFILES, and PROGRAMFILES(X86),
not the current directory or arbitrary PATH executables. Safari is macOS-only.
Linux desktop automation is not a supported target.
WhatsApp on Windows supports only the fixed legacy desktop installation; Store-only
installs are unsupported. Windows PDF/image opening requires Brave. See
[CROSS_PLATFORM.md](CROSS_PLATFORM.md) for the action audit and validation scope.

## Memory, context, and privacy

`MemoryManager` persists memories/preferences in SQLite `memory.db` relative to the
working directory. `ContextEngine` combines runtime context and relevant stored
memories, including browser preference resolution. Explicit `remember` commands
currently store user preferences; this is not an episode or general conversation
archive. See [MEMORY_MANAGER.md](MEMORY_MANAGER.md) for the memory API.

AI fallback sends the user's command and selected context/memories to Gemini.
Local storage does not imply that AI processing is offline. Diagnostic output
reports sizes, action categories, and sanitized errors rather than raw prompts,
responses, email bodies, search queries, or private paths. `logs/history.log`
contains redacted action/status records. Explicit memory retrieval displays the
requested memory content. Local memory is not encrypted by this application.

Gmail support is **compose preparation only**: it opens a compose URL with fields
explicitly provided by the user. It does not send, schedule, attach, reply, forward,
or support CC/BCC. The user reviews and sends in Gmail. Compose fields travel in
the URL and can appear in browser history; application logs redact them.

## Testing and verification

From the root, using the virtual environment's Python:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -c "import pathlib, py_compile; files = list(pathlib.Path('.').glob('*.py')) + [p for d in ('actions', 'ai', 'context', 'memory') for p in pathlib.Path(d).rglob('*.py')]; [py_compile.compile(str(p), doraise=True) for p in files]; print(f'Compiled {len(files)} files')"
```

On macOS substitute `.venv/bin/python`. Focused provider checks:
`python -m pytest -q test_ai_provider.py test_provider_manager.py test_reliability.py`.
Use the virtual environment's interpreter, not an unrelated global Python.

`conftest.py` isolates SQLite, history, environment variables, working directories,
and mutable configuration before collection/tests. SQLite access outside permitted
temporary resources is blocked; real dotenv files are excluded. Provider and OS
operations are mocked: no API key, live Gemini request, browser session, or real
user database is needed. The isolation regression repeats the suite in a temporary
source copy with sentinel memory/history/.env and checks environment restoration.

If a restricted Windows session cannot access an existing pytest temp directory,
use a dedicated disposable temp root before testing:

```powershell
New-Item -ItemType Directory -Force .venv/test-tmp | Out-Null
$env:TEMP = (Resolve-Path .venv/test-tmp).Path
$env:TMP = $env:TEMP
```

`.gitignore` excludes `.env` variants (except the blank example), `memory.db` and
its SQLite sidecars, `logs/history.log`, Python caches, and common virtual
environments. Keep these protections when adding tooling. Never run data-clearing
examples against a real user database as a setup or test step.
