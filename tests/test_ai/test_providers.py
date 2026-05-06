"""Tests pour les LLM providers (Anthropic, OpenAI, Ollama).

Tous les appels reseau sont mockes — aucune cle API requise pour faire tourner
ces tests. Couverture cible : >=80% sur winboost/ai/providers/.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from winboost.ai.providers.anthropic_provider import AnthropicProvider
from winboost.ai.providers.base import BaseLLMProvider, LLMResponse
from winboost.ai.providers.ollama_provider import OllamaProvider
from winboost.ai.providers.openai_provider import OpenAIProvider

# --- LLMResponse + BaseLLMProvider ---


class TestLLMResponse:
    def test_default_fields(self):
        r = LLMResponse(text="hello")
        assert r.text == "hello"
        assert r.model == ""
        assert r.provider == ""
        assert r.usage is None
        assert r.raw is None

    def test_full_fields(self):
        r = LLMResponse(
            text="hi",
            model="claude-x",
            provider="anthropic",
            usage={"input_tokens": 10, "output_tokens": 5},
            raw={"id": "msg_123"},
        )
        assert r.usage == {"input_tokens": 10, "output_tokens": 5}
        assert r.raw == {"id": "msg_123"}


class TestBaseProviderIsAbstract:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseLLMProvider()  # type: ignore[abstract]


# --- AnthropicProvider ---


class TestAnthropicProviderInit:
    def test_uses_explicit_api_key(self):
        p = AnthropicProvider(api_key="sk-ant-test")
        assert p._api_key == "sk-ant-test"

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
        p = AnthropicProvider()
        assert p._api_key == "sk-ant-from-env"

    def test_default_model(self):
        p = AnthropicProvider(api_key="x")
        assert "claude" in p._model

    def test_custom_model(self):
        p = AnthropicProvider(api_key="x", model="claude-opus-4-7")
        assert p._model == "claude-opus-4-7"

    def test_name(self):
        assert AnthropicProvider(api_key="x").name == "anthropic"

    def test_no_key_no_env(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = AnthropicProvider()
        assert p._api_key == ""


class TestAnthropicProviderIsAvailable:
    def test_returns_false_without_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert AnthropicProvider().is_available() is False

    def test_returns_true_with_key_and_lib(self):
        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            assert AnthropicProvider(api_key="x").is_available() is True

    def test_returns_false_when_lib_missing(self):
        # Simule l'absence d'anthropic
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("No module named anthropic")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            assert AnthropicProvider(api_key="x").is_available() is False


class TestAnthropicProviderComplete:
    def _mock_anthropic(self, text="hello world", in_tok=12, out_tok=8):
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_content = MagicMock()
        mock_content.text = text
        mock_message.content = [mock_content]
        mock_message.usage.input_tokens = in_tok
        mock_message.usage.output_tokens = out_tok
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.Anthropic.return_value = mock_client
        return mock_anthropic, mock_client, mock_message

    def test_returns_text(self):
        mock_anthropic, _, _ = self._mock_anthropic(text="bonjour")
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            p = AnthropicProvider(api_key="sk-ant-x")
            r = p.complete("hello")
            assert r.text == "bonjour"
            assert r.provider == "anthropic"

    def test_returns_usage(self):
        mock_anthropic, _, _ = self._mock_anthropic(in_tok=42, out_tok=17)
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            r = AnthropicProvider(api_key="x").complete("ping")
            assert r.usage == {"input_tokens": 42, "output_tokens": 17}

    def test_uses_default_system_prompt(self):
        mock_anthropic, mock_client, _ = self._mock_anthropic()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            AnthropicProvider(api_key="x").complete("ping")
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert "WinBoost" in call_kwargs["system"]

    def test_uses_custom_system_prompt(self):
        mock_anthropic, mock_client, _ = self._mock_anthropic()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            AnthropicProvider(api_key="x").complete("ping", system="You are a cat")
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["system"] == "You are a cat"

    def test_handles_empty_content(self):
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = []
        mock_message.usage.input_tokens = 5
        mock_message.usage.output_tokens = 0
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            r = AnthropicProvider(api_key="x").complete("ping")
            assert r.text == ""

    def test_passes_model(self):
        mock_anthropic, mock_client, _ = self._mock_anthropic()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            AnthropicProvider(api_key="x", model="claude-opus-4-7").complete("ping")
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["model"] == "claude-opus-4-7"


# --- OpenAIProvider ---


class TestOpenAIProviderInit:
    def test_uses_explicit_api_key(self):
        p = OpenAIProvider(api_key="sk-proj-test")
        assert p._api_key == "sk-proj-test"

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-env")
        p = OpenAIProvider()
        assert p._api_key == "sk-proj-env"

    def test_default_model(self):
        p = OpenAIProvider(api_key="x")
        assert "gpt" in p._model

    def test_name(self):
        assert OpenAIProvider(api_key="x").name == "openai"


class TestOpenAIProviderIsAvailable:
    def test_returns_false_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert OpenAIProvider().is_available() is False

    def test_returns_true_with_key_and_lib(self):
        with patch.dict("sys.modules", {"openai": MagicMock()}):
            assert OpenAIProvider(api_key="x").is_available() is True

    def test_returns_false_when_lib_missing(self):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("No module named openai")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            assert OpenAIProvider(api_key="x").is_available() is False


class TestOpenAIProviderComplete:
    def _mock_openai(self, text="hi from gpt", prompt_tok=5, comp_tok=3):
        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = text
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = prompt_tok
        mock_response.usage.completion_tokens = comp_tok
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.OpenAI.return_value = mock_client
        return mock_openai, mock_client, mock_response

    def test_returns_text(self):
        mock_openai, _, _ = self._mock_openai(text="hello there")
        with patch.dict("sys.modules", {"openai": mock_openai}):
            r = OpenAIProvider(api_key="x").complete("ping")
            assert r.text == "hello there"
            assert r.provider == "openai"

    def test_returns_usage(self):
        mock_openai, _, _ = self._mock_openai(prompt_tok=20, comp_tok=10)
        with patch.dict("sys.modules", {"openai": mock_openai}):
            r = OpenAIProvider(api_key="x").complete("ping")
            assert r.usage == {"input_tokens": 20, "output_tokens": 10}

    def test_handles_none_content(self):
        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            r = OpenAIProvider(api_key="x").complete("ping")
            assert r.text == ""
            assert r.usage == {}

    def test_uses_custom_system(self):
        mock_openai, mock_client, _ = self._mock_openai()
        with patch.dict("sys.modules", {"openai": mock_openai}):
            OpenAIProvider(api_key="x").complete("ping", system="be brief")
            messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
            assert messages[0]["content"] == "be brief"
            assert messages[1]["content"] == "ping"

    def test_uses_default_system(self):
        mock_openai, mock_client, _ = self._mock_openai()
        with patch.dict("sys.modules", {"openai": mock_openai}):
            OpenAIProvider(api_key="x").complete("ping")
            messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
            assert "WinBoost" in messages[0]["content"]


# --- OllamaProvider ---


class TestOllamaProviderInit:
    def test_default_model(self):
        p = OllamaProvider()
        assert p._model == "llama3.2"

    def test_default_base_url(self):
        p = OllamaProvider()
        assert p._base_url == "http://localhost:11434"

    def test_strips_trailing_slash(self):
        p = OllamaProvider(base_url="http://localhost:11434/")
        assert p._base_url == "http://localhost:11434"

    def test_custom_model(self):
        p = OllamaProvider(model="qwen2.5")
        assert p._model == "qwen2.5"

    def test_name(self):
        assert OllamaProvider().name == "ollama"


class TestOllamaProviderIsAvailable:
    def test_returns_true_when_server_responds(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            assert OllamaProvider().is_available() is True

    def test_returns_false_on_url_error(self):
        from urllib.error import URLError
        with patch("urllib.request.urlopen", side_effect=URLError("no server")):
            assert OllamaProvider().is_available() is False

    def test_returns_false_on_os_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            assert OllamaProvider().is_available() is False

    def test_returns_false_on_non_200(self):
        mock_resp = MagicMock()
        mock_resp.status = 503
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            assert OllamaProvider().is_available() is False


class TestOllamaProviderComplete:
    def test_returns_text(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"response": "salut"}).encode("utf-8")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            r = OllamaProvider().complete("ping")
            assert r.text == "salut"
            assert r.provider == "ollama"

    def test_returns_empty_text_on_missing_field(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({}).encode("utf-8")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            r = OllamaProvider().complete("ping")
            assert r.text == ""

    def test_payload_has_correct_fields(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"response": "ok"}).encode("utf-8")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            OllamaProvider(model="my-model").complete("salut", system="be short")
            # Inspect the request body
            req = mock_urlopen.call_args[0][0]
            body = json.loads(req.data.decode("utf-8"))
            assert body["model"] == "my-model"
            assert body["prompt"] == "salut"
            assert body["system"] == "be short"
            assert body["stream"] is False

    def test_default_system_prompt_when_empty(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"response": "ok"}).encode("utf-8")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            OllamaProvider().complete("ping")
            req = mock_urlopen.call_args[0][0]
            body = json.loads(req.data.decode("utf-8"))
            assert "WinBoost" in body["system"]

    def test_returns_no_usage(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"response": "ok"}).encode("utf-8")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            r = OllamaProvider().complete("ping")
            assert r.usage is None
