import os
import tempfile
from pathlib import Path

from ai import GeminiProvider
import httpx


class FakeInteractionResponse:
    def __init__(self, output_text):
        self.output_text = output_text


class FakeInteractions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeInteractionResponse("ok")


class FakeClient:
    def __init__(self):
        self.interactions = FakeInteractions()


def _patch_genai_client(fake_client):
    import ai.gemini as gemini_module

    original = gemini_module.genai.Client
    gemini_module.genai.Client = lambda api_key: fake_client
    return original


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


def test_provider_loads_dotenv_file_without_real_api_call():
    """Provider initialization should load a local .env file before reading the API key."""
    import ai.gemini as gemini_module

    fake_client = FakeClient()
    original_client = _patch_genai_client(fake_client)
    original_cwd = os.getcwd()

    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env"
        env_path.write_text("GEMINI_API_KEY=dotenv-key\n")
        os.chdir(tmpdir)

        try:
            provider = GeminiProvider()
            assert provider.api_key == "dotenv-key"
            assert provider.client is fake_client
        finally:
            os.chdir(original_cwd)
            gemini_module.genai.Client = original_client


def test_generate_text_uses_supported_model_without_real_api_call():
    """generate_text should use the supported Interactions API and not require a real call."""
    import ai.gemini as gemini_module

    fake_client = FakeClient()
    original = _patch_genai_client(fake_client)

    try:
        provider = GeminiProvider(api_key="test-key", model_name="gemini-3.6-flash")
        result = provider.generate_text("hello")

        assert result == "ok"
        assert fake_client.interactions.calls[0]["model"] == "gemini-3.6-flash"
        assert fake_client.interactions.calls[0]["input"] == "hello"
        assert fake_client.interactions.calls[0]["timeout"] == 20.0
    finally:
        gemini_module.genai.Client = original


def test_generate_text_handles_connection_failure_without_real_api_call():
    """Connection errors should become a clean application-level exception."""
    import ai.gemini as gemini_module

    class FailingInteractions:
        def create(self, **kwargs):
            raise httpx.ConnectError("connection refused")

    fake_client = type("FakeClient", (), {"interactions": FailingInteractions()})()
    original = _patch_genai_client(fake_client)

    try:
        provider = GeminiProvider(api_key="test-key")
        try:
            provider.generate_text("hello")
            assert False, "Expected GeminiProviderError"
        except ValueError as exc:
            assert "Gemini request failed" in str(exc)
    finally:
        gemini_module.genai.Client = original


def test_generate_text_handles_timeout_without_real_api_call():
    """Timeouts should fail fast with a clean application-level exception."""
    import ai.gemini as gemini_module

    class TimeoutInteractions:
        def create(self, **kwargs):
            from google.genai._gaos.lib.compat_errors import APITimeoutError

            raise APITimeoutError("request timed out")

    fake_client = type("FakeClient", (), {"interactions": TimeoutInteractions()})()
    original = _patch_genai_client(fake_client)

    try:
        provider = GeminiProvider(api_key="test-key")
        try:
            provider.generate_text("hello")
            assert False, "Expected GeminiProviderError"
        except ValueError as exc:
            assert "Gemini request failed" in str(exc)
    finally:
        gemini_module.genai.Client = original


if __name__ == "__main__":
    test_provider_initializes_when_api_key_exists()
    test_provider_loads_dotenv_file_without_real_api_call()
    test_generate_text_uses_supported_model_without_real_api_call()
    test_generate_text_handles_connection_failure_without_real_api_call()
    test_generate_text_handles_timeout_without_real_api_call()
    print("Gemini provider tests passed.")
