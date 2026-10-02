# AI Desktop Automation Agent

A local, safety-first desktop automation system that translates natural-language and voice commands into structured, policy-validated desktop actions.

---

## 1. Project Overview

The **AI Desktop Automation Agent** is a focused desktop automation framework designed for controlled, deterministic, and AI-assisted task execution. Rather than operating as an unconstrained "AI assistant" or executing arbitrary shell commands, the agent converts natural-language user intent into strictly defined, validated action plans before dispatching them to platform-specific adapters.

The system handles both deterministic operations (direct application launches, search queries, explicit memory management) and multi-step natural-language requests (such as configuring or restoring multi-application workspaces). All actions pass through schema validation and an explicit `ActionPolicy` gate before reaching the executor.

---

## 2. Core Architecture

The system enforces a unidirectional flow from user input to platform execution:

```text
User
 ↓
Voice / Text Input
 ↓
Agent / Interaction Layer
 ↓
AI Planning (Gemini + Groq Fallback)
 ↓
Structured Action Plan (JSON)
 ↓
Schema Validation
 ↓
ActionPolicy
 ↓
Executor
 ↓
Platform / Application Adapters
```

### Layer Responsibilities

1. **Voice / Text Input**: Captures user input via the CLI (`main.py`) or the desktop interface (`desktop_ui.py`) using optional local speech recognition (`local_voice.py`).
2. **Agent / Interaction Layer**: Routes commands between deterministic rules, explicit context/memory operations, and the AI planning pipeline.
3. **AI Planning**: Utilizes Google Gemini (`AIBrain` / `GeminiProvider`) as the primary planner to construct a declarative JSON action plan, backed by Groq (`GroqProvider`) on macOS for transient provider outages.
4. **Structured Action Plan**: A bounded JSON payload adhering strictly to allowed action types, parameters, and action limits (maximum 10 actions per plan).
5. **Schema Validation**: Validates payload structure, parameter types, string lengths, and action counts (`ai/plan_schema.py`).
6. **ActionPolicy**: Enforces strict security boundaries, verifying permitted action types, parameter values, trusted URLs, trusted folder aliases, and platform capability support (`ai/action_policy.py`).
7. **Executor**: Dispatches verified actions step-by-step; execution halts immediately on the first failure without executing subsequent steps (`executor.py`).
8. **Platform / Application Adapters**: Safe OS-level implementations for macOS and Windows (`actions/`), handling application opening/closing, URL launches, and local document access.

---

## 3. Key Features

- **Natural-Language Desktop Automation**: Converts spoken or typed phrases into concrete desktop operations.
- **Structured Action Planning**: Declarative JSON plan generation with schema validation and strict response limits.
- **ActionPolicy Safety Verification**: Zero direct shell access; parameters and actions are rigorously verified against allowlists.
- **Resilient AI Planning**: Gemini 2.5/Flash-lite primary planner with automatic fallback to Groq (`openai/gpt-oss-120b`) on macOS for eligible transient network/server failures.
- **Local Speech Recognition**: Optional offline voice input powered by `faster-whisper` (`base.en`) with energy/VAD voice activity detection and audio pre-roll.
- **Multi-Step Command Execution**: Executes multi-action plans sequentially with fast-fail safety semantics.
- **Application Lifecycle Management**: Controlled opening and closing of configured desktop applications (`vscode`, `calculator`, `whatsapp`, `telegram`, `brave`, `safari`).
- **Web & Search Actions**: Automated web search and direct home-URL opening across configured browsers.
- **Context & Memory Continuity**: SQLite-backed episodic and preference memory (`MemoryManager`) for contextual continuity across interactions.
- **Named Workspaces**: Complete workspace lifecycle management (`create`, `list`, `update`, `restore`, `delete`).
- **Trusted Workspace URLs**: Restores browser targets strictly against configured site allowlists (e.g., YouTube Music).
- **Trusted Workspace Folder Aliases**: Restores project folders using pre-configured trusted folder aliases rather than arbitrary filesystem paths.
- **Automated Regression Suite**: Comprehensive test suite covering units, schemas, safety policies, mocked platforms, and isolation boundaries.

