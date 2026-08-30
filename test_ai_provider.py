import os

from ai import GeminiProvider


def test_provider_initializes_when_api_key_exists():
    """Provider initialization should work when GEMINI_API_KEY is present."""
    original = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "test-key"

    try:
        provider = GeminiProvider()
        assert provider is not None
        assert provider.api_key == "test-key"
        assert provider.client is not None
    finally:
        if original is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = original


if __name__ == "__main__":
    test_provider_initializes_when_api_key_exists()
    print("Gemini provider tests passed.")
