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
            project_name=session.project_name or "generated_project",
            project_type=session.project_type or "library",
            is_project_mode=session.is_project_mode,
            test_execution_mode=session.test_execution_mode
        )
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
                test_majority = context.test_results.get("majority_passed", False)
                test_pass_rate = context.test_results.get("pass_rate", 0)

                await ws.emit(sid, "test_results", {
                    "passed": test_passed,
                    "majority_passed": test_majority,
                    "pass_rate": test_pass_rate,
                    "output": context.test_results.get("output", "")[:3000],
                    "coverage_line": context.test_results.get("coverage_line", 0),
                    "coverage_branch": context.test_results.get("coverage_branch", 0),
                    "duration": context.test_results.get("duration_seconds", 0),
                    "execution_mode": context.test_results.get("execution_mode", "unknown"),
                    "report_data": context.test_results.get("report_data", {}),
                    "rca_data": context.test_results.get("rca_data", {})
                })

                # ── ALWAYS show test_review checkpoint after testing (regardless of pass/fail) ──
                # The user must explicitly choose what happens next: Approve, Auto-Fix, Bypass, or Reject.
                # We always show the rich review content (summary, terminal output, RCA) so the user
                # can make an informed decision.
                raw_passed = context.test_results.get("raw_passed", test_passed)
                summary = (context.test_results.get("report_data", {}) or {}).get("summary", {}) or {}
                failed_count = int(summary.get("failed", 0) or 0)

                if test_passed and failed_count == 0:
                    stage_status = "complete"
                    stage_message = "All tests passed ✓. Waiting for user confirmation to proceed to Reviewer."
                    checkpoint_message = "All tests passed. Choose how to continue:"
                elif test_passed:
                    stage_status = "complete"
                    stage_message = (
                        f"Tests mostly passed ({test_pass_rate*100:.1f}%, "
                        f"{failed_count} edge-case failure(s)). Waiting for your review."
                    )
                    checkpoint_message = (
                        f"Most tests passed but {failed_count} edge-case failure(s) remain. "
                        "Review the tracebacks and choose an action."
                    )
                else:
                    stage_status = "error"
                    stage_message = "Tests failed ✗. Analysis complete. Waiting for user review..."
                    checkpoint_message = "Test failures detected. Review the tracebacks and root cause analysis below."

                await ws.emit(sid, "stage_update", {
                    "stage": "TESTING",
                    "status": stage_status,
                    "message": stage_message,
                })

                # ── Fire the checkpoint so user can choose an action ──
                action = await self._checkpoint(
                    session,
                    checkpoint_type="test_review",
                    message=checkpoint_message,
                    data={
                        "output": context.test_results.get("output", ""),
                        "rca_data": context.test_results.get("rca_data", {}),
                        "execution_mode": context.test_results.get("execution_mode", "unknown"),
                        "report_data": context.test_results.get("report_data", {}),
                        "passed": test_passed,
                        "majority_passed": test_majority,
                        "pass_rate": test_pass_rate,
                        "raw_passed": raw_passed,
                        "failed_count": failed_count,
                    }
                )

                logger.info("test_review action=%s session=%s", action, sid)

                # ── Reject: end the pipeline ──
                if action == "reject":
                    session.status = "complete"
                    context.success = False
                    context.error_message = "User rejected at test review."
                    await ws.emit(sid, "pipeline_complete", {
                        "status": "error",
                        "message": context.error_message,
                    })
                    return context

                # ── Bypass (Proceed): continue to Reviewer despite failures ──
                if action == "bypass":
                    logger.info("User bypassed failed tests for session=%s", sid)
                    await ws.emit(sid, "log", {"message": "→ Proceeding to Review phase (user bypassed)."})
                    await ws.emit(sid, "stage_update", {
                        "stage": "TESTING",
                        "status": "bypassed",
                        "message": "Testing bypassed by user — continuing to Reviewer."
                    })
                    break

                # ── Approve: accept current state and go to Reviewer (NOT back to Coder) ──
                if action == "approve":
                    logger.info("User approved tests for session=%s — proceeding to Reviewer", sid)
                    await ws.emit(sid, "log", {"message": "✓ Tests approved. Proceeding to Reviewer phase."})
                    await ws.emit(sid, "stage_update", {
                        "stage": "TESTING",
                        "status": "complete",
                        "message": "Tests approved — continuing to Reviewer"
                    })
                    break

                # ── Auto-Fix: convert RCA into FeedbackItems and loop back to Coder ──
                if action == "auto_fix":
                    rca_list = context.test_results.get("rca_data", {}).get("rca", []) or []
                    feedback_added = 0
                    if rca_list:
                        for rca in rca_list:
                            try:
                                context.add_feedback(FeedbackItem(
                                    run_id=context.run_id,
                                    checkpoint="TEST_REVIEW",
                                    source="tester",
                                    severity="critical",
                                    category="test",
                                    description=f"[{rca.get('category')}] {rca.get('why_it_happened')}\nSuggested Fix: {rca.get('suggested_fix')}",
                                    action="fix",
                                    status="open",
                                    author="tester",
                                    location=rca.get("caused_by_file")
                                ))
                                feedback_added += 1
                            except Exception as fe:
                                logger.warning("Failed to add RCA feedback item: %s", fe)
                    if feedback_added == 0:
                        context.add_feedback(FeedbackItem(
                            run_id=context.run_id,
                            checkpoint="TEST_REVIEW",
                            source="tester",
                            severity="critical",
                            category="test",
                            description="Tests failed. Please review the tracebacks and fix the underlying logic.",
                            action="fix",
                            status="open",
                            author="tester",
                        ))
                    await ws.emit(sid, "log", {
                        "message": f"🔧 Auto-Fix triggered. Looping back to Coder Agent to fix {max(feedback_added, 1)} issue(s)…"
                    })
                    context.retry_count += 1
                    if context.retry_count <= context.max_retries:
                        continue
                    else:
                        await ws.emit(sid, "log", {"message": "Maximum retries reached after Auto-Fix. Proceeding to Reviewer with failing tests."})
                        break

                # ── Retry Failed: re-run the tests without changing code ──
                if action == "retry":
                    await ws.emit(sid, "log", {"message": "Retrying failed tests (no code change)…"})
                    context.retry_count += 1
                    if context.retry_count <= context.max_retries:
                        continue
                    else:
                            await ws.emit(sid, "log", {"message": "Maximum retries reached after Retry. Proceeding to Reviewer."})
                            break

                    # Unknown action — fail safe by continuing to Reviewer
                    logger.warning("Unknown test_review action=%s — continuing to Reviewer", action)
                    await ws.emit(sid, "log", {"message": f"Unknown action '{action}'. Continuing to Reviewer."})
                    break
                
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

            # ── E. METRICS ─────────────────────────────────
            self._aggregate_metrics(context, start_time)

            await ws.emit(sid, "metrics", {
                "total_time": context.metrics.get("total_time", 0),
                "attempts": context.metrics.get("attempts", 1),
                "coverage": context.metrics.get("coverage", 0),
                "pylint_score": context.metrics.get("pylint_score", 0),
                "files_count": context.metrics.get("files_count", 0),
                "llm_cost": str(context.metrics.get("llm_cost", {})),
            })

            # ── F. FINAL REVIEW CHECKPOINT ──────────────────
            # Give the user a final review checkpoint where they can approve,
            # regenerate, or inspect the validator output before completion.
            action = await self._checkpoint(
                session,
                checkpoint_type="final_review",
                message="Final review: inspect the validation results and approve to complete.",
                data={
                    "metrics": context.metrics,
                    "review_issues": context.review_issues,
                    "validation_report": getattr(context, "validation_report", {}),
                    "files": list(context.source_code.keys()),
                },
            )
            logger.info("final_review action=%s session=%s", action, sid)

            if action == "reject":
                # User wants to reject from final review — record feedback and complete
                # (we're past the retry loop, so we just record the decision).
                context.add_feedback(FeedbackItem(
                    run_id=context.run_id,
                    checkpoint="FINAL_REVIEW",
                    source="human",
                    severity="major",
                    category="review",
                    description=session.checkpoint_response.get("feedback", "User rejected at final review."),
                    action="fix",
                    status="open",
                    author="human",
                ))
                context.success = False
                context.error_message = "User rejected at final review."
                await ws.emit(sid, "log", {"message": "✗ User rejected at final review. Pipeline ended."})
                session.status = "complete"
                context.stage = "REJECTED"
                await ws.emit(sid, "pipeline_complete", {
                    "status": "error",
                    "message": context.error_message,
                })
                return context

            # Approve / bypass / unknown → complete
            await ws.emit(sid, "log", {"message": "✓ Final review complete. Pipeline finished."})

            # ── G. COMPLETION ──────────────────────────────
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
