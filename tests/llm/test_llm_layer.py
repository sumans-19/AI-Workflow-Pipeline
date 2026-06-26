"""Tests for the LLM abstraction layer (US-001)."""

import time
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.exceptions import (
    ConfigurationError,
    LLMBudgetExceeded,
    LLMError,
)
from orchestrator.llm.cost_tracker import CostTracker, PRICING_TABLE
from orchestrator.llm.factory import create_llm_client

# ===================================================================
# OpenAIClient (Generic LLM Client) tests
# ===================================================================

class TestOpenAIClient:
    def test_init_missing_api_key(self, monkeypatch):
        from orchestrator.config import Settings
        monkeypatch.setattr(Settings, "LLM_API_KEY", "")
        from orchestrator.llm.openai_client import OpenAIClient

        with pytest.raises(ConfigurationError, match="LLM_API_KEY"):
            OpenAIClient()

    def test_init_success(self, mock_llm_env):
        with patch("orchestrator.llm.openai_client.OpenAI"):
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            assert client._provider_name == "llm_provider"
            assert client.model == "test-model"

    def test_generate_success(self, mock_llm_env):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"result": "hello"}'
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 10

        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.chat.completions.create.return_value = mock_response
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            result = client.generate("system", "user")
            assert '"result": "hello"' in result

    def test_generate_with_schema(self, mock_llm_env):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"files": []}'
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 20

        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI:
            mock_create = MockOpenAI.return_value.chat.completions.create
            mock_create.return_value = mock_response
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            result = client.generate("sys", "usr", response_schema={"type": "object"})
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["response_format"] == {"type": "json_object"}
            assert "max_tokens" in call_kwargs

    def test_rate_limit_retry(self, mock_llm_env):
        from openai import RateLimitError

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI, \
             patch("orchestrator.llm.openai_client.time.sleep") as mock_sleep:
            mock_create = MockOpenAI.return_value.chat.completions.create
            mock_create.side_effect = [RateLimitError("limit", response=MagicMock(), body=None), mock_response]
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            result = client.generate("sys", "usr", max_retries=3)
            assert result == "ok"
            mock_sleep.assert_called_once()

    def test_max_retries_exhausted(self, mock_llm_env):
        from openai import RateLimitError

        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI, \
             patch("orchestrator.llm.openai_client.time.sleep"):
            mock_create = MockOpenAI.return_value.chat.completions.create
            mock_create.side_effect = RateLimitError("limit", response=MagicMock(), body=None)
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            with pytest.raises(LLMError, match="Max retries"):
                client.generate("sys", "usr", max_retries=2)

    def test_api_error_raised(self, mock_llm_env):
        from openai import APIError

        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI:
            mock_create = MockOpenAI.return_value.chat.completions.create
            mock_create.side_effect = APIError("fail", request=MagicMock(), body=None)
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            with pytest.raises(LLMError, match="API Error"):
                client.generate("sys", "usr")

    def test_sanitize_control_chars(self, mock_llm_env):
        from orchestrator.llm.openai_client import OpenAIClient

        assert OpenAIClient._sanitize("hello<ctrl1>world") == "helloworld"
        assert OpenAIClient._sanitize("clean") == "clean"

    def test_reports_usage_to_cost_tracker(self, mock_llm_env, cost_tracker):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50

        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.chat.completions.create.return_value = mock_response
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            client.set_cost_tracker(cost_tracker)
            client.generate("sys", "usr")

            summary = cost_tracker.get_summary()
            assert summary["calls"] == 1
            assert summary["total_prompt_tokens"] == 100
            assert summary["total_completion_tokens"] == 50

    def test_json_repair_logic(self, mock_llm_env):
        from orchestrator.llm.openai_client import OpenAIClient
        # The logic is aggressive: it removes the last incomplete object entirely.
        # Case 1: Truncated string in value -> Deletes the object if it's the only one
        assert OpenAIClient._try_repair_json('{"key": "value') == ''
        # Case 2: Truncated second object -> Keeps the first one
        assert OpenAIClient._try_repair_json('{"a": 1}, {"b": 2') == '{"a": 1}'
        # Case 3: Truncated array in object -> Deletes the object if it's the only one
        assert OpenAIClient._try_repair_json('{"list": [1, 2') == ''

    def test_generate_truncated_response_repair(self, mock_llm_env):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        # Truncated path object inside list
        mock_response.choices[0].message.content = '{"files": [{"path": "main.py"'
        mock_response.choices[0].finish_reason = "length"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 50

        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.chat.completions.create.return_value = mock_response
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            result = client.generate("sys", "usr", response_schema={"type": "object"})
            # Should have been repaired by removing the partial object
            assert result == '{"files": []}'

    def test_transient_error_retry_timeout(self, mock_llm_env):
        from openai import APITimeoutError
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        
        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI, \
             patch("orchestrator.llm.openai_client.time.sleep"):
            mock_create = MockOpenAI.return_value.chat.completions.create
            mock_create.side_effect = [APITimeoutError(request=MagicMock()), mock_response]
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            result = client.generate("sys", "usr")
            assert result == "ok"
            assert mock_create.call_count == 2

    def test_unexpected_exception_handling(self, mock_llm_env):
        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI:
            mock_create = MockOpenAI.return_value.chat.completions.create
            mock_create.side_effect = Exception("Critical System Failure")
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            with pytest.raises(LLMError, match="Unexpected LLM error"):
                client.generate("sys", "usr")

    def test_max_retries_reached_exhaustion(self, mock_llm_env):
        from openai import RateLimitError
        with patch("orchestrator.llm.openai_client.OpenAI") as MockOpenAI, \
             patch("orchestrator.llm.openai_client.time.sleep"):
            mock_create = MockOpenAI.return_value.chat.completions.create
            mock_create.side_effect = RateLimitError("limit", response=MagicMock(), body=None)
            from orchestrator.llm.openai_client import OpenAIClient

            client = OpenAIClient()
            with pytest.raises(LLMError, match="Max retries reached"):
                client.generate("sys", "usr", max_retries=2)


