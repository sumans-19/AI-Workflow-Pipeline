import os
from typing import List, Optional

import typer

from .cli import console
from .core.workflow import WorkflowOrchestrator
from .scaffold_templates import get_template
from .tools.file_manager import FileManager

app = typer.Typer(help="AI Development Orchestrator — Generate, validate, and complete Python projects.")


@app.command()
def generate(
    requirements: List[str] = typer.Argument(..., help="Requirements for code generation"),
    output_dir: str = typer.Option("output", "--output-dir", "-o", help="Base directory for run artifacts"),
):
    """Generate code from scratch based on requirements."""
    prompt_text = " ".join(requirements)
    console.print_header()
    console.console.print("[bold]Mode 1: AI Generation[/bold]")

    orchestrator = WorkflowOrchestrator(output_dir=output_dir)
    orchestrator.run(prompt_text, mode="GENERATE")


@app.command()
def validate(
    filepath: str = typer.Argument(..., help="Path to the Python file to validate"),
    output_dir: str = typer.Option("output", "--output-dir", "-o", help="Base directory for run artifacts"),
):
    """Validate and improve existing Python code."""
    console.print_header()
    console.console.print("[bold]Mode 2: Validation[/bold]")

    fm = FileManager()
    code = fm.read_file(filepath)
    filename = os.path.basename(filepath)

    orchestrator = WorkflowOrchestrator(output_dir=output_dir)
    orchestrator.run("Validate code", mode="VALIDATE", input_files={filename: code})


@app.command()
def complete(
    filepath: str = typer.Argument(..., help="Path to the skeleton Python file"),
    requirements: Optional[List[str]] = typer.Argument(None, help="Additional requirements"),
    output_dir: str = typer.Option("output", "--output-dir", "-o", help="Base directory for run artifacts"),
):
    """Complete a Python code skeleton."""
    prompt_text = " ".join(requirements) if requirements else "Implement logic."
    console.print_header()
    console.console.print("[bold]Mode 3: Hybrid[/bold]")

    fm = FileManager()
    code = fm.read_file(filepath)
    filename = os.path.basename(filepath)

    orchestrator = WorkflowOrchestrator(output_dir=output_dir)
    orchestrator.run(prompt_text, mode="HYBRID", input_files={filename: code})


@app.command()
def project(
    requirements: List[str] = typer.Argument(..., help="Project requirements description"),
    name: str = typer.Option(None, "--name", "-n", help="Project name (derived from requirements if omitted)"),
    type: str = typer.Option("library", "--type", "-t", help="Project type: fastapi|flask|cli|library|script"),
    output_dir: str = typer.Option("output", "--output-dir", "-o", help="Base output directory"),
):
    """Generate a complete Python project with full directory structure.

    Creates a production-ready project with proper package layout, tests,
    configuration files, and CI/CD pipeline.
    """
    project_name = name or _derive_project_name(requirements)
    prompt_text = (
        f"Project Name: {project_name}\n"
        f"Project Type: {type}\n"
        + " ".join(requirements)
    )

    console.print_header()
    console.console.print("[bold]Mode 4: Full Project Generation[/bold]")
    console.console.print(f"  Project: [cyan]{project_name}[/cyan]  Type: [cyan]{type}[/cyan]")

    orchestrator = WorkflowOrchestrator(output_dir=output_dir)
    orchestrator.run(
        prompt_text,
        mode="GENERATE",
        project_name=project_name,
        project_type=type,
        is_project_mode=True,
    )


@app.command()
def init(
    name: str = typer.Argument(..., help="Project name"),
    type: str = typer.Option("library", "--type", "-t", help="Project type: fastapi|flask|cli|library|script"),
    output_dir: str = typer.Option(".", "--output-dir", "-o", help="Parent directory for the project"),
    git: bool = typer.Option(True, "--git/--no-git", help="Initialize a git repository"),
):
    """Scaffold a new Python project with standard structure and config files.

    Creates a boilerplate project from a template — no LLM calls needed.
    """
    console.print_header()
    console.console.print(f"[bold]Scaffolding project:[/bold] [cyan]{name}[/cyan]  [bold]Type:[/bold] [cyan]{type}[/cyan]\n")

    try:
        template = get_template(type, name)
    except ValueError as e:
        console.console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    project_path = FileManager.create_project_structure(output_dir, name, template)

    if git:
        FileManager.git_init(project_path)

    tree = FileManager.build_project_tree(project_path)
    console.display_project_tree(tree, title="Generated Project Structure")

    console.console.print(f"\n[green]Project created at {project_path}[/green]")
    console.console.print("[dim]Next steps:[/dim]")
    console.console.print(f"[dim]  cd {name}[/dim]")
    console.console.print("[dim]  python -m venv .venv && source .venv/bin/activate[/dim]")
    console.console.print("[dim]  pip install -e .[/dim]")


def _derive_project_name(requirements: List[str]) -> str:
    """Derive a project name from the requirements text."""
    text = " ".join(requirements).lower()
    for keyword in ["build", "create", "make", "develop", "implement"]:
        if keyword in text:
            parts = text.split(keyword, 1)
            if len(parts) > 1:
                after = parts[1].strip().split()[0:3]
                return "_".join(w for w in after if w.isalnum())
    words = text.split()[:3]
    return "_".join(w for w in words if w.isalnum())


if __name__ == "__main__":
    app()
