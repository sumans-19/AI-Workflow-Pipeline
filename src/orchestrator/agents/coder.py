import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agents.base import BaseAgent
from ..core.context import FeedbackItem, WorkflowContext
from ..core.guardrails import evaluate_guardrails, should_block_guardrail
from ..exceptions import LLMError, LLMResponseParseError, GuardrailViolation
from ..llm.base import BaseLLMClient
from ..llm.openai_client import OpenAIClient
from ..logging_config import logger


class CoderAgent(BaseAgent):
    CODE_RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "source_code": {"type": "string"},
                        "chunks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "target": {"type": "string"},
                                    "replacement": {"type": "string"},
                                },
                                "required": ["target", "replacement"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["files", "summary"],
        "additionalProperties": False,
    }

    PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

    def __init__(self, llm: Optional[BaseLLMClient] = None):
        super().__init__(name="Coder Agent")
        self.llm = llm or OpenAIClient()
        self._prompt_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, context: WorkflowContext) -> WorkflowContext:
        logger.info("%s starting in %s mode...", self.name, context.mode)

        try:
            unresolved = context.unresolved_feedback()
            if unresolved:
                return self._fix_code(context, unresolved)
            elif context.is_project_mode:
                return self._generate_project(context)
            elif context.mode == "GENERATE":
                return self._generate_code(context)
            elif context.mode == "VALIDATE":
                return self._validate_code(context)
            elif context.mode == "HYBRID":
                return self._hybrid_code(context)
            else:
                context.success = False
                context.error_message = f"Unknown mode: {context.mode}"
                return context
        except LLMError as e:
            context.success = False
            context.error_message = f"[{self.name}] API Failed: {str(e)}"
            return context

    @staticmethod
    def apply_human_edit(context: WorkflowContext, filename: str, new_code: str) -> WorkflowContext:
        """Directly replace code with a human-provided version (no LLM call)."""
        context.snapshot_code()
        context.source_code[filename] = new_code
        for item in context.feedback_items:
            if not item.location or filename in item.location:
                item.resolved = True
        context.current_step = "CODE_EDITED_BY_HUMAN"
        context.success = True
        context.guardrail_warnings = []
        return context

    # ------------------------------------------------------------------
    # Project generation (full project scaffold)
    # ------------------------------------------------------------------

    def _generate_project(self, context: WorkflowContext) -> WorkflowContext:
        """Generate a full project scaffold with multiple interconnected files."""
        logger.info("%s generating full project: %s", self.name, context.project_name)
        system_prompt = self._load_prompt("project_generate.txt",
                                          project_name=context.project_name,
                                          project_type=context.project_type,
                                          requirements=context.requirements)
        user_prompt = (
            f"Project Name: {context.project_name}\n"
            f"Project Type: {context.project_type}\n"
            f"Requirements: {context.requirements}\n"
            "Create a complete project with proper package structure, "
            "interconnected modules, tests, and configuration files."
        )
        context.source_code = self._llm_code_request(system_prompt, user_prompt)
        context.current_step = "PROJECT_GENERATED"
        context.success = True
        return context

    # ------------------------------------------------------------------
    # Structured fix
    # ------------------------------------------------------------------

    def _fix_code(self, context: WorkflowContext, feedback_items: List[FeedbackItem]) -> WorkflowContext:
        logger.info("%s fixing code based on %d feedback items...", self.name, len(feedback_items))

        issue_list = self._format_feedback_for_prompt(feedback_items)
        system_prompt = self._load_prompt("coder_fix.txt", issue_list=issue_list)
        fixed_source_code: Dict[str, str] = {}

        files_to_fix = self._files_needing_fix(context, feedback_items)

        for filename, code in context.source_code.items():
            if filename not in files_to_fix:
                fixed_source_code[filename] = code
                continue

            user_prompt = (
                f"Target filename: {filename}\n"
                f"Current code:\n{code}\n"
                "Return JSON only."
            )
            parsed = self._llm_code_request(
                system_prompt, 
                user_prompt, 
                default_filename=filename,
                current_files={filename: code}
            )
            fixed_code = parsed.get(filename) or parsed.get(next(iter(parsed)))
            fixed_source_code[filename] = fixed_code

        context.snapshot_code()
        previous = context.previous_code()

        context.source_code = fixed_source_code

        context.guardrail_warnings = []
        if previous:
            for filename in files_to_fix:
                old = previous.get(filename, "")
                new = fixed_source_code.get(filename, "")
                if old and new:
                    result = evaluate_guardrails(old, new, feedback_items, filename)
                    context.guardrail_warnings.extend(result["warnings"])
                    context.guardrail_warnings.extend(result["violations"])
                    if should_block_guardrail(result["violations"]):
                        context.success = False
                        context.error_message = f"Guardrail blocked unsafe fix in {filename}"
                        return context

        for item in feedback_items:
            context.mark_feedback_resolved(item, note="Applied by coder agent")

        context.current_step = "CODE_FIXED"
        context.success = True
        return context

    # ------------------------------------------------------------------
    # Single-file generation modes
    # ------------------------------------------------------------------

    def _generate_code(self, context: WorkflowContext) -> WorkflowContext:
        system_prompt = self._load_prompt("coder_generate.txt")
        user_prompt = f"Requirements: {context.requirements}"
        context.source_code = self._llm_code_request(system_prompt, user_prompt)
        context.current_step = "CODE_GENERATED"
        context.success = True
        return context

    def _validate_code(self, context: WorkflowContext) -> WorkflowContext:
        new_source_code: Dict[str, str] = {}

        for filename, code in context.source_code.items():
            logger.info("%s validating %s...", self.name, filename)
            system_prompt = (
                "You are a Code Auditor. Add type hints and docstrings. "
                "Return JSON only with keys filename and source_code."
            )
            user_prompt = (
                f"Target filename: {filename}\n"
                f"Code:\n{code}"
            )
            parsed = self._llm_code_request(system_prompt, user_prompt, default_filename=filename)
            improved_code = parsed.get(filename) or parsed.get(next(iter(parsed)))
            new_source_code[filename] = improved_code

        context.source_code = new_source_code
        context.current_step = "CODE_GENERATED"
        context.success = True
        return context

    def _hybrid_code(self, context: WorkflowContext) -> WorkflowContext:
        new_source_code: Dict[str, str] = {}

        for filename, code in context.source_code.items():
            logger.info("%s completing %s...", self.name, filename)
            system_prompt = (
                "Complete the skeleton. Add type hints and docstrings. "
                "Return JSON only with keys filename and source_code."
            )
            user_prompt = (
                f"Target filename: {filename}\n"
                f"Skeleton:\n{code}\n"
                f"Requirements: {context.requirements}"
            )
            parsed = self._llm_code_request(system_prompt, user_prompt, default_filename=filename)
            completed_code = parsed.get(filename) or parsed.get(next(iter(parsed)))
            new_source_code[filename] = completed_code

        context.source_code = new_source_code
        context.current_step = "CODE_GENERATED"
        context.success = True
        return context

    # ------------------------------------------------------------------
    # Shared LLM call + parse helper
    # ------------------------------------------------------------------

    def _llm_code_request(
        self,
        system_prompt: str,
        user_prompt: str,
        default_filename: str = "main.py",
        syntax_retries: int = 1,
        current_files: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Single method that handles LLM call + parse for all generation modes."""
        raw_response = self.llm.generate(
            system_prompt,
            user_prompt,
            response_schema=self.CODE_RESPONSE_SCHEMA,
        )
        parsed = self._parse_structured_response(raw_response, default_filename, current_files)
        errors = self._validate_generated_python(parsed)
        if errors:
            if syntax_retries > 0:
                repaired = self._repair_python_syntax(parsed, errors)
                errors = self._validate_generated_python(repaired)
                if not errors:
                    return repaired
            raise LLMResponseParseError(self._format_syntax_error_message(errors))
        return parsed

    # ------------------------------------------------------------------
    # Other helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_feedback_for_prompt(items: List[FeedbackItem]) -> str:
        """Build a numbered issue list string for the LLM prompt."""
        lines = []
        for idx, item in enumerate(items, 1):
            loc = f" at {item.location}" if item.location else ""
            lines.append(f"{idx}. [{item.severity.upper()}]{loc}: {item.description}")
        return "\n".join(lines)

    @staticmethod
    def _files_needing_fix(context: WorkflowContext, items: List[FeedbackItem]) -> set:
        """Determine which files are referenced by feedback items."""
        filenames: set = set()
        for item in items:
            if item.location:
                for fn in context.source_code:
                    if fn in item.location:
                        filenames.add(fn)
                        break
        if not filenames:
            filenames = set(context.source_code.keys())
        return filenames

    def _load_prompt(self, prompt_name: str, **kwargs) -> str:
        if prompt_name not in self._prompt_cache:
            prompt_path = self.PROMPTS_DIR / prompt_name
            try:
                self._prompt_cache[prompt_name] = prompt_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise LLMError(f"Prompt file unavailable: {prompt_path} ({exc})") from exc
        content = self._prompt_cache[prompt_name]
        return content.format(**kwargs) if kwargs else content

    def _repair_python_syntax(
        self,
        files: Dict[str, str],
        errors: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        targets = {err["filename"] for err in errors}
        repair_targets = {name: files[name] for name in targets if name in files}
        if not repair_targets:
            return files

        system_prompt = (
            "You are a Python syntax repair assistant. Fix syntax errors only. "
            "Return JSON with a files array, each item containing path and source_code. "
            "Do not add new files or change behavior beyond syntax fixes."
        )

        error_lines = []
        for err in errors:
            line = err.get("line")
            col = err.get("column")
            msg = err.get("message")
            error_lines.append(f"- {err['filename']}: {msg} (line {line}, column {col})")
        user_prompt = "Syntax errors:\n" + "\n".join(error_lines)

        for filename, source_code in repair_targets.items():
            user_prompt += f"\n\nFile: {filename}\n```python\n{source_code}\n```"

        raw_response = self.llm.generate(
            system_prompt,
            user_prompt,
            response_schema=self.CODE_RESPONSE_SCHEMA,
        )
        repaired = self._parse_structured_response(
            raw_response,
            default_filename=next(iter(repair_targets)),
        )

        merged = dict(files)
        for filename, source_code in repaired.items():
            merged[filename] = source_code
        return merged

    @staticmethod
    def _format_syntax_error_message(errors: List[Dict[str, Any]]) -> str:
        preview = errors[:3]
        details = "; ".join(
            f"{err['filename']}: {err.get('message')} (line {err.get('line')}, column {err.get('column')})"
            for err in preview
        )
        if len(errors) > 3:
            details += f"; ... ({len(errors) - 3} more)"
        return f"Generated Python is syntactically invalid after repair: {details}."

    @staticmethod
    def _validate_generated_python(files: Dict[str, str]) -> List[Dict[str, Any]]:
        errors: List[Dict[str, Any]] = []
        for filename, source_code in files.items():
            if Path(filename).suffix != ".py":
                continue
            try:
                ast.parse(source_code)
            except SyntaxError as exc:
                errors.append({
                    "filename": filename,
                    "message": exc.msg,
                    "line": exc.lineno,
                    "column": exc.offset,
                })
        return errors

    @staticmethod
    def _parse_structured_response(
        raw_response: str,
        default_filename: str = "main.py",
        current_files: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        # Strip markdown code fences that some models wrap around JSON
        cleaned = raw_response.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```\s*$', '', cleaned)

        payload = None
        last_error = None

        # Attempt 1: Parse cleaned response directly
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning("Initial JSON parse failed: %s. Attempting repair...", exc)

        # Attempt 2: Try to repair truncated JSON
        if payload is None:
            try:
                repaired = OpenAIClient._try_repair_json(cleaned)
                payload = json.loads(repaired)
                logger.info("JSON repair succeeded.")
            except json.JSONDecodeError as exc:
                last_error = exc

        if payload is None:
            raise LLMResponseParseError(
                f"Invalid JSON response from model: {last_error}. "
                "This is likely caused by the response being truncated due to "
                "output token limits. Try simplifying your requirements or "
                "splitting the project into smaller parts."
            )

        files = payload.get("files")
        if not isinstance(files, list) or not files:
            filename = payload.get("filename", default_filename)
            source_code = payload.get("source_code", "")
            if not isinstance(source_code, str) or not source_code.strip():
                raise LLMResponseParseError("Model response missing non-empty source code.")
            return {str(filename).strip(): source_code}

        parsed: Dict[str, str] = {}
        for item in files:
            path = item.get("path", default_filename)
            if not isinstance(path, str) or not path.strip():
                path = default_filename
            path = path.strip()

            chunks = item.get("chunks")
            if chunks and current_files and path in current_files:
                patched_code = current_files[path]
                for chunk in chunks:
                    target = chunk.get("target", "")
                    replacement = chunk.get("replacement", "")
                    
                    if target and target in patched_code:
                        patched_code = patched_code.replace(target, replacement)
                    elif target:
                        logger.warning("Failed to apply patch chunk in %s. Exact target not found.", path)
                parsed[path] = patched_code
            else:
                source_code = item.get("source_code", "")
                if isinstance(source_code, str) and source_code.strip():
                    parsed[path] = source_code

        if not parsed:
            raise LLMResponseParseError("Model response contained no valid files.")
        return parsed
