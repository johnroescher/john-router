"""Tests for the LLM backend swap from Anthropic to NVIDIA NIM (Kimi K2.5).

Covers:
- llm_client module (singleton, no-key fallback, base URL)
- Service constructors use shared client
- Health endpoint reports nvidia_llm
- ride_brief_loop _llm_json fallback when client is None
- Live NVIDIA NIM connectivity (skipped when NVIDIA_API_KEY is absent)
"""
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# llm_client module
# ---------------------------------------------------------------------------

class TestLLMClient:
    """Tests for app.services.llm_client."""

    def test_get_llm_model_returns_kimi(self):
        from app.services.llm_client import get_llm_model
        assert get_llm_model() == "moonshotai/kimi-k2.5"

    def test_get_llm_client_returns_none_without_key(self):
        import app.services.llm_client as mod
        mod._client = None
        with patch.object(mod.settings, "nvidia_api_key", None):
            client = mod.get_llm_client()
            assert client is None

    def test_get_llm_client_creates_openai_with_key(self):
        import app.services.llm_client as mod
        mod._client = None
        with patch.object(mod.settings, "nvidia_api_key", "test-key"):
            client = mod.get_llm_client()
            assert client is not None
            assert client.base_url is not None
            assert "nvidia" in str(client.base_url)
        mod._client = None

    def test_get_llm_client_singleton(self):
        import app.services.llm_client as mod
        mod._client = None
        with patch.object(mod.settings, "nvidia_api_key", "test-key"):
            c1 = mod.get_llm_client()
            c2 = mod.get_llm_client()
            assert c1 is c2
        mod._client = None

    def test_base_url_is_nvidia_nim(self):
        from app.services.llm_client import _LLM_BASE_URL
        assert _LLM_BASE_URL == "https://integrate.api.nvidia.com/v1"

    def test_clamp_max_tokens_raises_floor(self):
        from app.services.llm_client import clamp_max_tokens, MIN_MAX_TOKENS
        assert clamp_max_tokens(300) == MIN_MAX_TOKENS
        assert clamp_max_tokens(500) == MIN_MAX_TOKENS
        assert clamp_max_tokens(20000) == 20000

    def test_extract_llm_text_prefers_content(self):
        from app.services.llm_client import extract_llm_text
        choice = MagicMock()
        choice.message.content = "hello"
        choice.message.reasoning = "thinking..."
        assert extract_llm_text(choice) == "hello"

    def test_extract_llm_text_falls_back_to_reasoning(self):
        from app.services.llm_client import extract_llm_text
        choice = MagicMock()
        choice.message.content = None
        choice.message.reasoning = "thinking output"
        assert extract_llm_text(choice) == "thinking output"

    def test_extract_llm_text_returns_empty_when_nothing(self):
        from app.services.llm_client import extract_llm_text
        choice = MagicMock()
        choice.message.content = None
        choice.message.reasoning = None
        assert extract_llm_text(choice) == ""


# ---------------------------------------------------------------------------
# Service constructors
# ---------------------------------------------------------------------------

