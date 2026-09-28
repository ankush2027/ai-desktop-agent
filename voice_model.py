"""Pinned public model cache contract; no imports/downloads at module load."""

from pathlib import Path

from voice import VoiceInputFailure

MODEL_ID = "Systran/faster-whisper-base.en"
MODEL_REVISION = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"
MODEL_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
REPOSITORY_ROOT = Path(__file__).resolve().parent


def external_path(path):
    resolved = Path(path).expanduser().resolve()
    if resolved.is_relative_to(REPOSITORY_ROOT):
        raise VoiceInputFailure("cache")
    return resolved


def model_snapshot(*, provision=False):
    """Only the explicit provisioning CLI permits network access."""
    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.constants import HF_HUB_CACHE
    except ImportError:
        raise VoiceInputFailure("dependencies") from None
    cache = external_path(HF_HUB_CACHE)
    model_cache = external_path(cache / ("models--" + MODEL_ID.replace("/", "--")))
    external_path(model_cache / "blobs")
    expected = external_path(model_cache / "snapshots" / MODEL_REVISION)
    for name in MODEL_FILES:
        external_path(expected / name)
    try:
        snapshot = external_path(snapshot_download(
            MODEL_ID, revision=MODEL_REVISION, cache_dir=str(cache),
            allow_patterns=list(MODEL_FILES), local_files_only=not provision, token=False,
        ))
        for name in MODEL_FILES:
            file = external_path(snapshot / name)
            if not file.is_file() or file.stat().st_size == 0:
                raise VoiceInputFailure("model")
        return snapshot
    except VoiceInputFailure:
        raise
    except Exception:
        raise VoiceInputFailure("model") from None
