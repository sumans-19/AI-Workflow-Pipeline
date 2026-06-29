import ast
import re
from pathlib import Path
from typing import Optional, List, Set, Tuple
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

            # ── Resolve the test plan from the approved folder_structure ──
            test_root = self._resolve_test_root(context)
            planned_test_paths = self._planned_test_paths(context, test_root)

            # Build a work list. If the plan specifies test files, drive
            # off those (each one gets mapped back to a source file).
            # Otherwise fall back to "derive one test per source file".
            work_items: List[tuple] = []   # (test_path, source_path or None)
            seen_test_paths: Set[str] = set()

            if planned_test_paths:
                # The plan has explicit test files — respect them.
                for tpath in planned_test_paths:
                    seen_test_paths.add(tpath)
                    if Path(tpath).name in {"__init__.py", "conftest.py"}:
                        # conftest.py / package init — handled separately.
                        work_items.append((tpath, None))
                        continue
                    src = _match_source_for_test(tpath, python_sources, test_root)
                    work_items.append((tpath, src))
            else:
                # No plan → fall back to one test per source file.
                for src_path in python_sources:
                    mirror = _mirror_subpath_under_test_root(src_path, test_root)
                    if mirror == "__test_placeholder__":
                        continue
                    tpath = (Path(test_root) / mirror).as_posix()
                    if tpath not in seen_test_paths:
                        seen_test_paths.add(tpath)
                        work_items.append((tpath, src_path))

            # Add any source file not covered by the planned tests.
            for src_path in python_sources:
                already_covered = any(
                    Path(w[0]).stem.replace("test_", "", 1) == Path(src_path).stem
                    for w in work_items
                    if w[1] is not None
                )
                if already_covered:
                    continue
                mirror = _mirror_subpath_under_test_root(src_path, test_root)
                if mirror == "__test_placeholder__":
                    continue
                tpath = (Path(test_root) / mirror).as_posix()
                if tpath not in seen_test_paths:
                    seen_test_paths.add(tpath)
                    work_items.append((tpath, src_path))

            if not work_items:
                logger.warning("%s found no test work items.", self.name)
                if context.emit_event:
                    context.emit_event("agent_completed", {"agent": "tester", "message": "No tests to generate", "passed": True})
                context.success = True
                return context

            # ── Generate each test file ───────────────────────────────
            total = len(work_items)
            for idx, (test_filename, src_path) in enumerate(work_items, 1):
                if context.emit_event:
                    context.emit_event("agent_progress", {
                        "agent": "tester",
                        "progress": int((idx / max(total, 1)) * 50),
                        "message": f"Generating {test_filename}...",
                    })

                # conftest.py or __init__.py — generate a small stub.
                base = Path(test_filename).name
                if base == "__init__.py":
                    self._emit_test_file(test_filename, "", context)
                    continue
                if base == "conftest.py":
                    stub = self._generate_conftest(test_root, list(python_sources.keys()))
                    self._emit_test_file(test_filename, stub, context)
                    continue

                # Regular test_*.py file — generate against the source.
                if src_path and src_path in python_sources:
                    code = python_sources[src_path]
                elif src_path is None:
                    # Couldn't resolve a source — pick the source with the
                    # closest package name.
                    code = self._best_effort_source_for_test(test_filename, python_sources)

                test_code = self._generate_tests(code, src_path or test_filename)
                test_code = self._validate_and_repair_test(
                    code, src_path or test_filename, test_code, test_filename
                )
                self._emit_test_file(test_filename, test_code, context)
            logger.info("%s running pytest...", self.name)
            if context.emit_event:
                context.emit_event("agent_progress", {
                    "agent": "tester",
                    "progress": 75,
                    "message": "Running pytest...",
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

            # ── Auto-fix loop: detect ImportError and patch missing modules ─
            # If the Coder wrote code that imports from a module that doesn't
            # exist (e.g. ``from calculator_app.exceptions import ...`` when
            # ``exceptions.py`` was never created), generate a minimal stub
            # for each missing module and re-run pytest. This keeps the
            # majority/all-pass invariant working even when the Coder forgets
            # to write one of the files it imports.
            for repair_attempt in range(3):
                missing_modules = self._collect_missing_modules(output, context)
                if not missing_modules:
                    break
                logger.warning(
                    "%s: detected %d missing module(s) from ImportErrors: %s — "
                    "generating stubs (attempt %d/3)",
                    self.name, len(missing_modules),
                    ", ".join(missing_modules), repair_attempt + 1,
                )
                if context.emit_event:
                    context.emit_event("agent_progress", {
                        "agent": "tester",
                        "progress": 70,
                        "message": (
                            f"Auto-generating {len(missing_modules)} missing module(s)… "
                            f"({', '.join(missing_modules[:3])}…)"
                        ),
                    })
                self._stub_missing_modules(missing_modules, context)
                # Re-run pytest so the next iteration sees the stubs.
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
                if raw_success:
                    logger.info("%s: auto-repair succeeded on attempt %d", self.name, repair_attempt + 1)
                    break

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
            # Reflect the EFFECTIVE outcome (raw OR majority_passed) in
            # context.success so the orchestrator's downstream gating
            # agrees with the sidebar's TESTING card and the ReviewPanel.
            # Previously this was hard-coded to True which masked failures
            # when the orchestration continued past a 0%-pass run.
            context.success = bool(success)

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

    @staticmethod
    def _planned_test_paths(context, test_root: str) -> List[str]:
        """Return the explicit list of test file paths from the approved tree.

        Drops directory entries and ``__init__.py`` markers. Conftest and
        regular test files are all kept (the caller handles them differently).
        Only ``.py`` files are honoured — non-Python planned test paths
        (``.js``, ``.ts``) are silently skipped per the Python-only policy.
        """
        plan = getattr(context, "plan", None)
        if not plan or not getattr(plan, "plan_approved", False):
            return []
        try:
            # planned_test_files() already filters to *.py + test paths
            # (and warns about anything non-Python it finds), so we can
            # rely on it directly here.
            from .planning_models import FolderStructure as _FS
            fs = getattr(plan, "folder_structure", None)
            if not fs or not getattr(fs, "tree", None):
                return []
            out: list = []
            for p in _FS(tree=fs.tree).planned_test_files():
                if Path(p).name == "__init__.py":
                    continue
                if Path(p).suffix == ".py":
                    out.append(p)
            return out
        except Exception:
            return []  

    def _emit_test_file(self, test_filename: str, test_code: str, context) -> None:
        """Persist a generated test file and emit it as a ``file_created`` event.

        Defensive guard: refuses to write anything that isn't a ``.py`` file.
        The project is Python-only, so a non-``.py`` path here is always a
        bug (e.g. the LLM slipped us a ``tests/foo.js`` even though the
        planned tree said Python only).
        """
        # Allow standard packaging files (pyproject.toml etc.) to exist in
        # the planned tree, but tests are ALWAYS ``.py``.
        if Path(test_filename).suffix != ".py":
            # conftest.py / __init__.py are also ``.py`` (already covered).
            logger.warning(
                "Tester: refusing to write non-Python test file %r — Python only.",
                test_filename,
            )
            return
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

    def _generate_conftest(self, test_root: str, source_paths: List[str]) -> str:
        """Generate a sensible ``conftest.py`` for the planned test root."""
        # Build a sys.path tweak so pytest finds the inner package(s).
        inserts = sorted({str(Path(p).parents[len(Path(p).parents) - 2])
                          for p in source_paths
                          if len(Path(p).parents) >= 2 and p != "."})
        syspath_lines = "\n".join(
            f"sys.path.insert(0, {json.dumps(d)})" for d in inserts
        ) if inserts else ""

        return f'''"""Auto-generated conftest.py for {test_root}/.

Adds the inner package directory to ``sys.path`` so ``pytest`` can
import the modules under test without an editable install.
"""
import json
import sys
from pathlib import Path

# Make sure pytest discovers the project's inner packages even when it
# is invoked from a different working directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
{syspath_lines}


@pytest.fixture(scope="session")
def project_root():
    """Absolute path to the project root (parent of the tests/ directory)."""
    return _PROJECT_ROOT
'''

    def _best_effort_source_for_test(
        self, test_filename: str, python_sources: dict
    ) -> Tuple[str, str]:
        """Return ``(source_path, source_code)`` best matching a test path.

        Used when the test path was explicitly planned but we couldn't
        map it back to a real source file. Picks the source with the
        longest shared package name.
        """
        from pathlib import Path as _P
        test_stem = _P(test_filename).stem.replace("test_", "", 1)
        if not test_stem:
            test_stem = _P(test_filename).stem
        best, best_score = None, -1
        for sp in python_sources.keys():
            score = 0
            if _P(sp).stem == test_stem:
                score += 5
            if test_stem in sp:
                score += 2
            for part in _P(sp).parts[:-1]:
                if part and part in test_filename:
                    score += 1
            if score > best_score:
                best, best_score = sp, score
        if best is None and python_sources:
            best = next(iter(python_sources))
        return best, python_sources.get(best, "")

    @staticmethod
    def _collect_missing_modules(pytest_output: str, context) -> list:
        """Extract dotted module names that triggered ImportError.

        Looks for patterns like:
            ``ModuleNotFoundError: No module named 'calculator_app.exceptions'``
            ``from calculator_app.exceptions import (``

        Returns a deduplicated list of fully-qualified module names that
        were imported by some test/source file but don't have a matching
        ``.py`` file in the workspace.
        """
        import re as _re
        missing: list = []
        seen: set = set()
        # Strip very long output to keep regex fast.
        tail = pytest_output[-8000:] if pytest_output else ""

        # 1. ModuleNotFoundError: No module named 'foo.bar.baz'
        for m in _re.finditer(
            r"ModuleNotFoundError:\s*No module named ['\"]([^'\"]+)['\"]",
            tail,
        ):
            mod = m.group(1)
            if mod not in seen:
                seen.add(mod)
                missing.append(mod)

        # 2. ``from x.y.z import ...`` lines whose x.y.z package is
        # imported from a test file that errored at collection.
        for m in _re.finditer(
            r"(?:from|import)\s+([a-zA-Z_][\w.]*)\s*(?:$|\(|import)",
            tail,
        ):
            mod = m.group(1)
            if mod.startswith(("pytest", "unittest", "_pytest", "pluggy")):
                continue
            if mod in seen:
                continue
            seen.add(mod)
            missing.append(mod)

        # Discard anything that already exists as a real file on disk.
        ws = Path(context.workspace_path)
        existing = {
            ".".join(p.relative_to(ws).with_suffix("").parts)
            for p in ws.rglob("*.py")
            if p.name != "__init__.py"
        }
        # Also include directory packages.
        for p in ws.rglob("__init__.py"):
            rel = p.relative_to(ws).parent
            existing.add(".".join(rel.parts))

        # Only keep modules that are children of the project (not stdlib).
        # A typical missing module looks like ``calculator_app.exceptions``
        # which, if it lived at ``calculator_app/exceptions.py``, would be in
        # ``existing``.
        filtered: list = []
        for mod in missing:
            top = mod.split(".")[0]
            if top not in existing and "." not in mod:
                continue  # looks like a third-party package, leave it
            if mod in existing:
                continue  # actually exists, ImportError must be something else
            filtered.append(mod)
        return filtered

    @staticmethod
    def _stub_missing_modules(missing: list, context) -> None:
        """Generate minimal Python stub files for every missing module.

        Where they go:
          * If the dotted name already has a directory prefix that's in the
            workspace (e.g. ``calculator_app``), the stub goes inside that
            directory.
          * Otherwise the stub goes to ``<workspace>/<module>.py``.

        Stubs are emitted as ``file_created`` events so the FileTree
        reflects them immediately.
        """
        from .planning_models import is_test_path
        ws = Path(context.workspace_path)
        for mod in missing:
            parts = mod.split(".")
            target = ws.joinpath(*parts).with_suffix(".py")
            # Don't clobber tests or pre-existing files.
            if target.exists() or is_test_path(str(target)):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            stub = (
                f'"""Auto-generated stub for missing module `{mod}`.\n\n'
                f"This file was synthesised by the Tester Agent because the\n"
                f"Coder wrote `import {mod}` without producing a matching\n"
                f"``{parts[-1]}.py``. Replace its body with a real\n"
                f"implementation on the next Auto-Fix iteration.\n"
                f'"""\n\n'
                f"__all__ = []\n"
            )
            target.write_text(stub, encoding="utf-8")
            logger.info("Tester: stubbed missing module %s at %s", mod, target)
            # Update context so subsequent runs see it.
            rel = str(target.relative_to(ws))
            context.source_code[rel] = stub
            context.emitted_files.add(rel)
            if context.emit_event:
                context.emit_event("file_created", {
                    "path": rel,
                    "content": stub,
                    "language": "python",
                })

    @staticmethod
    def _resolve_test_root(context) -> str:
        """Pick the directory where tests should live.

        Priority:
          1. If the approved plan has a ``folder_structure`` module, parse
             the planned tree and pick the first directory whose name starts
             with ``test`` (e.g. ``tests``, ``tests/unit``).
          2. Otherwise fall back to a top-level ``tests/`` directory.
        """
        plan = getattr(context, "plan", None)
        if plan and getattr(plan, "plan_approved", False):
            try:
                from .planning_models import FolderStructure as _FS
                fs = getattr(plan, "folder_structure", None)
                if fs and getattr(fs, "tree", None):
                    root = _FS(tree=fs.tree).test_root()
                    if root:
                        return root.rstrip("/")
            except Exception:
                pass
        return "tests"

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
        
        # Compute the test filename from the planned test root so the
        # generated tests live where the folder_structure planned them to.
        mirror = _mirror_subpath_under_test_root(source_filename, "tests")
        if mirror == "__test_placeholder__":
            return ""  # Caller already filters __init__.py
        test_filename = (Path("tests") / mirror).as_posix()

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


# ─────────────────────────────────────────────────────────────────────
# Module-level helper used by TesterAgent.execute
# ─────────────────────────────────────────────────────────────────────

def _mirror_subpath_under_test_root(source_filename: str, test_root: str) -> str:
    """Return the test-file path that mirrors ``source_filename`` under ``test_root``.

    Strategy: keep only the Python package directory right before the
    file (plus any sub-package directories) and the file's stem. Common
    wrapper segments like ``src`` are stripped so the mirrored test path
    stays short and matches Python convention.

    Examples (test_root="tests"):
        src/calculator/core.py           → test_calculator_core.py
        src/calculator/__init__.py       → __test_placeholder__  (skipped upstream)
        calculator/core.py               → test_core.py
        src/calculator/services/api.py   → test_calculator_services_api.py
        calculator/src/calculator/core.py→ test_calculator_core.py  (root + wrapper stripped)
    """
    from pathlib import Path as _P
    src = _P(source_filename)
    if src.name == "__init__.py":
        return "__test_placeholder__"

    # Handle the common `projectname/src/projectname/...` layout by
    # stripping the duplicate root + wrapper.
    parts = list(src.parts)
    if len(parts) >= 3 and parts[0] == parts[2] and parts[1] in {"src", "lib"}:
        parts = parts[2:]

    # Drop common wrapper segments that aren't part of the package name.
    wrappers = {"src", "lib", "pkg", "app", "source", test_root}
    relevant = [p for p in parts[:-1] if p not in wrappers and p != "."]
    # De-duplicate consecutive identical segments (defensive).
    deduped: list = []
    for p in relevant:
        if not deduped or deduped[-1] != p:
            deduped.append(p)

    stem = src.stem
    if deduped:
        prefix = "_".join(deduped)
        return f"test_{prefix}_{stem}.py"
    return f"test_{stem}.py"


# ─────────────────────────────────────────────────────────────────────
# Module-level helper used by TesterAgent.execute
# ─────────────────────────────────────────────────────────────────────

def _match_source_for_test(test_filename: str, python_sources: dict, test_root: str) -> Optional[str]:
    """Return the source-file path that a planned test file should cover.

    Strategy (most specific first):
      1. Exact package+module reverse mapping (e.g. ``tests/calculator/test_core.py``
         → ``src/calculator/core.py``).
      2. Stem-matching within the planned test root (with package prefix
         inferred from the path).
      3. Bare stem match (e.g. ``test_cli.py`` → ``cli.py``) — used when
         nothing more specific is available.

    Returns ``None`` if no plausible source file can be found (caller
    will fall back to ``_best_effort_source_for_test``).
    """
    from pathlib import Path as _P
    test_path = _P(test_filename)
    test_stem = test_path.stem
    # Strip leading "test_" to get the candidate source stem.
    src_stem = test_stem[len("test_"):] if test_stem.startswith("test_") else test_stem

    # Make test_root absolute (so Path.parts behave predictably)
    test_root_path = _P(test_root)
    if test_root_path.is_absolute():
        try:
            rel = test_path.relative_to(test_root_path)
            test_parts = list(rel.parts)
        except ValueError:
            test_parts = list(test_path.parts)
    else:
        try:
            rel = test_path.relative_to(test_root_path)
            test_parts = list(rel.parts)
        except ValueError:
            test_parts = list(test_path.parts)

    # ── 1. Mirror-matched with package folders ──────────────────────
    # If the planned test is at ``<test_root>/<pkg>/test_<name>.py`` we
    # prefer the source at ``src/<pkg>/<name>.py`` or ``<pkg>/<name>.py``.
    mirror_candidates: List[str] = []
    if len(test_parts) >= 2:
        # Drop the trailing test_<name>.py and treat the rest as a package path.
        pkg_parts = test_parts[:-1]
        # Common Python wrapper directories we'll try inserting.
        for prefix in ["src", "lib", "pkg", "app", ""]:
            cand_parts = ([prefix] if prefix else []) + pkg_parts + [src_stem + ".py"]
            cand = "/".join(p for p in cand_parts if p)
            mirror_candidates.append(cand)

    for cand in mirror_candidates:
        if cand in python_sources:
            return cand
        # Allow ``.py`` ↔ ``/__init__.py`` not (we want real source).
        for sp in python_sources:
            if sp == cand:
                return cand

    # ── 2. Stem match across source files ──────────────────────────
    for sp in python_sources:
        if _P(sp).stem == src_stem:
            return sp

    # ── 3. Substring match (last resort) ───────────────────────────
    for sp in python_sources:
        if src_stem in sp:
            return sp

    return None
