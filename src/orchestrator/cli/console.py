import difflib
import io
import os
import sys
from typing import List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from ..config import settings

# Ensure stdout can handle Unicode (emojis/braille spinners) on Windows.
# Rich's legacy Windows renderer uses Win32 console API which encodes via
# cp1252 and crashes on characters outside that codepage.  By wrapping
# stdout.buffer in a UTF-8 TextIOWrapper and passing it to Console(file=...),
# Rich uses ANSI escape sequences instead of the Win32 renderer.
if sys.platform == "win32":
    _stdout_wrapper = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
    console = Console(file=_stdout_wrapper, force_terminal=True)
else:
    console = Console()


# ---------------------------------------------------------------------------
# Header / status helpers
# ---------------------------------------------------------------------------

def print_header():
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]AI Development Orchestrator[/bold cyan]\n[dim]Production Grade Pipeline[/dim]",
        border_style="blue"
    ))

def print_error(message: str):
    console.print(f"\n[bold red]❌ ERROR:[/bold red] {message}")

def print_success(message: str):
    console.print(f"\n[bold green]✅ SUCCESS:[/bold green] {message}")


# ---------------------------------------------------------------------------
# Code display
# ---------------------------------------------------------------------------

def display_code(filename: str, code: str):
    console.print(f"\n[bold]📄 File:[/bold] [cyan]{filename}[/cyan]")
    try:
        syntax = Syntax(code, "python", theme="monokai", line_numbers=True, word_wrap=False)
        # Wrap in a panel so long lines get cropped cleanly with visible overflow
        panel = Panel(
            syntax,
            title=filename,
            border_style="dim",
            padding=(0, 1),
            expand=False,
        )
        console.print(panel)
    except Exception:
        console.print(code)


# ---------------------------------------------------------------------------
# Diff display
# ---------------------------------------------------------------------------

def display_code_diff(old_code: str, new_code: str, filename: str, iteration: int = 0):
    """Show a color-coded unified diff between two code versions."""
    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"{filename} (previous)",
        tofile=f"{filename} (current)",
    ))

    if not diff_lines:
        console.print(f"[dim]No changes in {filename}[/dim]")
        return

    title = f"Changes in {filename}"
    if iteration:
        title += f" — Iteration {iteration}"

    diff_text = Text()
    for line in diff_lines:
        line_str = line.rstrip("\n")
        if line_str.startswith("+++") or line_str.startswith("---"):
            diff_text.append(line_str + "\n", style="bold")
        elif line_str.startswith("@@"):
            diff_text.append(line_str + "\n", style="cyan")
        elif line_str.startswith("+"):
            diff_text.append(line_str + "\n", style="green")
        elif line_str.startswith("-"):
            diff_text.append(line_str + "\n", style="red")
        else:
            diff_text.append(line_str + "\n")

    diff_text.no_wrap = True
    console.print(Panel(diff_text, title=title, border_style="yellow", expand=False))


# ---------------------------------------------------------------------------
# Feedback items display
# ---------------------------------------------------------------------------

