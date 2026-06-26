import ast
import difflib
import re
from typing import Dict, List

from .context import FeedbackItem
from ..config import settings


def _group_line_ranges(line_numbers: List[int]) -> List[tuple]:
    """Group consecutive line numbers into (start, end) ranges.

    Lines within a gap of 2 are merged into the same range.
    E.g. [1,2,3,5,6,10] → [(1,6), (10,10)]
    """
    if not line_numbers:
        return []
    sorted_lines = sorted(line_numbers)
    ranges = []
    start = end = sorted_lines[0]
    for ln in sorted_lines[1:]:
        if ln - end <= 2:
            end = ln
        else:
            ranges.append((start, end))
            start = end = ln
    ranges.append((start, end))
    return ranges


def compute_diff(old_code: str, new_code: str, filename: str = "file.py") -> str:
    """Return a unified diff string between old and new code."""
    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}")
    return "".join(diff)


def changed_line_numbers(old_code: str, new_code: str) -> List[int]:
    """Return 1-based line numbers that were added or modified in new_code."""
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    changed = set()
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            for line_num in range(j1 + 1, j2 + 1):
                changed.add(line_num)
    return sorted(changed)


def validate_fix_scope(
    old_code: str,
    new_code: str,
    feedback_items: List[FeedbackItem],
    filename: str = "",
) -> List[str]:
    """Check whether code changes are scoped to locations mentioned in feedback.

    Returns a list of warning strings for any changes that fall outside
    the locations referenced by the feedback items.
    """
    changed = changed_line_numbers(old_code, new_code)
    if not changed:
        return []

    # Collect all referenced locations (line numbers and function names)
    referenced_lines: set = set()
    referenced_names: set = set()
    for item in feedback_items:
        if not item.location:
            continue
        # Parse "L15", "line 15", ":15" patterns
        line_matches = re.findall(r"[Ll](?:ine)?\s*(\d+)", item.location)
        for m in line_matches:
            line_no = int(m)
            # Allow a ±3-line window around referenced locations
            for offset in range(-3, 4):
                referenced_lines.add(line_no + offset)
        # Parse function/class names
        name_match = re.search(r"(\w+)\(\)", item.location)
        if name_match:
            referenced_names.add(name_match.group(1))

    # If no locations were specified in any feedback, can't scope-check
    if not referenced_lines and not referenced_names:
        return []

    # Map function names to their line ranges in the new code
    func_line_ranges: Dict[str, set] = {}
    try:
        tree = ast.parse(new_code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                end_line = getattr(node, "end_lineno", node.lineno + 20)
                func_line_ranges[node.name] = set(range(node.lineno, end_line + 1))
    except SyntaxError:
        pass

    # Expand referenced_lines with function body ranges
    for name in referenced_names:
        if name in func_line_ranges:
            referenced_lines.update(func_line_ranges[name])

    out_of_scope = [ln for ln in changed if ln not in referenced_lines]
    if not out_of_scope:
        return []

    # Group consecutive line numbers into ranges for readable warnings
    ranges = _group_line_ranges(out_of_scope)
    warnings = []
    for start, end in ranges:
        if start == end:
            warnings.append(f"Line {start} was changed but no feedback item references it")
        else:
            warnings.append(f"Lines {start}-{end} were changed but no feedback item references them")

    return warnings


def check_preservation(old_code: str, new_code: str) -> Dict[str, List[str]]:
    """Detect accidental deletions of functions, classes, or docstrings.

    Returns a dict with keys 'functions_removed', 'classes_removed',
    'docstrings_removed' listing names of removed elements.
    """
    report: Dict[str, List[str]] = {
        "functions_removed": [],
        "classes_removed": [],
        "docstrings_removed": [],
    }

    def _extract_names(code: str):
        funcs, classes, docstring_funcs = set(), set(), set()
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    funcs.add(node.name)
                    if (node.body and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)):
                        docstring_funcs.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.add(node.name)
        except SyntaxError:
            pass
        return funcs, classes, docstring_funcs

    old_funcs, old_classes, old_doc_funcs = _extract_names(old_code)
    new_funcs, new_classes, new_doc_funcs = _extract_names(new_code)

    report["functions_removed"] = sorted(old_funcs - new_funcs)
    report["classes_removed"] = sorted(old_classes - new_classes)
    report["docstrings_removed"] = sorted(old_doc_funcs - new_doc_funcs)

    return report


def guardrail_check(
    old_code: str,
    new_code: str,
    feedback_items: List[FeedbackItem],
    filename: str = "",
) -> List[str]:
    """Run all guardrail checks and return aggregated warnings."""
    warnings = []

    # 1. Scope validation
    scope_warnings = validate_fix_scope(old_code, new_code, feedback_items, filename)
    warnings.extend(scope_warnings)

    # 2. Preservation check
    preservation = check_preservation(old_code, new_code)
    for func in preservation["functions_removed"]:
        warnings.append(f"Function '{func}()' was removed — was this intentional?")
    for cls in preservation["classes_removed"]:
        warnings.append(f"Class '{cls}' was removed — was this intentional?")
    for func in preservation["docstrings_removed"]:
        warnings.append(f"Docstring for '{func}()' was removed")

    return warnings


def check_forbidden_operations(new_code: str) -> List[str]:
    patterns = {
        "os.system": r"\bos\.system\(",
        "subprocess_shell": r"\bsubprocess\.(run|Popen)\([^)]*shell\s*=\s*True",
        "eval": r"\beval\(",
        "exec": r"\bexec\(",
        "pickle_loads": r"\bpickle\.(load|loads)\(",
    }
    violations = []
    for name, pattern in patterns.items():
        if re.search(pattern, new_code):
            violations.append(f"Forbidden operation detected: {name}")
    return violations


def evaluate_guardrails(
    old_code: str,
    new_code: str,
    feedback_items: List[FeedbackItem],
    filename: str = "",
) -> Dict[str, List[str]]:
    warnings = guardrail_check(old_code, new_code, feedback_items, filename)
    violations = check_forbidden_operations(new_code)
    return {"warnings": warnings, "violations": violations}


def should_block_guardrail(violations: List[str]) -> bool:
    mode = getattr(settings, "GUARDRAIL_MODE", "hard_block")
    if mode == "warn":
        return False
    return bool(violations)
