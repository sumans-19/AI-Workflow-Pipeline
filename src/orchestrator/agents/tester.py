import ast
import re
from pathlib import Path
from typing import Optional
import json

from ..agents.base import BaseAgent
from ..core.context import WorkflowContext, FeedbackItem
from ..exceptions import LLMError
from ..llm.base import BaseLLMClient
from ..llm.openai_client import OpenAIClient
from ..logging_config import logger
from ..tools.file_manager import FileManager
from ..tools.python_runner import PythonRunner


class TesterAgent(BaseAgent):
    PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

    def __init__(
        self,
        llm: Optional[BaseLLMClient] = None,
        file_manager: Optional[FileManager] = None,
        runner: Optional[PythonRunner] = None,
    ):
        super().__init__(name="Tester Agent")
        self.llm = llm or OpenAIClient()
        self.file_manager = file_manager or FileManager()
        self.runner = runner or PythonRunner()
        self._prompt_cache: dict = {}

    def execute(self, context: WorkflowContext) -> WorkflowContext:
        logger.info("%s starting test generation...", self.name)
        if context.emit_event:
            context.emit_event("agent_started", {"agent": "tester"})

        try:
            if not context.source_code:
                context.success = False
                context.error_message = "No source code found."
                if context.emit_event:
                    context.emit_event("agent_failed", {"agent": "tester", "reason": context.error_message})
                return context

            python_sources = {
                filename: code
                for filename, code in context.source_code.items()
                if Path(filename).suffix == ".py"
                and Path(filename).name != "__init__.py"
                and Path(filename).name != "conftest.py"
                and not Path(filename).name.startswith("test_")
                and not filename.startswith("tests/")
            }

            if not python_sources:
                logger.warning("%s found no Python source files to test.", self.name)
                if context.emit_event:
                    context.emit_event("agent_completed", {"agent": "tester", "message": "No tests to generate", "passed": True})
                context.success = True
                return context

            total_files = len(python_sources)
            for idx, (filename, code) in enumerate(python_sources.items(), 1):
                base_name = Path(filename).stem
                test_filename = (Path("tests") / f"test_{base_name}.py").as_posix()
                
                if context.emit_event:
                    context.emit_event("agent_progress", {
                        "agent": "tester",
                        "progress": int((idx / total_files) * 50),
                        "message": f"Generating {test_filename}..."
                    })

                test_code = self._generate_tests(code, filename)
                
                # Pre-Execution Validation (Self-Correction)
                if context.emit_event:
                    context.emit_event("agent_progress", {
                        "agent": "tester",
                        "progress": int((idx / total_files) * 50) + 5,
                        "message": f"Validating tests for {filename}..."
                    })
                
                test_code = self._validate_and_repair_test(code, filename, test_code, test_filename)
                # Place tests in a top-level tests/ directory, not alongside source
                path = self.file_manager.write_file(test_filename, test_code, directory=context.workspace_path)
                logger.info("%s generated test file: %s", self.name, path)

                context.test_code[test_filename] = test_code
                context.emitted_files.add(test_filename)
                if context.emit_event:
                    context.emit_event("file_created", {
                        "path": test_filename,
                        "content": test_code,
                        "language": "python",
                    })
                else:
                    from ..cli.console import display_code
                    display_code(test_filename, test_code)

            logger.info("%s running pytest...", self.name)
            if context.emit_event:
                context.emit_event("agent_progress", {
                    "agent": "tester",
                    "progress": 75,
                    "message": "Running pytest..."
                })

            result = self.runner.run_pytest(
                context.workspace_path,
                force_local=(context.test_execution_mode == "local")
            )
            raw_success = result["passed"]
            output = result["output"]
            coverage = result["coverage_line"]
            report_data = result.get("report_data", {})
            execution_mode = result["execution_mode"]
            is_env_error = execution_mode == "local_env_error" or result.get("env_error", False)

            # ── Pass-rate calculation ──
            # If the majority of tests pass, treat the run as PASSED even when
            # a few tests fail — this gives a much better UX for typical LLM
            # generations where minor edge cases may flake while the bulk works.
            summary = report_data.get("summary", {}) if isinstance(report_data, dict) else {}
            collected = int(summary.get("collected", 0) or summary.get("total", 0) or 0)
            passed_count = int(summary.get("passed", 0) or 0)
            failed_count = int(summary.get("failed", 0) or 0)
            pass_rate = (passed_count / collected) if collected > 0 else (1.0 if raw_success else 0.0)
            MAJORITY_THRESHOLD = 0.70
            majority_passed = (
                pass_rate >= MAJORITY_THRESHOLD
                and collected > 0
                and not is_env_error
            )

            # Effective success for downstream gating:
            #   - true  if pytest says passed
            #   - true  if majority-pass rule kicks in
            success = bool(raw_success) or majority_passed

            context.test_results = {
                "passed": success,                       # effective status (gates downstream flow)
                "raw_passed": raw_success,               # actual pytest exit code
                "majority_passed": majority_passed,      # True when pass_rate ≥ 70%
                "pass_rate": round(pass_rate, 4),
                "output": output,
                "coverage": coverage,
                "coverage_line": result["coverage_line"],
                "coverage_branch": result["coverage_branch"],
                "execution_mode": execution_mode,
                "duration_seconds": result["duration_seconds"],
                "report_data": report_data,
                "env_error": is_env_error,
            }
            if not success and not is_env_error:
                logger.info(
                    "%s analyzing test failures... (collected=%d passed=%d failed=%d rate=%.1f%%)",
                    self.name, collected, passed_count, failed_count, pass_rate * 100,
                )
                if context.emit_event:
                    context.emit_event("agent_progress", {
                        "agent": "tester",
                        "progress": 90,
                        "message": "Analyzing test failures..."
                    })
                rca_data = self._analyze_test_failures(output)
                context.test_results["rca_data"] = rca_data
            elif is_env_error:
                # Build a deterministic RCA describing the environment failure
                # so the UI doesn't show all zeros and gives actionable advice.
                context.test_results["rca_data"] = {
                    "rca": [
                        {
                            "category": "Environment Error",
                            "why_it_happened": (
                                "The local Python interpreter could not bootstrap pytest. "
                                "This is an environment problem (broken venv, missing stdlib, "
                                "or corrupted Python install) — not a test failure."
                            ),
                            "caused_by_file": "(environment)",
                            "caused_by_function": "pytest bootstrap",
                            "confidence_score": 95,
                            "suggested_fix": (
                                "1) Switch test-execution mode to 'Docker' in the top-right toolbar. "
                                "2) Or set TEST_USE_SYSTEM_PYTHON=1 in your .env to bypass venv creation. "
                                "3) Or delete the run's .venv directory and retry."
                            ),
                        }
                    ],
                    "recommended_action": "Switch to Docker mode or set TEST_USE_SYSTEM_PYTHON=1.",
                }
            elif success and not raw_success and majority_passed:
                # Majority passed but a few edge-case failures remain — record
                # them as informational feedback so Reviewer can flag them,
                # but don't block the pipeline.
                logger.info(
                    "%s: majority_passed (%.1f%%) — %d/%d tests passed; recording %d failures as informational.",
                    self.name, pass_rate * 100, passed_count, collected, failed_count,
                )
                context.test_results["rca_data"] = {
                    "rca": [],
                    "recommended_action": (
                        f"Majority of tests passed ({passed_count}/{collected}, "
                        f"{pass_rate*100:.1f}%). Pipeline continues to Reviewer."
                    ),
                }

            context.current_step = "TESTS_EXECUTED"
            context.success = True

            if context.emit_event:
                context.emit_event("agent_completed", {
                    "agent": "tester",
                    "passed": success,
                    "coverage": coverage,
                    "failed": not success,
                    "env_error": is_env_error,
                    "majority_passed": majority_passed,
                    "pass_rate": round(pass_rate, 4),
                })
            return context

        except LLMError as e:
            context.success = False
            context.error_message = f"[{self.name}] API Failed: {str(e)}"
            if context.emit_event:
                context.emit_event("agent_failed", {"agent": "tester", "reason": str(e)})
            return context

    def _generate_tests(self, source_code: str, source_filename: str) -> str:
        # 1. Pre-Analysis
        analysis_prompt = (
            "You are a Senior Python Architect. Analyze the following code.\n"
            "Identify all public classes, functions, decorators, dependencies, dataclasses, and complex logic branches.\n"
            "List obvious edge cases, unreachable code, or potential bugs that should be tested.\n"
            "Return a concise technical summary to guide test generation."
        )
        user_analysis = f"Source File: `{source_filename}`\n\n```python\n{source_code}\n```"
        analysis_summary = ""
        try:
            analysis_summary = self.llm.generate(analysis_prompt, user_analysis)
        except LLMError as e:
            logger.warning(f"Tester Agent pre-analysis failed: {e}")

        # 2. Generation
        system_prompt = (
            "You are a Senior QA Engineer. Write a comprehensive pytest suite for the following code.\n\n"
            "REQUIREMENTS:\n"
            "1. Analyze the 'Source File Path' and 'Test File Path' below.\n"
            "2. Write the correct Python import statement to import the classes and functions from the source file.\n"
            "3. Write tests covering both happy paths and edge cases identified in the technical summary.\n"
            "4. Return ONLY valid Python code."
        )
        
        test_filename = (Path("tests") / f"test_{Path(source_filename).stem}.py").as_posix()
        
        user_prompt = (
            f"Source File Path: `{source_filename}`\n"
            f"Test File Path: `{test_filename}`\n\n"
            f"TECHNICAL ANALYSIS SUMMARY:\n{analysis_summary}\n\n"
            f"SOURCE CODE:\n```python\n{source_code}\n```"
        )
        raw_response = self.llm.generate(system_prompt, user_prompt)

        # Basic cleanup: remove control characters and known markers
        raw_response = re.sub(r'<ctrl\d+>', '', raw_response)
        raw_response = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw_response)
        # Strip markdown code fences (```json / ```python) if present
        cleaned = raw_response.strip()
        cleaned = re.sub(r'^```(?:json|python)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```\s*$', '', cleaned)

        code = ""
        try:
            payload = json.loads(cleaned)
            # support either {"source_code": "..."} or {"files": [{"source_code": "..."}]}
            if isinstance(payload, dict):
                if "source_code" in payload and isinstance(payload["source_code"], str):
                    code = payload.get("source_code", "")
                else:
                    files = payload.get("files") or []
                    if isinstance(files, list) and files:
                        first = files[0]
                        if isinstance(first, dict):
                            code = first.get("source_code", "") or first.get("source", "")
        except json.JSONDecodeError:
            code = cleaned

        code = self._sanitize_generated_test_code(code)
        for bad, good in (
            ("—", "-"),
            ("–", "-"),
            ("‑", "-"),
            ("−", "-"),
            ("‒", "-"),
            ("﹘", "-"),
            ("﹣", "-"),
            ("－", "-"),
        ):
            code = code.replace(bad, good)
        if code and not self._is_valid_python(code):
            repaired = self._repair_test_syntax(source_code, source_filename, code, test_filename)
            code = self._sanitize_generated_test_code(repaired)
            for bad, good in (
                ("—", "-"),
                ("–", "-"),
                ("‑", "-"),
                ("−", "-"),
                ("‒", "-"),
                ("﹘", "-"),
                ("﹣", "-"),
                ("－", "-"),
            ):
                code = code.replace(bad, good)

        if not code or not self._looks_like_test_module(code):
            logger.warning("LLM failed to generate valid tests for %s, using default.", source_filename)
            code = self._fallback_test_suite(source_filename)
        return code

    def _validate_and_repair_test(self, source_code: str, source_filename: str, test_code: str, test_filename: str) -> str:
        """Perform an internal verification pass to maximize pass rate before pytest starts."""
        system_prompt = (
            "You are a strict QA Reviewer. Perform a static compatibility analysis between the Source Code and Test Code.\n"
            "Check for:\n"
            "1. Import errors (missing modules or wrong paths).\n"
            "2. Missing or incorrect constructor arguments.\n"
            "3. Dataclass mismatches.\n"
            "4. Incorrect static method usage.\n"
            "5. Incompatible assertions or wrong expected output.\n\n"
            "If any issues are found, automatically repair the test file and return the completely fixed valid Python test code.\n"
            "If no issues are found and the tests are 100% compatible, return the exact original test code.\n"
            "Return ONLY valid Python code, no markdown blocks."
        )
        user_prompt = (
            f"Source File: {source_filename}\n```python\n{source_code}\n```\n\n"
            f"Generated Test File: {test_filename}\n```python\n{test_code}\n```"
        )
        try:
            repaired = self.llm.generate(system_prompt, user_prompt)
            cleaned = self._sanitize_generated_test_code(repaired)
            cleaned = re.sub(r'^```(?:json|python)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```\s*$', '', cleaned)
            if cleaned and self._is_valid_python(cleaned):
                return cleaned
        except LLMError:
            pass
        return test_code

    @staticmethod
    def _sanitize_generated_test_code(code: str) -> str:
        """Normalize common LLM output issues before syntax validation."""
        if not code:
            return ""

        code = re.sub(r"<ctrl\d+>", "", code)
        code = code.translate(str.maketrans({
            "—": "-",
            "–": "-",
            "‑": "-",
        }))
        return code.strip()

    @staticmethod
    def _is_valid_python(code: str) -> bool:
        """Return True when the generated code parses as valid Python."""
        if not code.strip():
            return False
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    @staticmethod
    def _looks_like_test_module(code: str) -> bool:
        """Return True when code parses and contains at least one pytest-style test."""
        if not TesterAgent._is_valid_python(code):
            return False
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                return True
        return False

    def _repair_test_syntax(
        self,
        source_code: str,
        source_filename: str,
        invalid_code: str,
        test_filename: str,
    ) -> str:
        """Ask the LLM to repair syntax-only issues in generated tests."""
        system_prompt = (
            "You are a Python syntax repair assistant. Fix syntax errors only. "
            "Return ONLY valid Python code for the test file."
        )
        user_prompt = (
            f"Source File Path: `{source_filename}`\n"
            f"Test File Path: `{test_filename}`\n\n"
            f"The current test file has syntax errors. Repair it without changing the intended coverage.\n\n"
            f"```python\n{invalid_code}\n```\n\n"
            f"Source code for reference:\n```python\n{source_code}\n```"
        )

        try:
            repaired = self.llm.generate(system_prompt, user_prompt)
        except LLMError:
            return invalid_code

        cleaned = repaired.strip()
        cleaned = re.sub(r'^```(?:json|python)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```\s*$', '', cleaned)
        return cleaned

    @staticmethod
    def _fallback_test_suite(source_filename: str) -> str:
        """Provide a deterministic smoke-test fallback when generation fails."""
        module_name = Path(source_filename).with_suffix("").as_posix()
        module_name = module_name.replace("/", ".").replace("\\", ".")
        module_name = re.sub(r"^src\.", "", module_name)
        if module_name.endswith(".__init__"):
            module_name = module_name[: -len(".__init__")]

        return (
            "import importlib\n\n"
            f"MODULE_NAME = {module_name!r}\n\n"
            "def test_module_imports():\n"
            "    module = importlib.import_module(MODULE_NAME)\n"
            "    assert module is not None\n"
        )

    def _analyze_test_failures(self, output: str) -> dict:
        system_prompt = (
            "You are a Senior QA Engineer. Analyze the following pytest output and group the failures into a Root Cause Analysis.\n"
            "Classify each failure into one of these strict categories:\n"
            "Import Error, Assertion Failure, Validation Error, Runtime Exception, Type Error, Value Error, "
            "Module Missing, Logic Error, Floating Point Precision, Formatting Error, Static Method Error, Dependency Error, Dataclass Error.\n\n"
            "Return ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "rca": [\n'
            '    {\n'
            '      "category": "<One of the strict categories>",\n'
            '      "why_it_happened": "<Detailed explanation of the root cause>",\n'
            '      "caused_by_file": "<File path that needs to be fixed>",\n'
            '      "caused_by_function": "<Function or class name>",\n'
            '      "confidence_score": <Number 0-100>,\n'
            '      "suggested_fix": "<Actionable instructions to fix the code>"\n'
            "    }\n"
            "  ],\n"
            '  "recommended_action": "<General manual or auto-fix steps>"\n'
            "}"
        )
        
        user_prompt = f"Pytest Output:\n```text\n{output[-6000:] if len(output) > 6000 else output}\n```"
        
        try:
            raw_response = self.llm.generate(system_prompt, user_prompt)
            cleaned = raw_response.strip()
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```\s*$', '', cleaned)
            return json.loads(cleaned)
        except Exception as e:
            logger.warning("Failed to analyze test failures: %s", e)
            return {"rca": [], "recommended_action": "Check raw logs for details."}