---

## 4. Safety Model

The safety architecture is the core design pillar of this repository:

- **No Arbitrary Shell Execution**: The AI planner has zero access to shell commands, bash/cmd interpreters, terminal commands, or arbitrary script execution.
- **Structured Action Output**: The LLM outputs purely structured JSON data matching predefined schemas (`open`, `close_app`, `search`, `list`, `help`, `draft_email`, `create_workspace`, `restore_workspace`, `update_workspace`, `delete_workspace`, `list_workspaces`).
- **Strict Schema Validation**: Bounded JSON parsing enforces maximum action counts (≤ 10), payload size limits (≤ 4096 characters), and strict parameter types before policy evaluation.
- **ActionPolicy Validation**: The `ActionPolicy` gate evaluates each proposed action against strict allowlists:
  - Applications must exist in `config.APPS` and be supported by the current OS adapter.
  - URLs must match verified HTTP/HTTPS origins without embedded credentials, user tokens, queries, or fragments.
  - File operations cannot target arbitrary system paths.
- **Trusted Folder Aliases Only**: Workspace folder operations strictly reject arbitrary filesystem paths. Only pre-configured aliases (e.g., `ai-desktop-agent`, `projects`, `documents`) are accepted, and targets must reside within the user's home directory.
- **Unsafe Operations Blocked**: File mutations and destructive file/directory deletions are blocked from AI planning.
- **Fail-Fast Execution**: The executor terminates on any step error; no subsequent actions are attempted.

---

## 5. AI Provider Architecture

The AI layer is structured for high availability while keeping execution strictly sandboxed:

- **Primary Provider**: Google Gemini (`GeminiProvider`) via the official `google-genai` SDK using `gemini-2.5-flash-lite` (or a configured model override).
- **Fallback Provider (macOS)**: Groq (`GroqProvider`) using `openai/gpt-oss-120b`.
- **Fallback Conditions**: Fallback triggers exclusively on transient Gemini failures:
  - HTTP status codes: `408`, `500`, `502`, `503`, `504`
  - Network timeouts, DNS resolution errors, and connection drops
- **Ineligible for Fallback**: Configuration errors, missing API keys, HTTP `401`/`403` authentication failures, and HTTP `429` quota limits do **not** trigger Groq.
- **Full Safety Preservation**: Fallback responses pass through the exact same JSON parser, schema validation, `ActionPolicy`, and executor safety checks as Gemini. Fallback does not bypass safety constraints.

---

## 6. Voice Architecture

The local voice subsystem operates entirely on-device without streaming audio to external cloud providers:

- **Audio Capture**: Utilizes `sounddevice` (PortAudio) capturing 16 kHz mono float32 audio.
- **Voice Activity Detection**: Incorporates an adaptive energy-based onset detector with trailing silence detection (0.8s) and pre-roll preservation (0.2s).
- **Transcription**: Powered by `faster-whisper` running the pinned INT8-quantized `Systran/faster-whisper-base.en` model locally on CPU.
- **Process Isolation**: Audio capture closes the microphone stream before transcription begins, preventing resource locking.
- **Honest Limitations**:
  - Voice recognition can degrade in acoustically noisy environments or with low-gain microphones.
  - Reliable transcription requires speaking clearly in a relatively quiet room.
  - Future iterations can incorporate advanced neural noise suppression and streaming ASR.

---

## 7. Workspace System

The macOS-specific workspace manager allows defining, persisting, updating, and restoring multi-window workflows:

- **Components**: Workspaces can bundle configured desktop apps, trusted URLs, and trusted folder aliases (up to 10 total items per workspace).
- **Persistence**: Saved definitions are persisted in SQLite (`memory.db`) with transactional integrity.
- **Operations**:
  - `create_workspace`: Defines a new workspace with specified applications, URLs, and optional folder aliases.
  - `list_workspaces`: Lists all registered workspaces.
  - `update_workspace`: Atomically adds or removes an app or trusted folder alias.
  - `restore_workspace`: Revalidates the workspace definition and launches all apps, URLs, and folders in sequence.
  - `delete_workspace`: Removes a workspace definition.
