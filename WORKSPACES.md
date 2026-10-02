# Mac named workspaces

Workspaces are saved definitions, not snapshots of running applications. Management
and restoration are Mac-only. The existing planner/provider, ActionPolicy, task
runner, executor, and Mac application mappings remain in use.

## Data and persistence

New records use this JSON definition in the existing `memory.db` `workspaces`
table (columns `name` and `definition`):

```json
{"name":"music","apps":["brave"],"urls":["https://music.youtube.com"]}
```

Names are case-normalized identifiers matching `[a-z][a-z0-9_-]{0,31}`. Definitions
contain 1–10 total items across apps, URLs and folders, without duplicates, and at most 4096 encoded
characters. Apps must be keys supported by both configuration and the existing Mac
adapter: currently `vscode`, `calculator`, `whatsapp`, `telegram`, `brave`, `safari`.
No paths, processes, launch arguments, or shell commands are accepted.

URLs must exactly match a trusted entry in `config.SITES` or `config.WORKSPACE_URLS`.
`WORKSPACE_URLS` initially adds `youtube_music: https://music.youtube.com` on the Mac
policy path. To configure another destination, edit the trusted configuration;
AI workspace commands cannot extend this allowlist. Existing URL restrictions
still apply: HTTP(S) home destinations only, no credentials, query, or fragment.

## Structured operations

Each operation is an item in the existing `{"actions":[...]}` plan:

```json
{"action":"list_workspaces","target":"workspaces","params":{}}
{"action":"create_workspace","target":"music","params":{"apps":["brave"],"urls":["https://music.youtube.com"]}}
{"action":"restore_workspace","target":"music","params":{}}
{"action":"update_workspace","target":"coding","params":{"operation":"add","app":"telegram"}}
{"action":"update_workspace","target":"coding","params":{"operation":"remove","app":"telegram"}}
{"action":"delete_workspace","target":"music","params":{}}
```

Only `create_workspace` accepts list-valued parameters: required `apps` and `urls`
arrays, plus optional `folders`, all flat lists of strings. All other parameter
contracts remain string-only. `update_workspace` changes one supported app or one
trusted folder alias per operation, never both at once. URL edits remain outside
scope. Unknown parameters are rejected.

## Trusted folders

The optional `folders` field stores aliases, never raw paths:

```json
{"name":"coding2","apps":["vscode"],"urls":[],"folders":["ai-desktop-agent"]}
```

`config.WORKSPACE_FOLDERS` is the trusted catalog:

- `ai-desktop-agent` → `~/Desktop/ai-desktop-agent`
- `projects` → `~/Desktop/Test` (the user's selected directory on this Mac)
- `documents` → the existing documents mapping, `~/Documents`

The planner sees catalog alias names only. Unknown aliases, raw paths and traversal
are rejected. Configured directories must already exist under the user's home,
with no symlink/junction components, application bundles, traversal or unsafe
characters. Files are not folders. Validation reuses `resolve_local_target` and
never creates directories. Adding a folder and restoring require a valid directory;
removing a known alias whose directory is missing remains possible.

```json
{"action":"create_workspace","target":"coding2","params":{"apps":["vscode"],"urls":[],"folders":["ai-desktop-agent"]}}
{"action":"update_workspace","target":"coding2","params":{"operation":"add","folder":"projects"}}
{"action":"update_workspace","target":"coding2","params":{"operation":"remove","folder":"projects"}}
```

Folders are resolved from the trusted catalog and become ordinary `open` actions.
The entire list passes ActionPolicy before execution, and the existing Mac local
open adapter rechecks the paths at launch. No new shell, subprocess or AppleScript
execution is added. Removing a folder from a workspace only updates its saved list;
it never deletes, copies, moves or writes the directory. Workspaces without
`folders` retain their original data and behavior; no database migration is needed
for this optional field.

Creating an existing name fails without overwriting it. Adding an existing app,
removing an absent app, removing the last item, and restoring/updating/deleting a
missing workspace fail safely. List returns sorted saved names (or an empty list)
and prints them. Delete removes only that saved workspace row.

The existing parser routes `List my workspaces` and `list workspaces` to its normal
list handler. A Mac-only delegation there calls the same policy-validated workspace
handler; routing is unchanged. Other natural-language operations use the planner.

## Restore safety

Stored definitions are treated as untrusted and revalidated, including their name
matching the database key. Apps become normal `open` actions. URLs become normal
browser `open` actions with a `url` parameter, using the first saved browser or the
configured default if none is saved. The complete generated list goes through
ActionPolicy before the existing task runner/executor dispatches any app. A launch
failure stops the remaining actions; already opened apps are not rolled back.

Management itself does not launch applications. Create/update validate the complete
result before committing; updates use the existing SQLite transaction mechanism.

## Existing coding workspace

The original definition remains readable and restores the same two applications:

```json
{"name":"coding","apps":["vscode","brave"]}
```

The coding-only table constraint is migrated transactionally on first workspace
access. Existing definition bytes and memory/context data are preserved. Unrelated
memory operations do not run this migration. Updating legacy coding adds an empty
`urls` list. The existing `save_workspace` action with target `coding` and empty
params still saves/resets the original VS Code + Brave preset; it is not a generic
save action for other names. Older versions with coding-only validation cannot
restore newly configured named records.

## Validation

```sh
.venv/bin/python -m pytest --tb=short -q test_workspace.py test_named_workspaces.py test_workspace_folders.py
.venv/bin/python -m pytest --tb=short -q
```

Tests mock provider calls and OS launches and use temporary databases, including
migration/rollback and trusted-folder safety tests. For the folder feature, run
`desktop_ui.py` on Mac and speak: create coding2 with VS Code and the
ai-desktop-agent folder; list workspaces; restore coding2; add the projects folder
to coding2; restore coding2; remove the projects folder; delete coding2; list again.
Verify the expected app and folders open. Browser/page/application readiness is not
verified by the existing adapter.