def _truncate_description(text: str, max_lines: int = 4) -> str:
    """Truncate long descriptions to max_lines for table readability."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"


def display_feedback_items(items):
    """Display structured FeedbackItem list as a color-coded Rich Table."""
    if not items:
        return

    table = Table(
        title="📋 Feedback Items",
        show_header=True,
        header_style="bold magenta",
        border_style="blue",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Source", width=10)
    table.add_column("Severity", width=14)
    table.add_column("Location", width=22)
    table.add_column("What To Fix", min_width=30)
    table.add_column("Status", width=10, justify="center")

    severity_labels = {
        "critical": ("🔴 CRITICAL", "bold red"),
        "major":    ("🟡 MAJOR",    "yellow"),
        "minor":    ("🔵 MINOR",    "blue"),
        "suggestion": ("💡 SUGGESTION", "dim"),
    }

    for idx, item in enumerate(items, 1):
        label, style = severity_labels.get(item.severity, (item.severity.upper(), ""))
        status = "[green]✅ Fixed[/green]" if item.resolved else "[red]❌ Open[/red]"
        table.add_row(
            str(idx),
            item.source,
            f"[{style}]{label}[/{style}]",
            item.location or "—",
            _truncate_description(item.description),
            status,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Guardrail warnings display
# ---------------------------------------------------------------------------

def display_guardrail_warnings(warnings: List[str]):
    """Show guardrail warnings in a highlighted panel."""
    if not warnings:
        return
    content = "\n".join(f"⚠️  {w}" for w in warnings)
    console.print(Panel(content, title="🛡️ Guardrail Warnings", border_style="red"))


# ---------------------------------------------------------------------------
# Project tree display
# ---------------------------------------------------------------------------

def display_project_tree(tree_string: str, title: str = "Project Structure"):
    """Display the project directory tree using Rich."""
    if tree_string:
        console.print(Panel(tree_string, title=title, border_style="cyan"))


# ---------------------------------------------------------------------------
# Interactive file selector
# ---------------------------------------------------------------------------

def select_file_interactive(filenames: list) -> str:
    """Display a numbered list of files and let the user pick one or all."""
    console.print("\n[bold]Files:[/bold]")
    for idx, name in enumerate(filenames, 1):
        console.print(f"  [cyan]{idx}[/cyan]. {name}")
    console.print(f"  [cyan]0[/cyan]. [dim]All files[/dim]")

    while True:
        choice = console.input("[bold yellow]Select file number:[/bold yellow] ").strip()
        if choice.isdigit():
            num = int(choice)
            if num == 0:
                return "all"
            if 1 <= num <= len(filenames):
                return filenames[num - 1]
        console.print(f"[red]Invalid selection. Enter 0-{len(filenames)}[/red]")


# ---------------------------------------------------------------------------
# Human-in-the-loop prompt
# ---------------------------------------------------------------------------

def prompt_human_action(
    stage_name: str,
    allow_edit: bool = True,
    allow_skip: bool = False,
) -> Tuple[str, str]:
    """Prompt the human for a decision at a checkpoint.

    Returns:
        (action, feedback_text) where action is one of:
        "approve", "reject", "edit", "skip"
    """
    # Non-interactive override for test environments / CI
    if os.getenv("ORCHESTRATOR_AUTO_APPROVE", "").lower() in ("1", "true", "yes"):
        console.print(f"[dim]Auto-approving {stage_name} via ORCHESTRATOR_AUTO_APPROVE[/dim]")
        return "approve", ""
    options = "\\[a]pprove / \\[r]eject"
    valid = {"a", "approve", "r", "reject"}
    if allow_edit:
        options += " / \\[e]dit"
        valid.update({"e", "edit"})
    if allow_skip:
        options += " / \\[s]kip"
        valid.update({"s", "skip"})

    console.print()
    while True:
        choice = console.input(
            f"[bold yellow]{stage_name} — {options}:[/bold yellow] "
        ).lower().strip()
        if choice in valid:
            break
        console.print(f"[red]Invalid choice. Please enter one of: {options}[/red]")

    action_map = {"a": "approve", "r": "reject", "e": "edit", "s": "skip"}
    action = action_map.get(choice, choice)

    feedback_text = ""
    if action == "reject":
        feedback_text = console.input("[bold yellow]Enter feedback for the Coder Agent:[/bold yellow] ").strip()
    elif action == "edit":
        feedback_text = console.input("[bold yellow]Paste corrected code (or file path to read from):[/bold yellow] ").strip()

    return action, feedback_text


# ---------------------------------------------------------------------------
# Multi-line code input helper
# ---------------------------------------------------------------------------

def collect_multiline_code() -> str:
    """Collect multi-line code from the user until they type END on its own line."""
    console.print("[dim]Paste your code below. Type END on its own line when done:[/dim]")
    lines = []
    while True:
        line = console.input("")
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Metrics table
# ---------------------------------------------------------------------------

def display_metrics_table(metrics: dict):
    table = Table(title="📊 Pipeline Metrics Report", show_header=True, header_style="bold magenta", border_style="blue")
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Value", justify="right", style="green")
    table.add_column("Status", justify="center")

    # 1. Time
    total_time = metrics.get('total_time', 0)
    table.add_row("Execution Time", f"{total_time:.2f}s", "⏱️")

    # 2. Lines of Code
    loc = metrics.get('loc', 0)
    table.add_row("Lines of Code", str(loc), "📄")

    # 3. Files Generated
    files_count = metrics.get('files_count', 0)
    if files_count:
        table.add_row("Files Generated", str(files_count), "📁")

    # 4. Pylint Score — use config threshold
    score = metrics.get('pylint_score', 0)
    if score >= settings.MIN_PYLINT_SCORE + 1:
        score_status = "✅"
    elif score >= settings.MIN_PYLINT_SCORE:
        score_status = "🟡"
    else:
        score_status = "⚠️"
    table.add_row("Pylint Score", f"{score:.1f}/10", score_status)

    # 5. Test Coverage — use config threshold
    coverage = metrics.get('coverage_line', metrics.get('coverage', 0))
    if coverage >= settings.MIN_COVERAGE:
        cov_status = "✅"
    elif coverage > 0:
        cov_status = "🟡"
    else:
        cov_status = "❌"
    table.add_row("Line Coverage", f"{coverage}%", cov_status)
    branch_coverage = metrics.get("coverage_branch", 0)
    table.add_row("Branch Coverage", f"{branch_coverage}%", "ℹ️")

    # 6. Security
    sec = metrics.get('security_issues', 0)
    sec_status = "✅" if sec == 0 else "🚨"
    table.add_row("Security Warnings", str(sec), sec_status)

    # 7. Attempts
    attempts = metrics.get('attempts', 1)
    att_status = "✅" if attempts == 1 else "♻️"
    table.add_row("Auto-Fix Attempts", str(attempts), att_status)
    interventions = metrics.get("human_interventions", 0)
    table.add_row("Human Interventions", str(interventions), "👤")

    console.print(table)


# ---------------------------------------------------------------------------
# Per-file metrics table
# ---------------------------------------------------------------------------

def display_per_file_metrics(per_file_data: list):
    """Show coverage and quality per file."""
    if not per_file_data:
        return

    table = Table(
        title="📋 Per-File Metrics",
        show_header=True,
        header_style="bold magenta",
        border_style="blue",
    )
    table.add_column("File", style="cyan")
    table.add_column("Lines", justify="right")
    table.add_column("Coverage", justify="right")
    table.add_column("Pylint", justify="right")
    table.add_column("Issues", justify="right")

    for entry in per_file_data:
        coverage = entry.get("coverage", 0)
        cov_style = "green" if coverage >= settings.MIN_COVERAGE else "red"
        table.add_row(
            entry.get("filename", "—"),
            str(entry.get("lines", 0)),
            f"[{cov_style}]{coverage}%[/{cov_style}]",
            f"{entry.get('pylint_score', 0):.1f}",
            str(entry.get("issues", 0)),
        )

    console.print(table)


def display_validation_report(context):
    """Display the comprehensive pre-merge validation report."""
    report = context.validation_report
    if not report:
        return

    release = report.get("release", {})
    overall_status = release.get("status", "UNKNOWN")
    project_name = release.get("project_name", "unknown")

    if overall_status == "APPROVED":
        status_text = "[bold green]✅ APPROVED FOR MERGE[/bold green]"
        border = "green"
    else:
        status_text = "[bold yellow]⚠️ NEEDS ATTENTION[/bold yellow]"
        border = "yellow"

    # Header panel
    console.print(Panel(
        f"[bold]Project:[/bold] {project_name}  |  [bold]Attempt:[/bold] {release.get('attempt', 1)}\n"
        f"[bold]Status:[/bold] {status_text}",
        title="📋 Pre-Merge Validation Report",
        border_style=border,
        expand=False,
    ))

    # Quality Gates table
    gates = report.get("quality_gates", {}).get("gates", [])
    if gates:
        table = Table(
            title="Quality Gates",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
        )
        table.add_column("Gate", style="cyan", width=20)
        table.add_column("Status", justify="center", width=10)
        table.add_column("Detail", style="dim")

        for gate in gates:
            status = gate["status"]
            if status == "PASS":
                status_display = "[green]✅ PASS[/green]"
            elif status == "WARN":
                status_display = "[yellow]⚠️ WARN[/yellow]"
            else:
                status_display = "[red]❌ FAIL[/red]"
            table.add_row(gate["name"], status_display, gate.get("detail", ""))

        console.print(table)

    # Test summary
    tests = report.get("tests", {})
    if tests:
        console.print(f"\n🧪 [bold]Test Summary:[/bold] {tests.get('passed', 0)}/{tests.get('total', 0)} passed "
                       f"| Coverage: {tests.get('coverage', 0):.1f}% "
                       f"| Duration: {tests.get('duration', 0):.1f}s")

    # Documentation summary
    docs = report.get("docs", {})
    readme = docs.get("readme", {})
    if docs:
        readme_status = f"[green]✓[/green] ({readme.get('quality', 'unknown')})" if readme.get("exists") else "[red]✗ missing[/red]"
        docstrings = docs.get("docstrings", {})
        console.print(f"📝 [bold]Documentation:[/bold] README: {readme_status} "
                       f"| Docstrings: {docstrings.get('documented', 0)}/{docstrings.get('total_files', 0)} files")
        suggestions = readme.get("suggestions", [])
        if suggestions:
            for s in suggestions[:3]:
                console.print(f"   [dim]💡 {s}[/dim]")

    # Dependency summary
    deps = report.get("dependencies", {})
    if deps and deps.get("has_requirements"):
        pinned = "[green]✓ all pinned[/green]" if deps.get("pinned") else f"[yellow]⚠ {len(deps.get('unpinned', []))} unpinned[/yellow]"
        console.print(f"📦 [bold]Dependencies:[/bold] {pinned}")
        if deps.get("missing"):
            console.print(f"   [red]Missing from requirements: {', '.join(deps['missing'])}[/red]")

    # Release checklist
    checklist = release.get("checklist", [])
    if checklist:
        console.print(f"\n📝 [bold]Release Checklist[/bold]")
        for item in checklist:
            mark = "[green][x][/green]" if item["checked"] else "[red][ ][/red]"
            console.print(f"  {mark} {item['item']}")

    console.print()


def display_structured_test_report(context):
    """Display the detailed pipeline execution report."""
    results = context.test_results
    passed = results.get("passed", False)
    status_str = "[bold green]🟢 PASSED[/bold green]" if passed else f"[bold red]🔴 FAILED (Attempt {context.retry_count + 1})[/bold red]"
    
    console.print(f"\n📊 [bold]Pipeline Execution Report[/bold]")
    console.print(f"Status: {status_str}")
    
    coverage = results.get("coverage", 0)
    duration = results.get("duration_seconds", 0)
    console.print(f"Coverage: {coverage}%")
    console.print(f"Duration: {duration}s\n")

    rca_data = results.get("rca_data")
    if rca_data and "rca" in rca_data and rca_data["rca"]:
        table = Table(
            title="🔍 Root Cause Analysis (Grouped by Issue)",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
        )
        table.add_column("Issue Category", style="red", width=20)
        table.add_column("Impacted Tests", style="cyan", width=25)
        table.add_column("AI Diagnosis", style="yellow")
        
        for idx, item in enumerate(rca_data["rca"], 1):
            table.add_row(
                f"{idx}. {item.get('category', 'Unknown')}",
                item.get("impacted_tests", "Unknown"),
                item.get("diagnosis", "No diagnosis provided.")
            )
        console.print(table)
        console.print(f"\n🛠️ [bold]Recommended Next Steps[/bold]")
        console.print(rca_data.get("recommended_action", "No recommendation provided."))

    log_path = getattr(context, "last_test_log_path", None)
    if log_path:
        console.print(f"\n📂 [bold]Raw Logs & Artifacts[/bold]")
        console.print(f"Detailed traceback saved to: [cyan]{log_path}[/cyan]")


def display_summary_report(context, total_time: float):
    status = "[bold green]READY TO MERGE[/bold green]" if context.success else "[bold red]FAILED[/bold red]"
    report_content = f"""
[bold]Final Status:[/bold] {status}
[bold]Output Directory:[/bold] output/
"""
    console.print(Panel(report_content, title="🚀 Final Report", border_style="green" if context.success else "red"))
