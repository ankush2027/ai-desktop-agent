# Desktop actions: Windows and macOS

Python 3.12 is required. Windows and macOS are the supported desktop targets;
other operating systems return a controlled unsupported-platform result. Pure
help/list, memory/context, and Python filesystem code do not require a desktop.
There is no voice or GUI implementation in this phase.

## Boundary and audit

The existing AI route remains schema validation -> ActionPolicy -> TaskExecution
-> executor action handlers -> `actions/platforms.py`. The deterministic parser
continues to handle explicit local commands; it is not routed through the narrower
AI allowlist. There is no new parser, planner, execution engine, or memory system.

`get_platform()` is the single desktop OS detector. The small Windows and macOS
adapters accept named capabilities, not executable paths, shell strings, scripts,
or AI-generated flags. Shared URL construction, Gmail provenance checks, local
path validation, and filesystem operations remain in their existing modules.
ActionPolicy uses the same capability maps as execution, validates the whole AI
plan before dispatch, and still rejects all AI file mutations.

| Audited action | Windows | macOS |
| --- | --- | --- |
| Configured sites and Google search | Default browser | Default browser |
| Named browser | Brave | Brave or Safari |
| YouTube search | Encoded search URL in preferred supported browser | Same workflow |
| Gmail draft | Encoded compose URL in preferred supported browser | Same workflow |
| Calculator | SystemRoot/System32/calc.exe | Calculator via `/usr/bin/open -a` |
| VS Code (`vscode`) | Fixed user/system installation paths | Visual Studio Code via `/usr/bin/open -a` |
| WhatsApp | Legacy LOCALAPPDATA/WhatsApp/WhatsApp.exe only | WhatsApp via `/usr/bin/open -a` |
| Telegram | Fixed APPDATA or PROGRAMFILES installation paths | Telegram via `/usr/bin/open -a` |
| Home-contained folders | Fixed Explorer executable | Finder via `/usr/bin/open` |
| Allowed text documents | Fixed Notepad executable | TextEdit |
| Allowed PDF/images | Fixed Brave executable with a validated file URI | Preview |
| Create / rename / delete files and folders | Shared Python operations | Shared Python operations |
| Copy / move files | Shared shutil operations | Shared shutil operations |
| Copy / move folders; recursive delete | Unsupported | Unsupported |

Before this phase, Windows apps and local opening were unavailable, OS checks
were spread across action/policy modules, and the VS Code macOS app name was
incorrect. The boundary now supplies both adapters and Telegram mappings. Shared
filesystem handlers now propagate missing-source, existing-create, and nonempty
folder deletion errors to the executor rather than reporting successful commands.
Copy/move and rename also enforce their declared source type.

## Installation and platform differences

Windows executables are discovered only at fixed relative paths under absolute
trusted process-environment installation roots. No PATH/current-directory search,
shell, PowerShell, registry command, or executable supplied by a plan is used.
VS Code checks LOCALAPPDATA/Programs/Microsoft VS Code, PROGRAMFILES/Microsoft VS
Code, then PROGRAMFILES(X86)/Microsoft VS Code. Telegram checks APPDATA/Telegram
Desktop then PROGRAMFILES/Telegram Desktop. Brave retains its original discovery
order: LOCALAPPDATA, PROGRAMFILES, PROGRAMFILES(X86), each under
BraveSoftware/Brave-Browser/Application. GUI processes use nonblocking Popen.

Store-only WhatsApp/Telegram, portable/custom installations, Safari on Windows,
and other unlisted applications are not supported. Missing fixed installations
return an error; there is no fallback to a different application. Installation
roots and source configuration are trusted local administration, not AI inputs.
APPS keys enable known adapter entries; its values are display labels. Adding a
new application requires a reviewed fixed mapping in the appropriate adapter.

macOS uses the absolute `/usr/bin/open` executable with fixed app names and argv
lists. LaunchServices resolves installed applications by name; no AppleScript is
used. Missing apps/nonzero launch exits propagate through the existing failure
handling. Process acceptance never proves application readiness or page loading.

## Safety and shared workflows

AI open URLs are still restricted to configured site home destinations. Search
and Gmail URLs are constructed by application code. The adapter additionally
rejects non-HTTP(S) navigation, credentials, controls, and malformed ports. Local
file URIs are generated only by the validated Windows document-reader path.