# ===================================================================
# CostTracker tests
# ===================================================================

class TestCostTracker:
    def test_record_single_call(self, cost_tracker):
        cost_tracker.record("gpt-4o-mini", "openai", 100, 50)
        summary = cost_tracker.get_summary()
        assert summary["calls"] == 1
        assert summary["total_prompt_tokens"] == 100
        assert summary["total_completion_tokens"] == 50
        assert summary["total_tokens"] == 150

    def test_record_accumulates(self, cost_tracker):
        cost_tracker.record("gpt-4o-mini", "openai", 100, 50)
        cost_tracker.record("gemini-1.5-flash", "llm_provider", 200, 80)
        summary = cost_tracker.get_summary()
        assert summary["calls"] == 2
        assert summary["total_prompt_tokens"] == 300
        assert summary["total_completion_tokens"] == 130

    def test_cost_calculation(self, cost_tracker):
        cost_tracker.record("gpt-4o-mini", "openai", 1000, 1000)
        summary = cost_tracker.get_summary()
        expected = (1000 / 1000 * 0.00015) + (1000 / 1000 * 0.0006)
        assert abs(summary["total_cost_usd"] - expected) < 1e-10

    def test_unknown_model_zero_cost(self, cost_tracker):
        cost_tracker.record("unknown-model", "unknown", 1000, 1000)
        summary = cost_tracker.get_summary()
        assert summary["total_cost_usd"] == 0.0

    def test_budget_exceeded(self):
        tracker = CostTracker(budget_limit_usd=0.00001)
        with pytest.raises(LLMBudgetExceeded, match="Budget exceeded"):
            tracker.record("gpt-4o", "openai", 10000, 10000)

    def test_get_summary_format(self, cost_tracker):
        cost_tracker.record("gpt-4o-mini", "openai", 100, 50)
        summary = cost_tracker.get_summary()
        assert "total_cost_usd" in summary
        assert "total_tokens" in summary
        assert "calls" in summary
        assert "by_model" in summary
        assert "gpt-4o-mini" in summary["by_model"]
        assert summary["by_model"]["gpt-4o-mini"]["calls"] == 1

    def test_reset_clears_records(self, cost_tracker):
        cost_tracker.record("gpt-4o-mini", "openai", 100, 50)
        cost_tracker.reset()
        summary = cost_tracker.get_summary()
        assert summary["calls"] == 0
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_prompt_tokens"] == 0

    def test_no_budget_when_zero(self):
        tracker = CostTracker(budget_limit_usd=0)
        tracker.record("gpt-4o", "openai", 10000, 10000)  # Should not raise


# ===================================================================
# ClientFactory tests
# ===================================================================

class TestClientFactory:
    def test_create_llm_client(self, mock_llm_env):
        with patch("orchestrator.llm.factory.OpenAIClient") as MockOpenAI:
            instance = MagicMock()
            MockOpenAI.return_value = instance
            client = create_llm_client()
            assert client is instance
            MockOpenAI.assert_called_once()

    def test_cost_tracker_attached(self, mock_llm_env, cost_tracker):
        with patch("orchestrator.llm.factory.OpenAIClient") as MockOpenAI:
            instance = MagicMock()
            MockOpenAI.return_value = instance
            create_llm_client(cost_tracker=cost_tracker)
            instance.set_cost_tracker.assert_called_once_with(cost_tracker)
