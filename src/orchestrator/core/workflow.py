import os
import time
from pathlib import Path

from rich.panel import Panel
from rich.syntax import Syntax

from .context import WorkflowContext, FeedbackItem
from .metrics import collect_file_metrics, metrics_to_per_file_list
from ..agents.coder import CoderAgent
from ..agents.tester import TesterAgent
from ..agents.reviewer import ReviewerAgent
from ..agents.validator import ValidatorAgent
from ..tools.file_manager import FileManager
from ..config import settings
from ..llm.cost_tracker import CostTracker
from ..llm.factory import create_llm_client
from ..logging_config import logger
from ..cli.console import (
    console,
    collect_multiline_code,
    display_code,
    display_code_diff,
    display_feedback_items,
    display_guardrail_warnings,
    display_metrics_table,
    display_per_file_metrics,
    display_validation_report,
    prompt_human_action,
    select_file_interactive,
    display_project_tree,
    display_structured_test_report,
)


class WorkflowOrchestrator:
    def __init__(
        self,
        output_dir: str = None,
        coder: CoderAgent = None,
        tester: TesterAgent = None,
        reviewer: ReviewerAgent = None,
        validator: ValidatorAgent = None,
        file_manager: FileManager = None,
    ):
        budget = settings.LLM_BUDGET_LIMIT_USD or None
        self.cost_tracker = CostTracker(budget_limit_usd=budget)
        llm = create_llm_client(cost_tracker=self.cost_tracker)
        self.coder = coder or CoderAgent(llm=llm)
        self.tester = tester or TesterAgent(llm=llm)
        self.reviewer = reviewer or ReviewerAgent(llm=llm)
        self.validator = validator or ValidatorAgent(llm=llm)
        self.file_manager = file_manager or FileManager()
        self.output_dir = output_dir or settings.RUNS_DIR

    # ==================================================================
    # MAIN WORKFLOW LOOP
    # ==================================================================

    def run(
        self,
        requirements: str,
        mode: str = "GENERATE",
        input_files: dict = None,
        project_name: str = "",
        project_type: str = "library",
        is_project_mode: bool = False,
    ):
        start_time = time.time()
        context = self._create_context(requirements, mode, input_files)
        context.is_project_mode = is_project_mode
        context.project_name = project_name
        context.project_type = project_type
        self._initialize_run_workspace(context)
        self._write_input_files(context, input_files)

        while context.retry_count <= context.max_retries:
            # ── A. CODER AGENT ─────────────────────────────────────
            if not self._execute_coding_stage(context):
                return context

            # ── B. CHECKPOINT 1 — Code Review ──────────────────────
            if self._checkpoint_code(context) == "reject":
                context.retry_count += 1
                console.print("\n[bold blue]↩ Looping back to Coder Agent with feedback...[/bold blue]\n")
                continue

            self._persist_source_to_workspace(context)

            # ── C. TESTER AGENT ─────────────────────────────────────
            if not self._execute_testing_stage(context):
                return context

            # ── D. CHECKPOINT 2 — Test Results ─────────────────────
            test_decision = self._checkpoint_tests(context)
            if test_decision == "reject":
                context.retry_count += 1
                console.print("\n[bold blue]↩ Looping back to Coder Agent to fix test issues...[/bold blue]\n")
                continue
            if test_decision == "skip":
                console.print("\n[yellow]⚠ Tests skipped by human — proceeding with warning.[/yellow]\n")

            # ── E. REVIEWER AGENT ──────────────────────────────────
            if not self._execute_review_stage(context):
                return context

            # ── F. VALIDATOR AGENT ─────────────────────────────────
            self._execute_validation_stage(context)

            # ── G. METRICS ─────────────────────────────────────────
            self._aggregate_metrics(context, start_time)

            # ── H. CHECKPOINT 3 — Final Review ─────────────────────
            final_decision = self._checkpoint_final(context)

            if final_decision in ("approve", "edit"):
                return self._finalize_run(context, start_time)

            console.print(f"\n[bold blue]♻️  Auto-Fix Triggered (Attempt {context.retry_count + 1})[/bold blue]")
            context.retry_count += 1

        return self._exhausted_retries(context)

    def run_autonomous_loop(self, context: WorkflowContext) -> WorkflowContext:
        MAX_RETRIES = 3
        attempt = 0

        while attempt <= MAX_RETRIES:
            # 1. Generate or Fix Code (Coder uses unresolved feedback automatically)
            context = self.coder.execute(context)
            
            # 2. Sync to Disk
            self._persist_source_to_workspace(context)
            
            # 3. Run the Tests
            context = self.tester.execute(context)
            
            # 4. Evaluate
            if context.success:
                console.print(f"[bold green]All tests passed on attempt {attempt + 1}![/bold green]")
                return context
                
            attempt += 1
            if attempt <= MAX_RETRIES:
                console.print(f"[bold yellow]Tests failed. Initiating auto-fix loop (Attempt {attempt}/{MAX_RETRIES})...[/bold yellow]")
            else:
                console.print("[bold red]Max auto-fix retries reached. Pipeline suspended.[/bold red]")
                break

        return context

    # ==================================================================
    # CONTEXT SETUP
    # ==================================================================

    def _create_context(self, requirements: str, mode: str, input_files: dict = None) -> WorkflowContext:
        context = WorkflowContext(requirements=requirements, mode=mode)
        if input_files and mode in ("VALIDATE", "HYBRID"):
            context.project_name = os.path.splitext(os.path.basename(list(input_files.keys())[0]))[0]
        return context

    def _initialize_run_workspace(self, context: WorkflowContext):
        run_paths = self.file_manager.ensure_run_dirs(self.output_dir, context.run_id)
        context.run_root = run_paths["run_root"]
        context.workspace_path = run_paths["workspace"]
        context.artifacts_path = run_paths["artifacts"]
        context.metrics_path = run_paths["metrics"]
        context.logs_path = run_paths["logs"]

    def _write_input_files(self, context: WorkflowContext, input_files: dict = None):
        if input_files:
            context.source_code = input_files
            for filename, code in input_files.items():
                self.file_manager.write_file(filename, code, directory=context.workspace_path)

    # ==================================================================
    # PIPELINE STAGES
    # ==================================================================

    def _execute_coding_stage(self, context: WorkflowContext) -> bool:
        context.stage = "CODING"
        agent_start = time.time()
        with console.status("[bold green]Coder Agent working...[/bold green]", spinner="dots"):
            context = self.coder.execute(context)
        context.metrics["coder_time"] = time.time() - agent_start

        if not context.success:
            console.print(f"\n[bold red]Coder Agent failed: {context.error_message}[/bold red]")
            return False

        # Project mode: write files to workspace and build tree
        if context.is_project_mode and context.source_code:
            self._persist_source_to_workspace(context)
            context.project_tree = self.file_manager.build_project_tree(context.workspace_path)

        return True

    def _execute_testing_stage(self, context: WorkflowContext) -> bool:
        context.stage = "TESTING"
        agent_start = time.time()
        with console.status("[bold green]Tester Agent running pytest...[/bold green]", spinner="runner"):
            context = self.tester.execute(context)
        context.metrics["tester_time"] = time.time() - agent_start

        if hasattr(context, "test_results") and context.test_results:
            self._save_test_log(context)

        if not context.success:
            console.print(f"\n[bold red]Tester Agent failed: {context.error_message}[/bold red]")
            return False
        return True

    def _save_test_log(self, context: WorkflowContext):
        output = context.test_results.get("output", "")
        passed = context.test_results.get("passed", False)
        
        log_dir = Path(context.logs_path)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        status_str = "passed" if passed else "failed"
        attempt = context.retry_count + 1
        log_filename = log_dir / f"attempt_{attempt}_pytest_{status_str}.log"
        
        with open(log_filename, "w", encoding="utf-8") as f:
            f.write(output)
            
        context.last_test_log_path = str(log_filename)

    def _execute_review_stage(self, context: WorkflowContext) -> bool:
        context.stage = "REVIEWING"
        agent_start = time.time()
        with console.status("[bold green]Reviewer Agent analyzing...[/bold green]", spinner="dots"):
            context = self.reviewer.execute(context)
        context.metrics["reviewer_time"] = time.time() - agent_start

        if not context.success:
            return context.success
        return True

    def _execute_validation_stage(self, context: WorkflowContext):
        context.stage = "VALIDATING"
        agent_start = time.time()
        with console.status("[bold green]Validator Agent checking...[/bold green]", spinner="toggle10"):
            context = self.validator.execute(context)
        context.metrics["validator_time"] = time.time() - agent_start

    def _persist_source_to_workspace(self, context: WorkflowContext):
        logger.info("Syncing generated code to physical workspace: %s", context.workspace_path)
        workspace_root = Path(context.workspace_path)

        for filename, code in context.source_code.items():
            self.file_manager.write_file(filename, code, directory=context.workspace_path)

        for root, dirs, files in os.walk(workspace_root):
            current_dir = Path(root)
            if current_dir.name.startswith("."):
                continue
            
            if current_dir != workspace_root:
                init_file = current_dir / "__init__.py"
                if not init_file.exists():
                    init_file.touch()
                    logger.debug("Auto-generated __init__.py in %s", current_dir)

    def _aggregate_metrics(self, context: WorkflowContext, start_time: float):
        context.metrics["total_time"] = time.time() - start_time
        context.metrics["attempts"] = context.retry_count + 1
        context.metrics["coverage"] = context.test_results.get("coverage_line", context.test_results.get("coverage", 0))
        context.metrics["coverage_line"] = context.test_results.get("coverage_line", 0)
        context.metrics["coverage_branch"] = context.test_results.get("coverage_branch", 0)
        context.metrics["human_interventions"] = len(context.human_actions)
        context.metrics["files_count"] = len(context.source_code)
        context.metrics["llm_cost"] = self.cost_tracker.get_summary()

        # Collect per-file metrics
        if context.source_code:
            project_metrics = collect_file_metrics(
                context.source_code,
                context.test_results,
                context.review_issues,
            )
            context.metrics["per_file"] = metrics_to_per_file_list(project_metrics)
            context.metrics["project_metrics"] = project_metrics

    # ==================================================================
    # CHECKPOINT 1 — Code Review
    # ==================================================================

    def _checkpoint_code(self, context: WorkflowContext) -> str:
        console.print(Panel(
            f"[bold]Checkpoint 1: Code Review  (Attempt {context.retry_count + 1}/{context.max_retries + 1})[/bold]",
            expand=False,
            border_style="yellow",
        ))

        # Show project tree if in project mode
        if context.is_project_mode and context.project_tree:
            display_project_tree(context.project_tree, title="Generated Project Structure")

        previous = context.previous_code()
        if previous:
            for filename, code in context.source_code.items():
                old = previous.get(filename, "")
                if old:
                    display_code_diff(old, code, filename, iteration=context.retry_count + 1)
                else:
                    display_code(filename, code)
        else:
            for filename, code in context.source_code.items():
                display_code(filename, code)

        if context.guardrail_warnings:
            display_guardrail_warnings(context.guardrail_warnings)

        resolved = [f for f in context.feedback_items if f.resolved]
        if resolved:
            console.print(f"\n[dim]({len(resolved)} feedback items marked resolved this iteration)[/dim]")

        action, feedback_text = prompt_human_action("Code Review", allow_edit=True)
        context.add_human_action("CODE_REVIEW", action, feedback_text)

        if action == "reject" and feedback_text:
            context.feedback_items.append(FeedbackItem(
                source="human",
                severity="major",
                description=feedback_text,
                action="fix",
            ))

        if action == "edit":
            self._handle_human_edit(context, feedback_text)
            return "edit"

        return action

    # ==================================================================
    # CHECKPOINT 2 — Test Results
    # ==================================================================

    def _checkpoint_tests(self, context: WorkflowContext) -> str:
        console.print(Panel(
            f"[bold]Checkpoint 2: Test Results  (Attempt {context.retry_count + 1}/{context.max_retries + 1})[/bold]",
            expand=False,
            border_style="yellow",
        ))

        display_structured_test_report(context)

        console.print(
            "\n[dim]Tip: [e]dit to paste your own test code, "
            "[r]eject to ask AI to rewrite tests, "
            "[s]kip to proceed without tests[/dim]"
        )

        action, feedback_text = prompt_human_action(
            "Test Results",
            allow_edit=True,
            allow_skip=True,
        )

        context.add_human_action("TEST_REVIEW", action, feedback_text)

        if action == "reject" and feedback_text:
            context.feedback_items.append(FeedbackItem(
                source="human",
                severity="critical",
                description=f"Tests rejected: {feedback_text}",
                action="fix",
            ))

        if action == "edit":
            self._handle_human_test_edit(context, feedback_text)

        return action

    # ==================================================================
    # CHECKPOINT 3 — Final Review
    # ==================================================================

    def _checkpoint_final(self, context: WorkflowContext) -> str:
        console.print(Panel(
            f"[bold]Checkpoint 3: Final Review  (Attempt {context.retry_count + 1}/{context.max_retries + 1})[/bold]",
            expand=False,
            border_style="yellow",
        ))

        display_metrics_table(context.metrics)

        # Show per-file metrics if available
        if context.metrics.get("per_file"):
            display_per_file_metrics(context.metrics["per_file"])

        # Show the new structured validation report
        display_validation_report(context)

        if not context.test_results.get("passed"):
            console.print(Panel(
                context.test_results.get("output", ""),
                title="Test Failures",
                border_style="red",
            ))

        if context.review_issues:
            full_report = "\n".join(context.review_issues)
            console.print(Panel(full_report, title="Code Review Report", border_style="blue"))

        unresolved = context.unresolved_feedback()
        if unresolved:
            display_feedback_items(unresolved)

        action, feedback_text = prompt_human_action("Final Review", allow_edit=True)
        context.add_human_action("FINAL_REVIEW", action, feedback_text)

        if action == "reject" and feedback_text:
            msg = "User rejected final review."
            if not context.test_results.get("passed"):
                msg += " Tests failed."
            if context.metrics.get("coverage", 0) < settings.MIN_COVERAGE:
                msg += f" Coverage too low ({context.metrics['coverage']}%)."
            if context.metrics.get("pylint_score", 0) < settings.MIN_PYLINT_SCORE:
                msg += f" Pylint score too low ({context.metrics['pylint_score']})."
            msg += f" User note: {feedback_text}"
            context.feedback_items.append(FeedbackItem(
                source="human",
                severity="major",
                description=msg,
                action="fix",
            ))

        if action == "edit":
            self._handle_human_edit(context, feedback_text)
            return "edit"

        return action

    # ==================================================================
    # Human edit helpers
    # ==================================================================

    def _handle_human_edit(self, context: WorkflowContext, text: str):
        filenames = list(context.source_code.keys())
        if len(filenames) == 1:
            targets = [filenames[0]]
        else:
            selected = select_file_interactive(filenames)
            targets = [selected] if selected != "all" else filenames

        for target in targets:
            new_code = self._get_edit_code(target, context.source_code.get(target, ""), text)
            if new_code:
                CoderAgent.apply_human_edit(context, target, new_code)
                console.print(f"[green]✅ Code for {target} updated with your edit.[/green]")

    def _handle_human_test_edit(self, context: WorkflowContext, text: str):
        filenames = list(context.source_code.keys())
        test_filename = f"test_{filenames[0]}" if filenames else "test_main.py"

        new_test_code = ""
        if text and os.path.isfile(text):
            with open(text, "r", encoding="utf-8") as f:
                new_test_code = f.read()
            console.print(f"[green]Read test code from {text}[/green]")
        elif text and len(text) > 20:
            new_test_code = text
        else:
            console.print(f"\n[bold]Editing: [cyan]{test_filename}[/cyan][/bold]")
            new_test_code = collect_multiline_code()

        if new_test_code.strip():
            self.file_manager.write_file(test_filename, new_test_code, directory=context.workspace_path)
            console.print(f"[green]✅ Test file {test_filename} updated.[/green]")

            console.print("[bold green]Re-running pytest with your tests...[/bold green]")
            from ..tools.python_runner import PythonRunner
            runner = PythonRunner()
            context.test_results = runner.run_pytest(context.workspace_path)
            success = context.test_results["passed"]
            result_str = "[bold green]PASSED[/bold green]" if success else "[bold red]FAILED[/bold red]"
            console.print(f"Re-run result: {result_str}")

    def _get_edit_code(self, filename: str, current_code: str, text: str) -> str:
        if text and os.path.isfile(text):
            with open(text, "r", encoding="utf-8") as f:
                code = f.read()
            console.print(f"[green]Read code from {text}[/green]")
            return code
        elif text and len(text) > 20:
            return text
        else:
            console.print(f"\n[bold]Editing: [cyan]{filename}[/cyan][/bold]")
            console.print(f"[dim]Current content shown above. Paste new code below.[/dim]")
            return collect_multiline_code()

    # ==================================================================
    # Finalization
    # ==================================================================

    def _finalize_run(self, context: WorkflowContext, start_time: float) -> WorkflowContext:
        if context.retry_count > 0:
            self._persist_source_to_workspace(context)

        context.stage = "COMPLETE"
        console.clear()
        console.print("[bold green]🚀 PIPELINE COMPLETE[/bold green]\n")

        # Show project tree if project mode
        if context.is_project_mode and context.project_tree:
            display_project_tree(context.project_tree, title="Generated Project Structure")

        for filename, code in context.source_code.items():
            syntax = Syntax(code, "python", theme="monokai", line_numbers=True, word_wrap=False)
            panel = Panel(
                syntax,
                title=f"Final Output: {filename}",
                border_style="green",
                padding=(0, 1),
                expand=False,
            )
            console.print(panel)

        console.print()
        display_metrics_table(context.metrics)
        if context.metrics.get("per_file"):
            console.print()
            display_per_file_metrics(context.metrics["per_file"])

        console.print()
        console.print(Panel("[bold green]STATUS: READY TO MERGE[/bold green]", border_style="green"))
        context.success = True
        self._persist_run_artifacts(context)

        # Generate HTML report
        try:
            from ..reports.html_report import generate_html_report
            report_path = generate_html_report(
                context,
                os.path.join(context.artifacts_path, "report.html"),
            )
            logger.info("HTML report generated: %s", report_path)
        except Exception as e:
            logger.warning("Failed to generate HTML report: %s", e)

        return context

    def _exhausted_retries(self, context: WorkflowContext) -> WorkflowContext:
        context.stage = "REJECTED"
        self._persist_run_artifacts(context)
        console.print("\n[bold red]❌ MAX RETRIES REACHED.[/bold red]")
        return context

    def _persist_run_artifacts(self, context: WorkflowContext):
        self.file_manager.write_json("summary.json", {
            "run_id": context.run_id,
            "stage": context.stage,
            "attempts": context.retry_count + 1,
            "success": context.success,
            "current_step": context.current_step,
            "workspace_path": context.workspace_path,
        }, context.artifacts_path)
        self.file_manager.write_json("feedback.json", [
            item.__dict__ for item in context.feedback_items
        ], context.artifacts_path)
        self.file_manager.write_json("metrics.json", context.metrics, context.metrics_path)
        if context.validation_report:
            self.file_manager.write_json("validation_report.json", context.validation_report, context.artifacts_path)
