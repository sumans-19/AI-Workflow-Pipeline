import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agents.base import BaseAgent
from ..core.context import FeedbackItem, WorkflowContext
from ..config import settings
from ..llm.base import BaseLLMClient
from ..llm.openai_client import OpenAIClient
from ..logging_config import logger


def _extract_failure_summary(output: str, max_lines: int = 15) -> str:
    """Extract only the FAILURES/ERRORS section from pytest output."""
    lines = output.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("FAILED") or "FAILURES" in line or "ERRORS" in line or "= FAILURES =" in line:
            start = i
            break
    if start is not None:
        return "\n".join(lines[start:start + max_lines])
    return "\n".join(lines[-max_lines:])


def _is_duplicate(new_desc: str, existing_items: list[FeedbackItem]) -> bool:
    """Check if a feedback item's description overlaps with existing reviewer items."""
    for item in existing_items:
        if item.source == "reviewer":
            if item.description in new_desc or new_desc in item.description:
                return True
    return False


class ValidatorAgent(BaseAgent):
    PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

    def __init__(self, llm: Optional[BaseLLMClient] = None):
        super().__init__(name="Validator Agent")
        self.llm = llm or OpenAIClient()
        self._prompt_cache: dict = {}

    def execute(self, context: WorkflowContext) -> WorkflowContext:
        logger.info("%s running comprehensive validation...", self.name)

        report: Dict[str, Any] = {}

        # ── Phase 1: Test Validation ─────────────────────────────
        report["tests"] = self._validate_tests(context)

        # ── Phase 2: Documentation Validation ────────────────────
        report["docs"] = self._validate_documentation(context)

        # ── Phase 3: Dependency Validation ───────────────────────
        report["dependencies"] = self._validate_dependencies(context)

        # ── Phase 4: Build Verification ──────────────────────────
        report["build"] = self._validate_build(context)

        # ── Phase 5: Quality Gate Aggregation ────────────────────
        report["quality_gates"] = self._aggregate_quality_gates(context, report)

        # ── Phase 6: Release Report ──────────────────────────────
        report["release"] = self._generate_release_report(context, report)

        context.validation_report = report

        # Determine overall success and create feedback items for failures
        new_items: list[FeedbackItem] = []

        if not report["tests"]["all_pass"]:
            test_output = context.test_results.get("output", "No output")
            summary = _extract_failure_summary(test_output)
            new_items.append(FeedbackItem(
                run_id=context.run_id,
                checkpoint="FINAL_REVIEW",
                source="tester",
                severity="critical",
                category="test",
                description=f"Tests failed:\n{summary}",
                action="fix",
                author="validator",
            ))

        for issue in context.review_issues:
            if "MAJOR" in issue or "CRITICAL" in issue:
                desc = f"Review flagged issues:\n{issue}"
                if not _is_duplicate(desc, context.feedback_items):
                    new_items.append(FeedbackItem(
                        run_id=context.run_id,
                        checkpoint="FINAL_REVIEW",
                        source="validator",
                        severity="major",
                        category="quality",
                        description=desc,
                        action="fix",
                        author="validator",
                    ))

        if not report["tests"]["threshold_met"]:
            cov = report["tests"]["coverage"]
            new_items.append(FeedbackItem(
                run_id=context.run_id,
                checkpoint="FINAL_REVIEW",
                source="validator",
                severity="major",
                category="test",
                description=f"Coverage below threshold: {cov:.1f}% < {settings.MIN_COVERAGE:.1f}%",
                action="fix",
                author="validator",
            ))

        if not report["build"]["pylint_ok"]:
            score = report["build"]["pylint_score"]
            new_items.append(FeedbackItem(
                run_id=context.run_id,
                checkpoint="FINAL_REVIEW",
                source="validator",
                severity="major",
                category="style",
                description=f"Pylint score below threshold: {score:.2f} < {settings.MIN_PYLINT_SCORE:.2f}",
                action="fix",
                author="validator",
            ))

        if new_items:
            context.feedback_items = [
                f for f in context.feedback_items
                if f.source not in ("tester", "validator")
            ]
            context.feedback_items.extend(new_items)
            context.success = False
            logger.info("%s failed — %d issues found.", self.name, len(new_items))
        else:
            context.success = True
            context.current_step = "READY_TO_MERGE"
            logger.info("%s passed — all gates clear.", self.name)

        return context

    # ==================================================================
    # Phase 1: Test Validation
    # ==================================================================

    def _validate_tests(self, context: WorkflowContext) -> Dict[str, Any]:
        results = context.test_results
        passed = results.get("passed", False)
        coverage = float(results.get("coverage_line", results.get("coverage", 0)))
        duration = float(results.get("duration_seconds", 0))

        # Parse pass/fail/skip counts from pytest output
        output = results.get("output", "")
        counts = self._parse_test_counts(output)

        return {
            "all_pass": passed,
            "total": counts["total"],
            "passed": counts["passed"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
            "coverage": coverage,
            "threshold_met": coverage >= settings.MIN_COVERAGE,
            "duration": duration,
            "duration_ok": duration < 300,  # 5 minute threshold
        }

    @staticmethod
    def _parse_test_counts(output: str) -> Dict[str, int]:
        """Extract passed/failed/skipped counts from pytest summary line."""
        counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        
        # Match pytest summary like: "12 failed, 125 passed, 5 warnings in 0.89s"
        passed_match = re.search(r"(\d+)\s+passed", output)
        failed_match = re.search(r"(\d+)\s+failed", output)
        skipped_match = re.search(r"(\d+)\s+skipped", output)

        if passed_match:
            counts["passed"] = int(passed_match.group(1))
        if failed_match:
            counts["failed"] = int(failed_match.group(1))
        if skipped_match:
            counts["skipped"] = int(skipped_match.group(1))
        
        counts["total"] = counts["passed"] + counts["failed"] + counts["skipped"]
        return counts

    # ==================================================================
    # Phase 2: Documentation Validation
    # ==================================================================

    def _validate_documentation(self, context: WorkflowContext) -> Dict[str, Any]:
        source = context.source_code
        
        # Check for key files
        readme_key = self._find_file(source, "README.md")
        requirements_key = self._find_file(source, "requirements.txt") or self._find_file(source, "pyproject.toml")
        gitignore_key = self._find_file(source, ".gitignore")

        readme_content = source.get(readme_key, "") if readme_key else ""
        readme_exists = bool(readme_key and len(readme_content.strip()) > 50)

        # LLM-based README quality analysis
        readme_quality = {"quality_score": "poor", "suggestions": ["README.md is missing or empty"]}
        if readme_exists:
            readme_quality = self._analyze_readme_quality(readme_content)

        # Check docstrings in Python source files
        docstring_results = self._check_docstrings(source)

        return {
            "readme": {
                "exists": readme_exists,
                "quality": readme_quality.get("quality_score", "unknown"),
                "has_description": readme_quality.get("has_description", False),
                "has_installation": readme_quality.get("has_installation", False),
                "has_usage_examples": readme_quality.get("has_usage_examples", False),
                "suggestions": readme_quality.get("suggestions", []),
            },
            "requirements": bool(requirements_key),
            "gitignore": bool(gitignore_key),
            "docstrings": docstring_results,
        }

    def _analyze_readme_quality(self, readme_content: str) -> dict:
        """Use LLM to evaluate README completeness."""
        try:
            system_prompt = self._load_prompt("validator_docs.txt")
            user_prompt = f"README.md Content:\n```markdown\n{readme_content}\n```"
            raw = self.llm.generate(system_prompt, user_prompt)
            cleaned = raw.strip()
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```\s*$', '', cleaned)
            return json.loads(cleaned)
        except Exception as e:
            logger.warning("README quality analysis failed: %s", e)
            return {"quality_score": "unknown", "suggestions": ["Analysis failed"]}

    @staticmethod
    def _check_docstrings(source: Dict[str, str]) -> Dict[str, Any]:
        """Check that Python source files have module-level docstrings."""
        total = 0
        documented = 0
        undocumented: list[str] = []

        for filename, code in source.items():
            if not filename.endswith(".py"):
                continue
            if Path(filename).name in ("__init__.py", "conftest.py"):
                continue
            if filename.startswith("tests/") or Path(filename).name.startswith("test_"):
                continue

            total += 1
            try:
                tree = ast.parse(code)
                if ast.get_docstring(tree):
                    documented += 1
                else:
                    undocumented.append(filename)
            except SyntaxError:
                undocumented.append(filename)

        return {
            "total_files": total,
            "documented": documented,
            "undocumented": undocumented,
        }

    # ==================================================================
    # Phase 3: Dependency Validation
    # ==================================================================

    def _validate_dependencies(self, context: WorkflowContext) -> Dict[str, Any]:
        source = context.source_code
        req_key = self._find_file(source, "requirements.txt")

        if not req_key:
            return {
                "has_requirements": False,
                "pinned": False,
                "unpinned": [],
                "unused": [],
                "missing": [],
                "security_scan": "not_available",
            }

        req_content = source[req_key]
        deps = self._parse_requirements(req_content)
        unpinned = [d["name"] for d in deps if not d["pinned"]]

        # Cross-reference imports vs requirements
        imported_modules = self._extract_imports(source)
        declared_deps = {d["name"].lower().replace("-", "_") for d in deps}
        
        # Standard library modules to exclude
        stdlib = {
            "os", "sys", "re", "json", "ast", "time", "datetime", "math", "pathlib",
            "typing", "collections", "functools", "itertools", "enum", "abc",
            "dataclasses", "logging", "unittest", "argparse", "subprocess", "io",
            "copy", "uuid", "hashlib", "secrets", "csv", "configparser",
            "textwrap", "shutil", "glob", "tempfile", "contextlib", "warnings",
        }
        external_imports = {m for m in imported_modules if m not in stdlib}
        
        missing = [m for m in external_imports if m.lower().replace("-", "_") not in declared_deps]
        unused = [d for d in declared_deps if d not in {m.lower().replace("-", "_") for m in external_imports}]

        return {
            "has_requirements": True,
            "pinned": len(unpinned) == 0,
            "unpinned": unpinned,
            "unused": unused,
            "missing": missing,
            "security_scan": "not_scanned",  # Placeholder for future Docker-based scanning
        }

    @staticmethod
    def _parse_requirements(content: str) -> list[dict]:
        """Parse requirements.txt into structured dependency list."""
        deps = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Check for version pin (>=, ==, ~=, !=, <, >)
            pinned = bool(re.search(r'[><=!~]', line))
            name = re.split(r'[><=!~\[]', line)[0].strip()
            if name:
                deps.append({"name": name, "pinned": pinned, "raw": line})
        return deps

    @staticmethod
    def _extract_imports(source: Dict[str, str]) -> set[str]:
        """Extract top-level imported module names from all Python files."""
        modules: set[str] = set()
        for filename, code in source.items():
            if not filename.endswith(".py"):
                continue
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            modules.add(alias.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.level == 0:
                            modules.add(node.module.split(".")[0])
            except SyntaxError:
                continue
        return modules

    # ==================================================================
    # Phase 4: Build Verification
    # ==================================================================

    def _validate_build(self, context: WorkflowContext) -> Dict[str, Any]:
        syntax_errors: list[dict] = []
        import_errors: list[str] = []

        for filename, code in context.source_code.items():
            if not filename.endswith(".py"):
                continue
            try:
                ast.parse(code)
            except SyntaxError as e:
                syntax_errors.append({
                    "file": filename,
                    "line": e.lineno,
                    "message": e.msg,
                })

        # Check imports by attempting to compile each file
        for filename, code in context.source_code.items():
            if not filename.endswith(".py"):
                continue
            if Path(filename).name == "__init__.py":
                continue
            try:
                compile(code, filename, "exec")
            except SyntaxError:
                pass  # Already captured above
            except Exception as e:
                import_errors.append(f"{filename}: {e}")

        pylint_score = float(context.metrics.get("pylint_score", 0))

        return {
            "syntax_valid": len(syntax_errors) == 0,
            "syntax_errors": syntax_errors,
            "imports_ok": len(import_errors) == 0,
            "import_errors": import_errors,
            "pylint_score": pylint_score,
            "pylint_ok": pylint_score >= settings.MIN_PYLINT_SCORE,
        }

    # ==================================================================
    # Phase 5: Quality Gate Aggregation
    # ==================================================================

    def _aggregate_quality_gates(self, context: WorkflowContext, report: Dict) -> Dict[str, Any]:
        gates: list[dict] = []

        # Gate 1: Coding Standards (Pylint)
        pylint_score = report["build"]["pylint_score"]
        gates.append({
            "name": "Coding Standards",
            "status": "PASS" if report["build"]["pylint_ok"] else "FAIL",
            "detail": f"Pylint {pylint_score:.1f}/10 (min: {settings.MIN_PYLINT_SCORE})",
        })

        # Gate 2: Test Coverage
        coverage = report["tests"]["coverage"]
        gates.append({
            "name": "Test Coverage",
            "status": "PASS" if report["tests"]["threshold_met"] else "FAIL",
            "detail": f"{coverage:.1f}% (min: {settings.MIN_COVERAGE}%)",
        })

        # Gate 3: All Tests Pass
        gates.append({
            "name": "Test Execution",
            "status": "PASS" if report["tests"]["all_pass"] else "FAIL",
            "detail": f"{report['tests']['passed']}/{report['tests']['total']} passed",
        })

        # Gate 4: Code Review
        unresolved = context.unresolved_feedback()
        critical_unresolved = [f for f in unresolved if f.severity in ("critical", "major")]
        gates.append({
            "name": "Code Review",
            "status": "PASS" if not critical_unresolved else "FAIL",
            "detail": f"{len(critical_unresolved)} critical/major issues" if critical_unresolved else "No critical issues",
        })

        # Gate 5: Documentation
        doc_ok = report["docs"]["readme"]["exists"] and report["docs"]["requirements"]
        gates.append({
            "name": "Documentation",
            "status": "PASS" if doc_ok else "WARN",
            "detail": f"README: {'✓' if report['docs']['readme']['exists'] else '✗'}, "
                      f"Deps: {'✓' if report['docs']['requirements'] else '✗'}",
        })

        # Gate 6: Build Integrity
        gates.append({
            "name": "Build Integrity",
            "status": "PASS" if report["build"]["syntax_valid"] else "FAIL",
            "detail": f"{len(report['build']['syntax_errors'])} syntax errors",
        })

        all_passed = all(g["status"] == "PASS" for g in gates)
        
        return {
            "gates": gates,
            "all_passed": all_passed,
        }

    # ==================================================================
    # Phase 6: Release Report Generation
    # ==================================================================

    def _generate_release_report(self, context: WorkflowContext, report: Dict) -> Dict[str, Any]:
        tests = report["tests"]
        docs = report["docs"]
        deps = report["dependencies"]
        build = report["build"]
        gates = report["quality_gates"]

        checklist = [
            {"item": "All tests pass", "checked": tests["all_pass"]},
            {"item": f"Coverage ≥ {settings.MIN_COVERAGE}% (achieved: {tests['coverage']:.1f}%)", "checked": tests["threshold_met"]},
            {"item": f"Pylint score ≥ {settings.MIN_PYLINT_SCORE} (achieved: {build['pylint_score']:.1f})", "checked": build["pylint_ok"]},
            {"item": "No syntax errors", "checked": build["syntax_valid"]},
            {"item": "README.md present", "checked": docs["readme"]["exists"]},
            {"item": "Dependencies declared", "checked": deps["has_requirements"]},
            {"item": "Dependencies version-pinned", "checked": deps["pinned"]},
            {"item": "No critical review issues", "checked": gates["all_passed"]},
        ]

        all_checked = all(c["checked"] for c in checklist)
        overall_status = "APPROVED" if all_checked else "NEEDS_ATTENTION"

        return {
            "status": overall_status,
            "checklist": checklist,
            "project_name": context.project_name or "unknown",
            "attempt": context.retry_count + 1,
        }

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _find_file(source: Dict[str, str], target_name: str) -> Optional[str]:
        """Find a file in source_code dict by basename, case-insensitive."""
        for key in source:
            if Path(key).name.lower() == target_name.lower():
                return key
        return None

    def _load_prompt(self, prompt_name: str) -> str:
        if prompt_name not in self._prompt_cache:
            prompt_path = self.PROMPTS_DIR / prompt_name
            try:
                self._prompt_cache[prompt_name] = prompt_path.read_text(encoding="utf-8")
            except OSError:
                return "You are a documentation quality auditor. Return JSON."
        return self._prompt_cache[prompt_name]
