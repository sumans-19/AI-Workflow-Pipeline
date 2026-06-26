"""Per-file and project-level metrics collection."""

import ast
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FileMetrics:
    filename: str
    lines_of_code: int = 0
    function_count: int = 0
    class_count: int = 0
    complexity: int = 0
    coverage_line: float = 0.0
    pylint_score: float = 0.0
    issues_count: int = 0


@dataclass
class ProjectMetrics:
    files: List[FileMetrics] = field(default_factory=list)
    total_loc: int = 0
    avg_coverage: float = 0.0
    avg_pylint: float = 0.0
    total_issues: int = 0
    test_count: int = 0
    source_file_count: int = 0


def _count_complexity(code: str) -> int:
    """Estimate cyclomatic complexity by counting branch points via AST."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0
    complexity = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += len(node.values) - 1
    return complexity


def _count_definitions(code: str) -> tuple:
    """Return (function_count, class_count) from source code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0, 0
    funcs = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    return funcs, classes


def _count_test_functions(code: str) -> int:
    """Count test functions in a test file."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0
    return sum(
        1 for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name.startswith("test_")
    )


def collect_file_metrics(
    source_code: Dict[str, str],
    test_results: Dict,
    review_issues: List[str],
) -> ProjectMetrics:
    """Collect comprehensive metrics from all pipeline outputs."""
    project = ProjectMetrics()
    output = test_results.get("output", "")

    # Parse per-file coverage from pytest-cov output
    per_file_coverage: Dict[str, float] = {}
    for match in re.finditer(r"^(\S+\.py)\s+.*?\s+(\d+)%\s", output, re.MULTILINE):
        per_file_coverage[match.group(1)] = float(match.group(2))

    for filename, code in source_code.items():
        if filename.startswith("tests/") or filename.startswith("test_"):
            project.test_count += _count_test_functions(code)
            continue

        project.source_file_count += 1
        funcs, classes = _count_definitions(code)
        lines = len(code.splitlines())
        complexity = _count_complexity(code)

        # Get coverage for this specific file
        coverage = per_file_coverage.get(filename, 0.0)

        # Count issues that mention this file
        issues = sum(1 for issue in review_issues if filename in issue)

        fm = FileMetrics(
            filename=filename,
            lines_of_code=lines,
            function_count=funcs,
            class_count=classes,
            complexity=complexity,
            coverage_line=coverage,
            issues_count=issues,
        )
        project.files.append(fm)
        project.total_loc += lines

    if project.files:
        project.avg_coverage = sum(f.coverage_line for f in project.files) / len(project.files)

    return project


def metrics_to_per_file_list(project_metrics: ProjectMetrics) -> List[Dict]:
    """Convert ProjectMetrics to a list of dicts for display."""
    return [
        {
            "filename": fm.filename,
            "lines": fm.lines_of_code,
            "functions": fm.function_count,
            "classes": fm.class_count,
            "complexity": fm.complexity,
            "coverage": fm.coverage_line,
            "issues": fm.issues_count,
        }
        for fm in project_metrics.files
    ]
