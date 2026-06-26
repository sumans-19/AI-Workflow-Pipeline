"""LLM cost tracking and budget management."""

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional

from ..exceptions import LLMBudgetExceeded

# Pricing: (provider, model) -> (prompt_price_per_1k, completion_price_per_1k) in USD
PRICING_TABLE: Dict[tuple, tuple] = {
    ("openai", "gpt-4o"): (0.0025, 0.01),
    ("openai", "gpt-4o-mini"): (0.00015, 0.0006),
    ("openai", "gpt-4.1"): (0.002, 0.008),
    ("openai", "gpt-4.1-mini"): (0.0004, 0.0016),
    ("openai", "gpt-4.1-nano"): (0.0001, 0.0004),
    ("gemini", "gemini-2.5-flash"): (0.00015, 0.0006),
    ("gemini", "gemini-2.5-pro"): (0.00125, 0.005),
}


@dataclass
class UsageRecord:
    """Single API call usage record."""

    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    timestamp: float


@dataclass
class CostTracker:
    """Accumulates LLM token usage and cost across a pipeline run."""

    records: List[UsageRecord] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    budget_limit_usd: Optional[float] = None
    _lock: Lock = field(default_factory=Lock)

    def record(
        self,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        cost = self._calculate_cost(model, provider, prompt_tokens, completion_tokens)
        total = prompt_tokens + completion_tokens
        rec = UsageRecord(
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            estimated_cost_usd=cost,
            timestamp=time.time(),
        )
        with self._lock:
            self.records.append(rec)
            self.total_cost_usd += cost
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens

        if self.budget_limit_usd and self.budget_limit_usd > 0 and self.total_cost_usd > self.budget_limit_usd:
            raise LLMBudgetExceeded(
                f"Budget exceeded: ${self.total_cost_usd:.6f} > ${self.budget_limit_usd:.6f}"
            )

    def _calculate_cost(
        self, model: str, provider: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        key = (provider, model)
        if key in PRICING_TABLE:
            prompt_price, completion_price = PRICING_TABLE[key]
            return (prompt_tokens / 1000 * prompt_price) + (
                completion_tokens / 1000 * completion_price
            )
        return 0.0

    def get_summary(self) -> Dict:
        with self._lock:
            by_model: Dict[str, Dict] = {}
            for rec in self.records:
                if rec.model not in by_model:
                    by_model[rec.model] = {
                        "calls": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "cost_usd": 0.0,
                    }
                entry = by_model[rec.model]
                entry["calls"] += 1
                entry["prompt_tokens"] += rec.prompt_tokens
                entry["completion_tokens"] += rec.completion_tokens
                entry["cost_usd"] += rec.estimated_cost_usd

            return {
                "total_cost_usd": round(self.total_cost_usd, 6),
                "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
                "total_prompt_tokens": self.total_prompt_tokens,
                "total_completion_tokens": self.total_completion_tokens,
                "calls": len(self.records),
                "by_model": by_model,
                "budget_limit_usd": self.budget_limit_usd,
            }

    def reset(self) -> None:
        with self._lock:
            self.records.clear()
            self.total_cost_usd = 0.0
            self.total_prompt_tokens = 0
            self.total_completion_tokens = 0