class TestServiceConstructors:
    """All LLM services should use get_llm_client / get_llm_model."""

    def _assert_service_uses_shared_client(self, service_class):
        with patch("app.services.llm_client.get_llm_client", return_value=None), \
             patch("app.services.llm_client.get_llm_model", return_value="test-model"):
            svc = service_class()
            assert svc.client is None
            assert svc.model == "test-model"

    def test_ride_brief_loop(self):
        from app.services.ride_brief_loop import RideBriefLoopService
        self._assert_service_uses_shared_client(RideBriefLoopService)

    def test_route_evaluator(self):
        from app.services.route_evaluator import RouteEvaluator
        self._assert_service_uses_shared_client(RouteEvaluator)

    def test_route_improver(self):
        from app.services.route_improver import RouteImprover
        self._assert_service_uses_shared_client(RouteImprover)

    def test_route_modifier(self):
        from app.services.route_modifier import RouteModifier
        self._assert_service_uses_shared_client(RouteModifier)

    def test_route_planner(self):
        from app.services.route_planner import IntelligentRoutePlanner
        self._assert_service_uses_shared_client(IntelligentRoutePlanner)

    def test_response_generator(self):
        from app.services.response_generator import ResponseGenerator
        self._assert_service_uses_shared_client(ResponseGenerator)

    def test_cycling_facts(self):
        from app.services.cycling_facts import CyclingFactsService
        self._assert_service_uses_shared_client(CyclingFactsService)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Health endpoint should report nvidia_llm, not anthropic."""

    def test_health_services_nvidia_configured(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        response = client.get("/api/health/services")
        data = response.json()
        assert "nvidia_llm" in data["services"]
        assert "anthropic" not in data["services"]


# ---------------------------------------------------------------------------
# ride_brief_loop fallback
# ---------------------------------------------------------------------------

class TestRideBriefLoopFallback:
    """_llm_json returns {} when client is None."""

    @pytest.mark.asyncio
    async def test_llm_json_returns_empty_when_no_client(self):
        from app.services.ride_brief_loop import RideBriefLoopService
        with patch("app.services.llm_client.get_llm_client", return_value=None), \
             patch("app.services.llm_client.get_llm_model", return_value="test"):
            svc = RideBriefLoopService()
            result = await svc._llm_json("test prompt")
            assert result == {}

    @pytest.mark.asyncio
    async def test_llm_json_calls_chat_completions(self):
        """When client exists, _llm_json calls chat.completions.create."""
        from app.services.ride_brief_loop import RideBriefLoopService

        mock_choice = MagicMock()
        mock_choice.message = MagicMock()
        mock_choice.message.content = '{"test": true}'
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("app.services.llm_client.get_llm_client", return_value=mock_client), \
             patch("app.services.llm_client.get_llm_model", return_value="test-model"):
            svc = RideBriefLoopService()
            result = await svc._llm_json("test prompt")

        assert result == {"test": True}
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["messages"] == [{"role": "user", "content": "test prompt"}]


# ---------------------------------------------------------------------------
# Chat exception handling
# ---------------------------------------------------------------------------

class TestChatExceptionHandling:
    """chat.py should catch openai exceptions, not anthropic."""

    def test_imports_openai_not_anthropic(self):
        import app.api.chat as chat_mod
        import inspect
        source = inspect.getsource(chat_mod)
        assert "import openai" in source
        assert "import anthropic" not in source


# ---------------------------------------------------------------------------
# No remaining anthropic imports in production code
# ---------------------------------------------------------------------------

class TestNoAnthropicInProduction:
    """No production service should import anthropic (except deprecated ai_copilot)."""

    def test_no_anthropic_in_ride_brief_loop(self):
        import inspect
        from app.services import ride_brief_loop
        source = inspect.getsource(ride_brief_loop)
        assert "from anthropic" not in source
        assert "import anthropic" not in source

    def test_no_anthropic_in_route_evaluator(self):
        import inspect
        from app.services import route_evaluator
        source = inspect.getsource(route_evaluator)
        assert "from anthropic" not in source

    def test_no_anthropic_in_chat(self):
        import inspect
        from app.api import chat
        source = inspect.getsource(chat)
        assert "import anthropic" not in source


# ---------------------------------------------------------------------------
# Live NVIDIA NIM test (skipped when no key)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("NVIDIA_API_KEY"),
    reason="NVIDIA_API_KEY not set; skipping live NIM test",
)
class TestLiveNVIDIANIM:
    """Live connectivity test against NVIDIA NIM endpoint."""

    @pytest.mark.asyncio
    async def test_nim_endpoint_responds(self):
        from openai import AsyncOpenAI
        from app.services.llm_client import clamp_max_tokens, extract_llm_text

        client = AsyncOpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.environ["NVIDIA_API_KEY"],
        )
        response = await client.chat.completions.create(
            model="moonshotai/kimi-k2.5",
            max_tokens=clamp_max_tokens(100),
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            temperature=1.0,
            top_p=1.0,
        )
        assert response.choices
        text = extract_llm_text(response.choices[0])
        assert len(text) > 0
