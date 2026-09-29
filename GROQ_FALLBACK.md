# macOS Groq planner fallback

Gemini remains the primary provider for every request. On macOS only,
`ProviderManager` makes one Groq request if Gemini reports a transient failure:

- HTTP 408, 500, 502, 503, or 504.
- An HTTPX timeout, network error, or remote protocol error.
- A provider-level `TimeoutError` or `ConnectionError`.

The official Groq SDK uses the fixed model `openai/gpt-oss-120b` and Groq endpoint.
Its completion is non-streaming, with a 20-second request timeout and SDK retries
disabled. Like the existing Gemini wrapper, it leaves temperature and output-token
settings at provider defaults. The existing response-size and action-count limits
remain in the shared planner validator. Incomplete and tool-call responses fail.

Groq gets exactly the planner prompt sent to Gemini, including its context. Its
text follows the existing pipeline:

```text
Gemini ── success ───────────────────────────────┐
   └── transient failure on macOS → Groq text ──┤
                                               ↓
AIBrain JSON parser → shared validate_plan → ActionPolicy → executor
```

There is no fallback for missing Gemini configuration, authentication failures,
HTTP 429 quota/rate limits, other non-allowlisted errors, empty Gemini output,
malformed JSON, invalid schema/actions, unsafe parameters, policy rejection, or
execution failure. Groq failure ends the request; there is no provider loop.
Explicitly injected providers remain isolated unless an explicit fallback provider
is also injected. Windows keeps its Gemini-only path and does not install Groq.

## Configuration

From the project directory on macOS, install the updated pinned dependencies:

```sh
.venv/bin/python -m pip install -r requirements.txt
```

Set `GROQ_API_KEY` privately in your environment or the ignored `.env` file.
`.env.example` contains an empty placeholder only. An existing environment value
takes precedence over `.env`. Keep the existing Gemini key configured; Groq is not
a replacement primary. A missing Groq key leaves successful Gemini requests
unaffected and produces a controlled service error if fallback is needed.

## Manual real-provider smoke test (planning only)

Run this only after the mocked tests pass. It sends the harmless command to Groq
using the existing planner prompt, parses the response, applies the existing
schema and ActionPolicy, and checks the exact expected action. It does not call
an executor, open Calculator, read memory, or print credentials/provider payloads.
A real request uses your Groq account quota. Do not enable SDK debug logging while
handling private prompts.

```sh
.venv/bin/python - <<'PY'
import json
import platform
from ai.brain import AIBrain
from ai.groq import GroqProvider
from ai.action_policy import ActionPolicy
from ai.errors import AIServiceError

if platform.system() != "Darwin":
    raise SystemExit("This smoke test is macOS only.")
provider = None
try:
    provider = GroqProvider()
    plan = AIBrain(provider=provider).plan("Open Calculator")
    actions = ActionPolicy().validate(plan["actions"])
    expected = [{"action": "open", "target": "calculator", "params": {}}]
    if actions != expected:
        raise SystemExit("Unexpected plan; nothing executed.")
    print(json.dumps({"actions": actions}))
    print("Groq planner and policy smoke test passed; nothing executed.")
except AIServiceError:
    raise SystemExit("Groq smoke test failed; nothing executed.") from None
finally:
    if provider is not None:
        provider.client.close()
PY
```

Expected action output:

```json
{"actions": [{"action": "open", "target": "calculator", "params": {}}]}
```

This isolates Groq deliberately; mocked integration tests verify the automatic
Gemini-to-Groq transition without manufacturing a real Gemini outage.

## Mocked tests

```sh
.venv/bin/python -m pytest --tb=short -q test_groq_provider.py test_ai_provider.py test_provider_manager.py test_ai_brain.py test_ai_integration.py test_action_policy.py test_reliability.py
.venv/bin/python -m pytest --tb=short -q
```

Tests use fake credentials and mocked SDK calls/HTTP transports. The test harness
removes any inherited Groq key before collection and restores the caller's
environment afterward. No real provider smoke test runs as part of pytest.
