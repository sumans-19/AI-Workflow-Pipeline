"""Planning Agent — the first stage of the orchestration pipeline.

Generates a structured implementation blueprint for the downstream Coder,
Tester, Reviewer, and Validator agents. The user chooses which of the 15
planning modules to include via the Planning Configuration UI, and only
those modules are requested from the LLM.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agents.base import BaseAgent
from ..core.context import WorkflowContext
from ..exceptions import LLMError, LLMResponseParseError
from ..llm.base import BaseLLMClient
from ..llm.openai_client import OpenAIClient
from ..logging_config import logger
from .planning_models import (
    PLANNING_MODULES,
    PlanningDocument,
    parse_plan_from_dict,
)


# ─────────────────────────────────────────────────────────────
# JSON Schema for the LLM response (forces only selected keys)
# ─────────────────────────────────────────────────────────────

def _build_response_schema(selected_ids: List[str]) -> Dict[str, Any]:
    """Build an OpenAI-style JSON schema that ONLY allows the selected modules.

    Every module is typed as `object` with `additionalProperties: True` so the
    model can include extra fields, but it MUST be a JSON object — never a
    string or array. This is what prevents the LLM from echoing back the
    schema description verbatim as a string value.
    """
    module_properties: Dict[str, Any] = {}
    required: List[str] = []
    for mod in PLANNING_MODULES:
        if mod["id"] not in selected_ids:
            continue
        mid = mod["id"]
        required.append(mid)
        module_properties[mid] = {
            "type": "object",
            "additionalProperties": True,
        }
    return {
        "type": "object",
        "properties": module_properties,
        "required": required,
        "additionalProperties": False,
    }


# ─────────────────────────────────────────────────────────────
# The agent
# ─────────────────────────────────────────────────────────────

class PlanningAgent(BaseAgent):
    """First-class planning agent that produces an implementation blueprint."""

    PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

    def __init__(self, llm: Optional[BaseLLMClient] = None):
        super().__init__(name="Planning Agent")
        self.llm = llm or OpenAIClient()
        self._prompt_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, context: WorkflowContext) -> WorkflowContext:
        """Generate the plan for the modules selected on the context."""
        logger.info("%s starting for run_id=%s", self.name, context.run_id)

        modules = context.planning_modules or {}
        selected = [m for m in PLANNING_MODULES if modules.get(m["id"], False)]

        if not selected:
            # Nothing to plan — emit a stub doc so downstream stages can still
            # see a `context.plan` exists.
            logger.warning("%s invoked with no modules selected — emitting empty plan", self.name)
            context.plan = PlanningDocument(requirements=context.requirements)
            context.plan.generated_at = time.time()
            context.current_step = "PLAN_EMPTY"
            context.success = True
            return context

        selected_ids = [m["id"] for m in selected]
        logger.info("%s generating %d modules: %s", self.name, len(selected), ", ".join(selected_ids))

        try:
            if context.emit_event:
                context.emit_event("agent_started", {
                    "agent": "planner",
                    "modules": selected_ids,
                    "message": "Planning Agent is analyzing your requirements…",
                })

            system_prompt, user_prompt = self._build_prompts(selected, context.requirements)

            raw_response = self.llm.generate(
                system_prompt,
                user_prompt,
                response_schema=_build_response_schema(selected_ids),
            )

            payload = self._parse_response(raw_response, selected_ids)
            doc = parse_plan_from_dict(payload, requirements=context.requirements)
            doc.generated_at = time.time()
            context.plan = doc
            context.current_step = "PLAN_GENERATED"
            context.success = True

            logger.info(
                "%s generated plan with modules: %s",
                self.name, ", ".join(doc.selected_module_ids()),
            )

            if context.emit_event:
                context.emit_event("agent_completed", {
                    "agent": "planner",
                    "modules_generated": doc.selected_module_ids(),
                    "plan_summary": doc.to_dict(),
                    "message": f"Planning Agent generated {len(doc.selected_module_ids())} module(s).",
                })

            return context

        except LLMError as e:
            logger.error("%s API failure: %s", self.name, e)
            context.success = False
            context.error_message = f"[{self.name}] API Failed: {str(e)}"
            if context.emit_event:
                context.emit_event("agent_failed", {
                    "agent": "planner",
                    "message": context.error_message,
                })
            return context
        except LLMResponseParseError as e:
            logger.error("%s parse failure: %s", self.name, e)
            context.success = False
            context.error_message = f"[{self.name}] Could not parse plan: {str(e)}"
            if context.emit_event:
                context.emit_event("agent_failed", {
                    "agent": "planner",
                    "message": context.error_message,
                })
            return context

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompts(self, selected: List[Dict[str, str]], requirements: str) -> tuple[str, str]:
        template = self._load_prompt("planning_generate.txt")
        selected_listing = "\n".join(f"- `{m['id']}` → {m['label']}: {m['description']}"
                                     for m in selected)
        # Use plain .replace() instead of .format() so literal `{` and `}` in
        # the prompt (the example JSON output) are not interpreted as format
        # placeholders.
        user_prompt = (template
            .replace("{requirements}", requirements or "(no requirements provided)")
            .replace("{selected_modules}", selected_listing))
        # The system prompt is the template — return it AND the formatted user prompt.
        # We return the template as the system prompt to set role, and the
        # formatted version as the user prompt to feed the data.
        return ("You are a senior software architect. Always output strict JSON only.", user_prompt)

    def _load_prompt(self, prompt_name: str) -> str:
        if prompt_name not in self._prompt_cache:
            prompt_path = self.PROMPTS_DIR / prompt_name
            try:
                self._prompt_cache[prompt_name] = prompt_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise LLMError(f"Prompt file unavailable: {prompt_path} ({exc})") from exc
        return self._prompt_cache[prompt_name]

    @staticmethod
    def _parse_response(raw: str, expected_keys: List[str]) -> Dict[str, Any]:
        """Parse the LLM JSON response, tolerating fences and minor errors."""
        cleaned = raw.strip()
        # Strip markdown fences if the model wrapped its answer.
        cleaned = re.sub(r"^```(?:json|JSON)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

        # If the model echoed back the schema description verbatim (or returned
        # an obviously non-JSON string), short-circuit early with an empty dict.
        if cleaned and cleaned[0] not in "{[":
            return {}

        payload: Optional[Dict[str, Any]] = None
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try OpenAIClient's repair helper.
            try:
                repaired = OpenAIClient._try_repair_json(cleaned)
                payload = json.loads(repaired)
            except Exception:
                # Last resort: try to extract any JSON object.
                m = re.search(r"\{[\s\S]*\}", cleaned)
                if m:
                    try:
                        payload = json.loads(m.group(0))
                    except Exception as e:
                        raise LLMResponseParseError(
                            f"Planning Agent returned non-JSON output: {e}"
                        ) from e
                else:
                    raise LLMResponseParseError(
                        "Planning Agent returned no JSON object."
                    )

        # The LLM occasionally wraps the dict in a list (e.g. `[ {...} ]`).
        # Unwrap one level before validating the type.
        if isinstance(payload, list):
            if len(payload) == 1 and isinstance(payload[0], dict):
                payload = payload[0]
            else:
                # Treat each list element as a candidate module dict.
                merged: Dict[str, Any] = {}
                for item in payload:
                    if isinstance(item, dict):
                        merged.update(item)
                payload = merged if merged else {}

        if not isinstance(payload, dict):
            raise LLMResponseParseError("Planning Agent JSON root is not an object.")

        # Drop any unexpected top-level keys (we only asked for the selected ones).
        for k in list(payload.keys()):
            if k not in expected_keys:
                payload.pop(k, None)

        return payload
