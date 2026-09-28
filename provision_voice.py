"""Explicit one-time download of the pinned English voice model."""

from voice import VoiceInputFailure
from voice_model import MODEL_ID, MODEL_REVISION, model_snapshot


def main():
    try:
        path = model_snapshot(provision=True)
    except VoiceInputFailure as exc:
        print(exc.notice)
        print("Provisioning requires internet access and a writable external cache. See VOICE_SETUP.md.")
        return 1
    print(f"Ready: {MODEL_ID} at revision {MODEL_REVISION}")
    print(f"Model cache: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