- **Restore Validation**: Stored records are treated as untrusted data and re-validated through `ActionPolicy` before any application or folder is launched.

---

## 8. Example Commands

### Basic Desktop & Browser Actions
```text
Open Calculator
Open YouTube
Open YouTube and search Python
Search for Python dataclasses
Close Calculator
```

### Workspace Management
```text
Create a workspace called coding
List my workspaces
Restore coding
Add Telegram to coding
Remove Telegram from coding
Delete workspace coding
```

### Context & Memory
```text
Remember that I prefer Brave
What are my preferences
Continue what I was doing
```

---

## 9. Setup

### Prerequisites
- **Python**: CPython 3.12 (check `.python-version`)
- **OS**: macOS 13+ (tested & verified on Apple Silicon / Intel) or Windows 10/11 x64

### 1. Clone & Environment Setup

```bash
# macOS
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

```powershell
# Windows PowerShell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Configure your API credentials in `.env`:
```ini
# Google Gemini (Primary Planner)
GEMINI_API_KEY=your_gemini_api_key_here

# Groq (Optional macOS Fallback)
GROQ_API_KEY=your_groq_api_key_here
```
*Note: Deterministic commands, memory operations, and test suites operate without API keys.*

### 3. Optional Voice Setup

To enable local microphone input:

```bash
pip install -r requirements-voice.txt
python provision_voice.py
```
This downloads the pinned `base.en` Whisper model to your local user cache (`~/.cache/huggingface/hub`).

### 4. Running the Agent

**CLI Mode (One command per execution):**
```bash
.venv/bin/python main.py
```

**Desktop UI Mode:**
```bash
.venv/bin/python -B desktop_ui.py
```

---

## 10. Testing

The repository maintains an extensive, fully isolated offline test suite. All tests mock external AI provider calls, operating system launches, and filesystem writes.

Run the test suite using the standard project command:

```bash
.venv/bin/python -m pytest --tb=short -q
```

**Release Verification Result:**
```text
1096 passed in 47.38s
```

All 1,096 tests pass completely offline without requiring network access or live API credentials.

---

## 11. Platform Support

- **macOS (Fully Validated)**:
  - Native application launch and termination via `/usr/bin/open` and AppleScript / `pkill`.
  - Full workspace support (apps, trusted URLs, and folder aliases).
  - Groq AI provider fallback.
  - Native desktop UI and voice capture.
- **Windows (Supported with Known Constraints)**:
  - Fixed executable discovery paths for configured applications (LOCALAPPDATA, Program Files).
  - Browser and site automation via default browser / Brave.
  - Workspace management features are macOS-only.
  - Groq fallback dependency is excluded on Windows.

---

## 12. Known Limitations

- **Acoustic Sensitivity**: Local voice capture relies on energy VAD; accuracy degrades in noisy environments or with low-quality microphones.
- **Application Allowlist**: Only explicitly mapped applications in `config.py` can be opened or closed.
- **Folder Containment**: Workspace folders are constrained to predefined aliases in `config.WORKSPACE_FOLDERS` and must exist within the user home directory.
- **Cloud Dependency for Planning**: Natural-language planning requires network connectivity to Google Gemini (or Groq). Deterministic commands work fully offline.
- **No Background Daemon**: The application runs interactively and does not maintain a background daemon or listen to global hotkeys.

---

## 13. Future Improvements

- **Neural Noise Suppression**: Integration of pre-ASR speech enhancement (e.g., DeepFilterNet) for improved voice capture in noisy rooms.
- **Faster Voice Inference**: Streaming ASR and model warm-up optimizations.
- **Background Daemon / Global Hotkey**: Optional system tray daemon with a global shortcut for summoning the UI.
- **Extended Platform Adapters**: Deeper Windows workspace parity and expanded Linux desktop support.

---

## 14. Project Status

This repository is a **completed, release-ready portfolio project** demonstrating safe, production-grade agentic design patterns, structured LLM planning, multi-provider fault tolerance, and constrained local automation.
