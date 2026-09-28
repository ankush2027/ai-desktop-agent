# Local voice input

The desktop Microphone button uses `InteractionController.submit_voice()` ->
`LocalVoiceInput` -> in-memory microphone capture -> faster-whisper -> ordinary
text -> the controller's existing Agent Core path. The provider imports no agent,
parser, memory, database, policy, or desktop-action modules. TTS remains absent.

## Install and provision

Use 64-bit CPython 3.12: Windows x64, macOS 13+ Intel, or macOS 14+ Apple Silicon.
Use native Python on Apple Silicon. From the repository root:

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe provision_voice.py
.\.venv\Scripts\python.exe -B desktop_ui.py
```

macOS:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-voice.txt
.venv/bin/python -m pip check
.venv/bin/python provision_voice.py
.venv/bin/python -B desktop_ui.py
```

Skip venv creation if it already exists. Text-only installation uses
`requirements.txt`; `requirements-dev.txt` adds tests. Voice dependencies remain
optional, with direct/transitive pins in `constraints.txt` and
`constraints-voice.txt`. No API key, login, `.env`, or new variable is required.

`provision_voice.py` explicitly downloads the public English **base.en** model:

- Repository: `Systran/faster-whisper-base.en`
- Immutable revision: `3d3d5dee26484f91867d81cb899cfcf72b96be6c`
- Files: `config.json`, `model.bin`, `tokenizer.json`, `vocabulary.txt`

Provisioning needs internet and writable disk space. Repeating it reuses the
cached files. The default Hugging Face cache is `~/.cache/huggingface/hub` on both
systems; `~` means the current user's home. Existing `HF_HOME`, `HF_HUB_CACHE`, or
`XDG_CACHE_HOME` settings may change that location. Repository-local caches are
rejected, including resolved symlinks into this checkout. Keep models outside Git.
Successful provisioning prints the pinned revision and snapshot path.

Recognition only resolves that revision with `local_files_only=True`; it never
provisions or falls back to an arbitrary revision. All four files must be present
and nonempty before Whisper loads. Missing/incomplete files produce a controlled
notice directing the user to provisioning. CPU INT8 model loading is lazy, on the
first microphone request, and the same model is reused for the process lifetime.
Imports and ordinary typed commands do not import the optional speech stack or
load a model. A restarted UI reloads the cached model into RAM on first use.

## Capture and cancellation

Capture uses the default input device at 16 kHz, mono float32. `CaptureConfig` in
`local_voice.py` holds the defaults: 5 seconds to start speaking, 15 seconds maximum
utterance, and 0.8 seconds of trailing silence. The RMS onset threshold is three
times the tracked quiet-block noise level, with a 0.001 floor and the configured
0.015 ceiling. The initial noise estimate is 0.0003; quiet blocks update it with
10% weight, and speech blocks do not raise it. Onset requires 100 ms of consecutive
speech-level audio; continuation uses 60% of the onset threshold so quieter
syllables do not prematurely end capture. Settings
must be finite and positive; start/utterance limits are capped at 30/60 seconds.
A 0.2-second pre-roll preserves speech onset. The callback queue is bounded;
overflows and interrupted audio fail safely. Exceeding the utterance limit rejects
the request rather than dispatching a truncated command.

Click Cancel or dismiss the window to cancel. Capture checks cancellation at most
every 50 ms between Python operations and always attempts abort/close in `finally`,
including stream-start failures. The microphone is closed **before** transcription.
Native driver calls, model loading, and Whisper inference cannot necessarily be
interrupted immediately. Cancellation during inference suppresses dispatch when
native code returns; dismissal hides the window while its worker finishes. No
hard wall-clock deadline for native inference or a stalled driver is claimed.
Only one request per provider/controller can run at a time.

No audio/WAV files or transcripts are written by the provider. Recognition is local
and can run offline after provisioning. Recognized text follows the normal agent
flow: explicit memory commands may persist text, and AI fallback may send text and
context to Gemini under existing behavior. Use a deterministic command such as
`help` for a fully offline smoke test.

## Permissions, troubleshooting, and limitations

