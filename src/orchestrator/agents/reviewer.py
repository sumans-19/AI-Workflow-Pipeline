import os
import re
import subprocess
import json
from pathlib import Path
from typing import Optional

from ..agents.base import BaseAgent
from ..core.context import FeedbackItem, WorkflowContext
from ..exceptions import LLMError
from ..llm.base import BaseLLMClient
from ..llm.openai_client import OpenAIClient
from ..logging_config import logger


class ReviewerAgent(BaseAgent):
    PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

    def __init__(self, llm: Optional[BaseLLMClient] = None):
        super().__init__(name="Reviewer Agent")
        self.llm = llm or OpenAIClient()
        self._prompt_cache: dict = {}

    def execute(self, context: WorkflowContext) -> WorkflowContext:
        logger.info("%s analyzing code...", self.name)

        if not context.source_code:
            context.success = False
            return context

        all_issues: list[dict] = []
        total_score = 0.0
        security_issues = 0
        review_feedback: list[FeedbackItem] = []

        for filename, code in context.source_code.items():
            report, items, parsed_dicts = self._review_code(filename, code)
            all_issues.extend(parsed_dicts)
            review_feedback.extend(items)

            score, sec_count, pylint_items = self._run_pylint(filename, context.workspace_path)
            total_score += score
            security_issues += sec_count
            review_feedback.extend(pylint_items)

        context.review_issues = all_issues

        context.feedback_items = [
            f for f in context.feedback_items
            if f.source != "reviewer"
        ]
        context.feedback_items.extend(review_feedback)

        avg_score = total_score / len(context.source_code) if context.source_code else 0

        context.metrics['pylint_score'] = avg_score
        context.metrics['security_issues'] = security_issues
        context.metrics['loc'] = sum(len(c.splitlines()) for c in context.source_code.values())

        context.success = True
        return context

    # ------------------------------------------------------------------
    # Pylint analysis
    # ------------------------------------------------------------------

    def _run_pylint(self, filename, workspace_path: str):
        try:
            file_path = os.path.join(workspace_path, filename)

            result = subprocess.run(
                ["pylint", file_path, "--output-format=text", "--disable=C0114"],
                capture_output=True,
                text=True,
                timeout=30
            )

            output = result.stdout + result.stderr

            score = 0.0
            score_match = re.search(r"rated at ([\d\.]+)", output)
            if score_match:
                score = float(score_match.group(1))
            else:
                score = 8.0

            items: list[FeedbackItem] = []
            for match in re.finditer(
                r"^.*?:(\d+):\d+:\s*([CRWEF]\d+):\s*(.+?)(?:\s*\(.*\))?\s*$",
                output,
                re.MULTILINE,
            ):
                line_no = match.group(1)
                code = match.group(2)
                message = match.group(3).strip()

                if code.startswith("E") or code.startswith("F"):
                    severity = "critical"
                elif code.startswith("W"):
                    severity = "major"
                elif code.startswith("C"):
                    severity = "minor"
                else:
                    severity = "suggestion"

                items.append(FeedbackItem(
                    source="reviewer",
                    severity=severity,
                    description=f"[{code}] {message}",
                    location=f"{filename}:L{line_no}",
                    action="fix",
                ))

            sec_count = len(re.findall(r"^[WE]:", output, re.MULTILINE))

            return score, sec_count, items

        except Exception as e:
            logger.warning("Pylint error for %s: %s", filename, e)
            return 8.0, 0, []

    # ------------------------------------------------------------------
    # LLM semantic review
    # ------------------------------------------------------------------

    def _review_code(self, filename: str, code: str) -> tuple:
        system_prompt = self._load_prompt("reviewer_analyze.txt")
        user_prompt = f"File: {filename}\nCode:\n```python\n{code}\n```"
        raw_report = self.llm.generate(system_prompt, user_prompt)

        items, parsed_dicts = self._parse_review_to_feedback(raw_report, filename)
        return raw_report, items, parsed_dicts

    def _load_prompt(self, prompt_name: str) -> str:
        if prompt_name not in self._prompt_cache:
            prompt_path = self.PROMPTS_DIR / prompt_name
            try:
                self._prompt_cache[prompt_name] = prompt_path.read_text(encoding="utf-8")
            except OSError:
                return "You are a strict code reviewer. Return JSON with an issues array."
        return self._prompt_cache[prompt_name]

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Strip markdown code fences (```json ... ```) from LLM output."""
        text = text.strip()
        fence_pattern = re.compile(r"```(?:json|JSON|python|PYTHON)?\s*\n?(.*?)\n?```", re.DOTALL)
        match = fence_pattern.search(text)
        if match:
            return match.group(1).strip()
        return text

    @staticmethod
    def _parse_review_to_feedback(report: str, filename: str) -> tuple:
        """Parse LLM review output into (FeedbackItems, parsed_dicts).

        Strips markdown code fences first. Returns parsed issue dicts so the
        UI can render structured issue cards instead of raw fenced JSON.
        """
        items: list[FeedbackItem] = []
        parsed_dicts: list[dict] = []

        cleaned = ReviewerAgent._strip_markdown_fences(report)

        payload = None
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find a JSON object or array within the text
            obj_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            arr_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            candidate = obj_match.group(0) if obj_match else (arr_match.group(0) if arr_match else None)
            if candidate:
                try:
                    payload = json.loads(candidate)
                except json.JSONDecodeError:
                    payload = None

        if isinstance(payload, dict):
            raw_issues = payload.get("issues", [])
        elif isinstance(payload, list):
            raw_issues = payload
        else:
            raw_issues = []

        for issue in raw_issues:
            if not isinstance(issue, dict):
                continue
            severity = issue.get("severity", "major").lower()
            description = issue.get("problem", "").strip()
            location_raw = issue.get("location", "").strip()
            if not description:
                continue
            location = f"{filename}:{location_raw}" if location_raw else filename
            items.append(FeedbackItem(
                source="reviewer",
                severity=severity,
                category=issue.get("category", "style"),
                description=description,
                location=location,
                file_path=filename,
                action="fix",
                author="reviewer",
            ))
            parsed_dicts.append({
                "severity": severity,
                "category": issue.get("category", "style"),
                "location": location,
                "file": filename,
                "title": issue.get("title") or description.split(".")[0][:80],
                "description": description,
            })

        return items, parsed_dicts
