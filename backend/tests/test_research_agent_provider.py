"""Configuration tests for the six-agent model provider."""

from unittest.mock import patch

import pytest

from app.services import research_agents


def test_ollama_is_the_default_provider_without_an_openai_key(monkeypatch):
    monkeypatch.delenv("ARTHVEST_AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("ARTHVEST_AGENT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    status = research_agents.get_agent_status()

    assert status["provider_id"] == "ollama"
    assert status["configured"] is True
    assert status["model"] == "qwen2.5:7b"
    assert "OPENAI_API_KEY" not in status["note"]


def test_local_model_uses_the_configured_ollama_endpoint(monkeypatch):
    monkeypatch.setenv("ARTHVEST_AGENT_PROVIDER", "ollama")
    monkeypatch.setenv("ARTHVEST_AGENT_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

    with (
        patch.object(research_agents, "set_tracing_disabled") as tracing_disabled,
        patch.object(research_agents, "AsyncOpenAI") as async_openai,
        patch.object(research_agents, "OpenAIChatCompletionsModel") as chat_model,
    ):
        result = research_agents._build_model()

    tracing_disabled.assert_called_once_with(True)
    async_openai.assert_called_once()
    assert async_openai.call_args.kwargs["base_url"] == "http://127.0.0.1:11434/v1"
    assert async_openai.call_args.kwargs["api_key"] == "ollama"
    chat_model.assert_called_once_with(
        model="qwen2.5:7b",
        openai_client=async_openai.return_value,
    )
    assert result is chat_model.return_value


def test_openai_provider_requires_a_key(monkeypatch):
    monkeypatch.setenv("ARTHVEST_AGENT_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        research_agents._build_model()


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("ARTHVEST_AGENT_PROVIDER", "unknown-provider")

    with pytest.raises(RuntimeError, match="Unsupported ARTHVEST_AGENT_PROVIDER"):
        research_agents._build_model()