- Windows: enable Microphone access and Let desktop apps access your microphone
  under Settings > Privacy & security > Microphone. Missing native DLLs may require
  the official [Visual C++ x64 runtime](https://aka.ms/vs/17/release/vc_redist.x64.exe).
- macOS: grant the launching terminal/app permission under System Settings >
  Privacy & Security > Microphone, then relaunch. Working Tcl/Tk is needed for the UI.
- Select a connected default input device in OS settings. A device that cannot
  open mono 16 kHz produces an actionable error; this implementation does not add
  resampling or a device picker. Close other applications holding the microphone.
- The first request imports the optional libraries and checks the model cache
  before capture. Model initialization now happens after the microphone closes,
  so cold model loading cannot swallow speech. The UI currently shows Listening
  during capture, loading, and inference; subsequent requests reuse the model.
- RMS silence detection is approximate. Background noise, quiet speech, long pauses,
  and Whisper hallucinations can affect results. VAD also filters transcription.
  Use short English commands; there is no confirmation step added to existing routing.
- Wheels supply PortAudio and FFmpeg libraries; no separate audio library, compiler,
  CUDA, or GPU setup is needed. ONNX Runtime 1.23.2 and cryptography 48.0.1 retain
  Intel Mac wheels; PyAV 18.1.0 requires macOS 14+ on Apple Silicon. Windows ARM64
  and 32-bit Python are not validated targets. Do not bypass wheel-only installation
  with undocumented source builds.
- Hugging Face caching works without Windows symlink privileges, potentially using
  more disk space. Administrator execution is not a setup requirement.

## Manual native smoke test (both Windows and macOS)

Use a disposable copy containing this implementation if you need to protect an
existing personal database/history. Install, provision, and launch with the commands
above; model weights remain in the external user cache.

1. Type `help`, press Send, and verify the normal command-help response.
2. Click Microphone, speak `help`, then remain silent. Verify the same help response
   arrives through the normal controller/core flow. Repeat to exercise model reuse.
3. Click Microphone and then Cancel; verify no command runs and the previous result
   remains. Repeat with dismissal. If inference is already running, allow it to finish.
4. Try remaining silent, disabling the input device, or denying permission. Verify
   a controlled notice and preserved previous response; typed `help` must still work.

Do not use destructive or memory-changing commands for the smoke test.
Cross-target wheel resolution does not prove native Mac behavior. Provisioning
the real model is an explicit manual step, not a test.

## Automated verification

Install `requirements-dev.txt` into the same venv. Using its Python interpreter:

```text
python -B -m pytest -q -p no:cacheprovider test_local_voice.py test_interaction.py test_desktop_ui.py
python -B -m pytest -q -p no:cacheprovider
python -m pip check
```

Tests mock microphone, model, arrays, and timing and use the existing isolated
storage fixtures. They require neither optional voice libraries nor a model,
network, microphone, Gemini key, or audio files. Existing setup validation confirmed
Windows native library imports, CPU INT8 availability, and wheel resolution for
both Mac architectures; see README for import-only verification.

Initial implementation validation on Windows / CPython 3.12.14: **109 focused tests passed**,
**690 full-suite tests passed**, 84 Python sources compiled, and `pip check` passed
in both text-only and voice environments. Synthetic capture with real NumPy passed
without hardware. Protected database/history hashes remained unchanged. No real
Whisper model was provisioned or native speech recognition exercised.

Reliability fix validation (2026-09-27): **706 tests passed** with
`python -m pytest -q -p no:cacheprovider`; changed Python sources passed
`py_compile`. New tests cover quiet speech, short commands, trailing silence,
internal pauses, noise adaptation, clicks, cold-load ordering, and the three
exact command transcripts reaching the deterministic core. Cancellation and
capture-limit regressions remain covered.

A native Windows run used the existing UI/controller and real microphone/Whisper
in a temporary source copy. Capture produced float32 audio and transcripts;
`Open Calculator` reached the deterministic route and succeeded. `Open YouTube`
was transcribed with terminal punctuation and routed to AI fallback, which failed.
The user reported `AI service unavailable` for `Open Google` as well; its exact
transcript was not retained. Native provider initialization reproduced
`AIProviderError` caused by `ValueError` for the absent/empty Gemini credential.
Parser and Gemini configuration were left unchanged. Normal sitting distance was
requested but not independently verified; native macOS remains untested.

References: [model revision](https://huggingface.co/Systran/faster-whisper-base.en/tree/3d3d5dee26484f91867d81cb899cfcf72b96be6c),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[sounddevice](https://python-sounddevice.readthedocs.io/en/latest/installation.html),
[Hugging Face cache](https://huggingface.co/docs/huggingface_hub/guides/manage-cache).
