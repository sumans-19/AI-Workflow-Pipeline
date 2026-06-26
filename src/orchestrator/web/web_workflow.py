"""Web-adapted workflow orchestrator.

Wraps the existing pipeline stages but replaces terminal I/O with WebSocket
events so the React frontend can drive checkpoints.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set

from ..agents.coder import CoderAgent
from ..agents.tester import TesterAgent
from ..agents.reviewer import ReviewerAgent
from ..agents.validator import ValidatorAgent
from ..config import settings
from ..core.context import FeedbackItem, WorkflowContext
from ..core.metrics import collect_file_metrics, metrics_to_per_file_list
from ..llm.cost_tracker import CostTracker
from ..llm.factory import create_llm_client
from ..logging_config import logger
from ..tools.file_manager import FileManager
from .session import Session
from .ws_manager import manager as ws


class WebWorkflowOrchestrator:
    """Runs the same agent pipeline as the CLI but communicates via WebSocket."""

    def __init__(self, output_dir: str = None):
        budget = settings.LLM_BUDGET_LIMIT_USD or None
        self.cost_tracker = CostTracker(budget_limit_usd=budget)
        llm = create_llm_client(cost_tracker=self.cost_tracker)
        self.coder = CoderAgent(llm=llm)
        self.tester = TesterAgent(llm=llm)
        self.reviewer = ReviewerAgent(llm=llm)
        self.validator = ValidatorAgent(llm=llm)
        self.file_manager = FileManager()
        self.output_dir = output_dir or settings.RUNS_DIR
        self._emitted_files: Set[str] = set()

    # ------------------------------------------------------------------
    # Main entry — called from the FastAPI endpoint in a background thread
    # ------------------------------------------------------------------

    async def run(self, session: Session) -> WorkflowContext:
        """Execute the full pipeline, emitting WebSocket events."""
        start_time = time.time()

        context = WorkflowContext(
            requirements=session.prompt,
            mode=session.mode,
        )
        context.is_project_mode = session.is_project_mode
        context.project_name = session.project_name
        context.project_type = session.project_type

        session.context = context
        session.status = "running"

        # Initialize workspace
        run_paths = self.file_manager.ensure_run_dirs(self.output_dir, context.run_id)
        context.run_root = run_paths["run_root"]
        context.workspace_path = run_paths["workspace"]
        context.artifacts_path = run_paths["artifacts"]
        context.metrics_path = run_paths["metrics"]
        context.logs_path = run_paths["logs"]

        sid = session.session_id

        await ws.emit(sid, "pipeline_started", {
            "run_id": context.run_id,
            "mode": context.mode,
            "requirements": context.requirements,
        })

        # Define the emit_event callback for structured agent events
        def _emit_event_sync(event_type: str, data: Dict[str, Any]):
            # Use asyncio.run_coroutine_threadsafe if we were in a thread, 
            # but since emit_event is called from the thread (e.g. TesterAgent.execute),
            # we need to schedule it on the main event loop.
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(ws.emit(sid, event_type, data), loop)

        # However, tester.execute runs in a thread via to_thread.
        # We can pass an async loop to it, or just use a threadsafe wrapper.
        current_loop = asyncio.get_running_loop()
        def threadsafe_emit(event_type: str, data: Dict[str, Any]):
            asyncio.run_coroutine_threadsafe(ws.emit(sid, event_type, data), current_loop)
            
        context.emit_event = threadsafe_emit

        try:
            while context.retry_count <= context.max_retries:
                # ── A. CODER AGENT ──────────────────────────────
                await ws.emit(sid, "stage_update", {
                    "stage": "CODING",
                    "status": "in_progress",
                    "message": "Coder Agent is generating code…",
                })

                context = await asyncio.to_thread(self.coder.execute, context)

                if not context.success:
                    await ws.emit(sid, "stage_update", {
                        "stage": "CODING",
                        "status": "error",
                        "message": context.error_message or "Coder Agent failed",
                    })
                    await ws.emit(sid, "pipeline_complete", {
                        "status": "error",
                        "message": context.error_message or "Coder Agent failed",
                    })
                    session.status = "error"
                    return context

                # Persist files and notify frontend
                await asyncio.to_thread(self._persist_source, context)
                await self._emit_files(sid, context)

                await ws.emit(sid, "stage_update", {
                    "stage": "CODING",
                    "status": "complete",
                    "message": f"Generated {len(context.source_code)} file(s)",
                })

                # ── A.5. CODE REVIEW CHECKPOINT ─────────────────────
                action = await self._checkpoint(
                    session,
                    checkpoint_type="code_review",
                    message="Review the generated code before proceeding to testing.",
                    data=self._build_code_review_data(context),
                )
                logger.info("Checkpoint resolved with action=%s for session=%s", action, sid)

                if action == "reject":
                    session.status = "complete"
                    context.success = False
                    context.error_message = "User rejected the code."
                    await ws.emit(sid, "pipeline_complete", {
                        "status": "error",
                        "message": context.error_message,
                    })
                    return context
                elif action == "edit":
                    # Proceed to testing with whatever is in context
                    pass

                # ── B. TESTER AGENT ─────────────────────────────
                logger.info("Starting Tester Agent for session=%s", sid)
                await ws.emit(sid, "stage_update", {
                    "stage": "TESTING",
                    "status": "in_progress",
                    "message": "Tester Agent is starting...",
                })

                try:
                    context = await asyncio.to_thread(self.tester.execute, context)
                except Exception as tester_err:
                    logger.exception("Tester Agent crashed for session=%s: %s", sid, tester_err)
                    await ws.emit(sid, "stage_update", {
                        "stage": "TESTING",
                        "status": "error",
                        "message": f"Tester Agent crashed: {tester_err}",
                    })
                    await ws.emit(sid, "pipeline_complete", {
                        "status": "error",
                        "message": f"Tester Agent crashed: {tester_err}",
                    })
                    context.success = False
                    context.error_message = f"Tester Agent crashed: {tester_err}"
                    session.status = "error"
                    return context

                logger.info("Tester Agent finished for session=%s, success=%s", sid, context.success)

                if not context.success:
                    await ws.emit(sid, "stage_update", {
                        "stage": "TESTING",
                        "status": "error",
                        "message": context.error_message or "Tester Agent failed",
                    })
                    await ws.emit(sid, "pipeline_complete", {
                        "status": "error",
                        "message": context.error_message or "Tester Agent failed",
                    })
                    session.status = "error"
                    return context

                # ── Sync test files into context & emit to frontend ──
                await self._sync_test_files(sid, context)

                test_passed = context.test_results.get("passed", False)
                
                await ws.emit(sid, "test_results", {
                    "passed": test_passed,
                    "output": context.test_results.get("output", "")[:3000],
                    "coverage_line": context.test_results.get("coverage_line", 0),
                    "coverage_branch": context.test_results.get("coverage_branch", 0),
                    "duration": context.test_results.get("duration_seconds", 0),
                })

                if not test_passed:
                    await ws.emit(sid, "stage_update", {
                        "stage": "TESTING",
                        "status": "error",
                        "message": "Tests failed ✗. Analyzing and attempting to fix...",
                    })
                    # Auto-retry on test failure
                    context.retry_count += 1
                    if context.retry_count <= context.max_retries:
                        await ws.emit(sid, "log", {"message": f"Test failures detected. Looping back to Coder Agent to fix (Retry {context.retry_count}/{context.max_retries})…"})
                        continue
                    else:
                        await ws.emit(sid, "log", {"message": "Maximum retries reached. Proceeding with failing tests."})
                
                # Testing stage is completed via agent_completed event emitted by TesterAgent

                # If we get here, tests either passed or we maxed out retries.
                # Break out of the retry loop and proceed to Reviewer.
                break
            
            if context.retry_count > context.max_retries and not context.test_results.get("passed", False):
                # Optionally handle max retries failure mode here, but proceeding is fine
                pass

            # ── C. REVIEWER AGENT ───────────────────────────
            await ws.emit(sid, "stage_update", {
                "stage": "REVIEWING",
                "status": "in_progress",
                "message": "Reviewer Agent is analyzing code quality…",
            })

            context = await asyncio.to_thread(self.reviewer.execute, context)

            await ws.emit(sid, "review_report", {
                "issues": context.review_issues,
                "pylint_score": context.metrics.get("pylint_score", 0),
                "security_issues": context.metrics.get("security_issues", 0),
            })

            await ws.emit(sid, "stage_update", {
                "stage": "REVIEWING",
                "status": "complete",
                "message": f"Review complete — pylint {context.metrics.get('pylint_score', 'N/A')}/10",
            })

            # ── D. VALIDATOR AGENT ──────────────────────────
            await ws.emit(sid, "stage_update", {
                "stage": "VALIDATING",
                "status": "in_progress",
                "message": "Validator Agent is checking completeness…",
            })

            context = await asyncio.to_thread(self.validator.execute, context)

            await ws.emit(sid, "stage_update", {
                "stage": "VALIDATING",
                "status": "complete",
                "message": "Validation complete",
            })

            # ── E. METRICS & COMPLETION ─────────────────────
            self._aggregate_metrics(context, start_time)

            await ws.emit(sid, "metrics", {
                "total_time": context.metrics.get("total_time", 0),
                "attempts": context.metrics.get("attempts", 1),
                "coverage": context.metrics.get("coverage", 0),
                "pylint_score": context.metrics.get("pylint_score", 0),
                "files_count": context.metrics.get("files_count", 0),
                "llm_cost": str(context.metrics.get("llm_cost", {})),
            })

            # Auto-complete the pipeline
            context.stage = "COMPLETE"
            context.success = True
            session.status = "complete"

            await ws.emit(sid, "pipeline_complete", {
                "status": "success",
                "files": list(context.source_code.keys()),
                "metrics": context.metrics,
            })
            return context

        except Exception as e:
            logger.exception("Pipeline error in session %s", sid)
            session.status = "error"
            await ws.emit(sid, "pipeline_complete", {
                "status": "error",
                "message": str(e),
            })
            context.success = False
            context.error_message = str(e)
            return context

    # ------------------------------------------------------------------
    # Checkpoint helper — emits event, waits for user action via WS
    # ------------------------------------------------------------------

    async def _checkpoint(
        self,
        session: Session,
        checkpoint_type: str,
        message: str,
        data: Dict[str, Any],
    ) -> str:
        """Emit a checkpoint event and wait for the user to respond."""
        session.checkpoint_type = checkpoint_type
        session.checkpoint_event.clear()
        session.checkpoint_response = {}
        session.status = "checkpoint"

        logger.info(
            "Checkpoint emitted: type=%s session=%s — waiting for user response…",
            checkpoint_type, session.session_id,
        )

        await ws.emit(session.session_id, "checkpoint", {
            "checkpoint_type": checkpoint_type,
            "message": message,
            "data": data,
        })

        # Wait for the frontend to POST a response
        await session.checkpoint_event.wait()

        action = session.checkpoint_response.get("action", "approve")
        logger.info(
            "Checkpoint resolved: type=%s session=%s action=%s",
            checkpoint_type, session.session_id, action,
        )

        session.status = "running"
        return action

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _persist_source(self, context: WorkflowContext) -> None:
        """Write source files to workspace (runs in thread)."""
        for filename, code in context.source_code.items():
            self.file_manager.write_file(filename, code, directory=context.workspace_path)

    async def _emit_files(self, sid: str, context: WorkflowContext) -> None:
        """Notify frontend about generated files (skips already-emitted ones)."""
        for filename, code in context.source_code.items():
            if filename not in self._emitted_files and filename not in context.emitted_files:
                await ws.emit(sid, "file_created", {
                    "path": filename,
                    "content": code,
                    "language": self._detect_language(filename),
                })
                self._emitted_files.add(filename)
                context.emitted_files.add(filename)
            else:
                self._emitted_files.add(filename)

    async def _sync_test_files(self, sid: str, context: WorkflowContext) -> None:
        """Read test files written by TesterAgent from disk and emit them once."""
        test_dir = Path(context.workspace_path) / "tests"
        if not test_dir.exists():
            return

        for test_file in sorted(test_dir.glob("*.py")):
            rel_path = f"tests/{test_file.name}"
            if rel_path in context.emitted_files or rel_path in self._emitted_files:
                continue
            try:
                content = test_file.read_text(encoding="utf-8", errors="replace")
                context.test_code[rel_path] = content
                await ws.emit(sid, "file_created", {
                    "path": rel_path,
                    "content": content,
                    "language": self._detect_language(rel_path),
                })
                context.emitted_files.add(rel_path)
                self._emitted_files.add(rel_path)
                logger.info("Synced test file to frontend: %s", rel_path)
            except Exception as e:
                logger.warning("Failed to read test file %s: %s", rel_path, e)

    @staticmethod
    def _detect_language(filename: str) -> str:
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "tsx", ".jsx": "jsx", ".json": "json",
            ".md": "markdown", ".toml": "toml", ".yaml": "yaml",
            ".yml": "yaml", ".cfg": "ini", ".txt": "text",
        }
        for ext, lang in ext_map.items():
            if filename.endswith(ext):
                return lang
        return "text"

    @staticmethod
    def _build_code_review_data(context: WorkflowContext) -> Dict[str, Any]:
        files_preview = {}
        for filename, code in context.source_code.items():
            files_preview[filename] = {
                "content": code,
                "lines": len(code.splitlines()),
            }
        return {"files": files_preview}

    def _aggregate_metrics(self, context: WorkflowContext, start_time: float) -> None:
        context.metrics["total_time"] = round(time.time() - start_time, 2)
        context.metrics["attempts"] = context.retry_count + 1
        context.metrics["coverage"] = context.test_results.get(
            "coverage_line", context.test_results.get("coverage", 0)
        )
        context.metrics["coverage_line"] = context.test_results.get("coverage_line", 0)
        context.metrics["coverage_branch"] = context.test_results.get("coverage_branch", 0)
        context.metrics["files_count"] = len(context.source_code)
        context.metrics["llm_cost"] = self.cost_tracker.get_summary()

        if context.source_code:
            project_metrics = collect_file_metrics(
                context.source_code,
                context.test_results,
                context.review_issues,
            )
            context.metrics["per_file"] = metrics_to_per_file_list(project_metrics)