Local opening stays inside the resolved home directory, rejects links, junctions,
application bundles, unsupported types, Windows alternate data streams, and macOS
executable documents. It rechecks targets at dispatch. Readers are fixed rather
than user file associations. Text suffixes: txt, md, csv, json, log. Preview
suffixes: pdf, png, jpg, jpeg, gif, webp. A concurrent external replacement between
the final path check and the OS opening remains a filesystem race; no atomic
cross-process file handoff is claimed.

Explicit user filesystem commands retain their existing path scope (they are
not confined to home), native permission checks, and os/shutil destination
semantics. Quote multiword operands. Create is exclusive; folder deletion is
empty-only. Rename overwrite behavior, case sensitivity, reserved filenames,
and filesystem permissions can differ between Windows and macOS. No overwrite
confirmation, rollback, or recursive deletion has been added. AI cannot request
these mutations through its validated schema/policy.

Gmail remains compose preparation only, using the existing signed-in browser
session. No authentication/provider redesign or actual email sending occurs.
Recipient/subject/body provenance, URL encoding, and privacy redaction are
unchanged. YouTube remains search-page navigation, not verified playback.

## Verification

Run with the project virtual environment (use `.venv/bin/python` on macOS):

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q -p no:cacheprovider test_desktop_platform.py test_browser_platform.py test_actions_opener.py test_action_policy.py test_hardening.py test_email_workflow.py test_youtube_workflow.py
python -B -m pytest -q -p no:cacheprovider
python -B -m pip check
```

Use the README's disposable temporary-root setup if Windows temp permissions
prevent pytest setup. Tests mock all desktop process/browser launches and use
isolated temporary files/database/history. Existing safety tests remain, with
mock targets moved to the adapter boundary and obsolete Windows-unavailable
expectations replaced by supported Windows coverage and unsupported-OS coverage.

Windows host validation exercises Python execution, parser/policy/task integration,
temporary native filesystem operations, and regressions. Windows application
launches and discovery candidates are mocked; no interactive desktop smoke test
is claimed. macOS validation is unit/mock and static only, executed on Windows.
Actual macOS LaunchServices, installed app names, Brave/Safari navigation, Finder,
TextEdit/Preview, native filesystem behavior and permissions still require testing
on a Mac. There is no native macOS runtime result for this phase.

Dependencies and all three dependency files are unchanged. Context Episodes,
Context Continuity, and B10 provider/privacy behavior are covered by the full
regression suite; their implementation modules are unchanged.

Recorded validation on Windows / CPython 3.12.14 (2026-09-23):

| Check | Result |
| --- | --- |
| Focused desktop/policy/browser/Gmail/YouTube/hardening tests | 313 passed |
| Full regression suite | 581 passed |
| New desktop test cases | 113 passed |
| B10 provider/reliability subset within full suite | 64 passed |
| Context Episodes subset within full suite | 37 passed |
| Context Continuity subset within full suite | 35 passed |
| py_compile, changed/new Python files | 26 passed; bytecode written to disposable temp storage |
| Dependency checks | pip check passed; all 36 pinned entries matched installed versions |
| Protected state hashes | 163 unchanged; no protected files added/removed |
| Git diff inspection and whitespace check | Passed; changes unstaged, no commit/push |

Protected state includes existing dotenv/example, SQLite, logs, and repository
Python/pytest caches. Tests disabled bytecode/cache writes and used disposable
resources under the ignored virtual environment. The initial default-temp run
could not set up tests due to Windows permissions; the recorded passing runs use
the documented disposable temp-root setup. Compilation outputs were removed.

## Review manifest

Added files:

- `CROSS_PLATFORM.md`
- `actions/platforms.py`
- `test_desktop_platform.py`

Modified files:

- `README.md`
- `actions/apps.py`
- `actions/browser.py`
- `actions/copy_file.py`
- `actions/create.py`
- `actions/delete.py`
- `actions/delete_file.py`
- `actions/delete_folder.py`
- `actions/directories.py`
- `actions/files.py`
- `actions/local_paths.py`
- `actions/move_file.py`
- `actions/rename.py`
- `actions/rename_file.py`
- `actions/rename_folder.py`
- `actions/search.py`
- `ai/action_policy.py`
- `config.py`
- `main.py`
- `test_actions_opener.py`
- `test_browser_platform.py`
- `test_email_workflow.py`
- `test_hardening.py`
- `test_parser.py`
- `test_youtube_workflow.py`

The new desktop test module adds 113 cases covering selection, app mappings,
installation discovery, unsupported actions, fixed readers, junctions, alternate
data streams, policy ordering, argument/URL rejection, and temporary filesystem
success/failure behavior. Existing parser tests now create a temporary rename
source before asserting the exact OS arguments. No safety assertion was removed.
