"""Planning agent data models.

Defines the structure of an implementation plan produced by the Planning Agent
and the registry of all 15 selectable planning modules. Each module is
optional — the user picks which ones to include from the Planning
Configuration UI, and the LLM is instructed to only emit those.

A `PlanningDocument` is the root dataclass returned by the agent. Every
sub-module is a typed dataclass (Optional), so unchecked modules are simply
`None` rather than missing keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────
# Registry of all 15 planning modules.
# Order is the canonical order used in the configuration UI, the
# prompt template, and the markdown renderer.
# ─────────────────────────────────────────────────────────────

PLANNING_MODULES: List[Dict[str, str]] = [
    {
        "id": "project_understanding",
        "label": "Project Understanding",
        "description": "Identify project type, complexity, assumptions, and ambiguous requirements.",
        "icon": "Lightbulb",
    },
    {
        "id": "functional_requirements",
        "label": "Functional Requirements",
        "description": "Core, secondary, optional, and future features.",
        "icon": "ListChecks",
    },
    {
        "id": "folder_structure",
        "label": "Folder Structure",
        "description": "Complete directory tree the Coder must respect.",
        "icon": "FolderTree",
    },
    {
        "id": "architecture_design",
        "label": "Architecture Design",
        "description": "Architecture pattern (MVC, Clean, Hexagonal, etc.) with rationale.",
        "icon": "Building2",
    },
    {
        "id": "component_breakdown",
        "label": "Component Breakdown",
        "description": "Modules, classes, services, interfaces, and their purposes.",
        "icon": "Boxes",
    },
    {
        "id": "dependency_planning",
        "label": "Dependency Planning",
        "description": "Python packages, frameworks, and runtime requirements with reasoning.",
        "icon": "Package",
    },
    {
        "id": "data_flow",
        "label": "Data Flow",
        "description": "High-level execution flow from input to output.",
        "icon": "Workflow",
    },
    {
        "id": "file_responsibilities",
        "label": "File Responsibilities",
        "description": "Responsibility of every planned file (entry point, services, utils, etc.).",
        "icon": "FileText",
    },
    {
        "id": "api_planning",
        "label": "API Planning",
        "description": "Endpoints, HTTP methods, request/response models, auth. (Only if applicable.)",
        "icon": "Globe",
    },
    {
        "id": "database_planning",
        "label": "Database Planning",
        "description": "DB choice, tables, entities, relationships, indexes, ORM models.",
        "icon": "Database",
    },
    {
        "id": "security_considerations",
        "label": "Security Considerations",
        "description": "Input validation, auth, secret management, error handling, logging, rate-limiting.",
        "icon": "Shield",
    },
    {
        "id": "testing_strategy",
        "label": "Testing Strategy",
        "description": "Unit, integration, e2e, edge cases, mocking, coverage goals.",
        "icon": "TestTube",
    },
    {
        "id": "code_standards",
        "label": "Code Standards",
        "description": "Naming, organization, type hints, docstrings, comments, formatting.",
        "icon": "Code",
    },
    {
        "id": "risks_challenges",
        "label": "Risks & Challenges",
        "description": "Technical risks, dependency conflicts, scalability, performance, mitigations.",
        "icon": "AlertTriangle",
    },
    {
        "id": "execution_roadmap",
        "label": "Execution Roadmap",
        "description": "Step-by-step implementation order (scaffold → models → services → tests).",
        "icon": "Map",
    },
]


# ─────────────────────────────────────────────────────────────
# 15 typed sub-modules. All Optional so unchecked modules are None.
# ─────────────────────────────────────────────────────────────


@dataclass
class ProjectUnderstanding:
    summary: str = ""
    project_type: str = ""               # CLI / API / Web / Library / AI / Mobile / Desktop
    complexity: str = ""                 # simple / moderate / complex / enterprise
    assumptions: List[str] = field(default_factory=list)
    ambiguous_requirements: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)
    missing_requirements_suggested: List[str] = field(default_factory=list)


@dataclass
class FunctionalRequirements:
    core_features: List[str] = field(default_factory=list)
    secondary_features: List[str] = field(default_factory=list)
    optional_features: List[str] = field(default_factory=list)
    future_enhancements: List[str] = field(default_factory=list)


@dataclass
class FolderStructure:
    tree: str = ""                       # ASCII tree of the planned directory layout
    notes: str = ""                      # Conventions & rationale

    # Minimum-files policy
    DEFAULT_MAX_SOURCE_FILES = 10        # hard cap for typical projects
    SOFT_MAX_SOURCE_FILES    = 8         # typical default
    DEFAULT_MAX_TEST_FILES   = 10        # at most 1 test_*.py per source + conftest + __init__

    # ── Convenience helpers ────────────────────────────────────────────
    def parsed_paths(self) -> List[str]:
        """Return the list of file paths implied by the ASCII tree.

        Empty tree → empty list. The parser is tolerant of common tree
        notations (`├──`, `└──`, `│`, plain indentation).
        """
        return parse_tree(self.tree)

    def planned_source_files(self) -> List[str]:
        """File paths from the tree that should be implemented as Python source.

        Only ``.py`` files are returned; non-Python source files
        (``.html``, ``.js``, ``.css`` etc.) are filtered out and a
        warning is logged. Config files (``pyproject.toml``,
        ``requirements.txt``, …) are excluded too — they don't need
        Coder-generated code.

        If the LLM over-generated (>10 files) we cap at the highest
        priority files so the Coder doesn't have a 4,000-line backlog.
        """
        out: List[str] = []
        paths = self.parsed_paths()
        from ..logging_config import logger as _logger
        for p in paths:
            # Directory entries (e.g. ``calculator/src``) don't have a
            # file extension — quietly skip them.
            if not Path(p).suffix and "/" in p:
                continue
            if p.endswith("/"):
                continue
            if is_doc_or_config(p):
                continue
            if is_test_path(p):
                continue
            if not is_python_source(p):
                _logger.warning(
                    "FolderStructure: dropping non-Python planned source %r — "
                    "the project is Python-only.", p,
                )
                continue
            out.append(p)

        # ── Server-side cap (safety net) ────────────────────────────
        if len(out) > self.DEFAULT_MAX_SOURCE_FILES:
            kept = out[: self.DEFAULT_MAX_SOURCE_FILES]
            dropped_count = len(out) - len(kept)
            _logger.warning(
                "FolderStructure: planned_source_files returned %d files — "
                "capping at the first %d per the minimal-files policy. "
                "Dropped %d lower-priority file(s). Ask the planner to refine "
                "the tree if those files are required.",
                len(out), self.DEFAULT_MAX_SOURCE_FILES, dropped_count,
            )
            return kept
        return out

    def planned_test_files(self) -> List[str]:
        """File paths from the tree that the Tester Agent should generate.

        Only ``.py`` test files (``test_*.py`` or files under ``tests/``)
        are returned. ``conftest.py`` and ``__init__.py`` under tests/
        are included. Capped at ``DEFAULT_MAX_TEST_FILES`` to honour the
        minimal-files policy.
        """
        out: List[str] = []
        paths = self.parsed_paths()
        from ..logging_config import logger as _logger
        for p in paths:
            # Directory entries (e.g. ``myapp/tests/unit``) don't have a
            # file extension — quietly skip them.
            if not Path(p).suffix and "/" in p:
                continue
            if p.endswith("/"):
                continue
            if not is_test_path(p):
                continue
            if not is_python_source(p):
                _logger.warning(
                    "FolderStructure: dropping non-Python planned test %r — "
                    "tests must be .py files.", p,
                )
                continue
            out.append(p)

        if len(out) > self.DEFAULT_MAX_TEST_FILES:
            kept = out[: self.DEFAULT_MAX_TEST_FILES]
            dropped = len(out) - len(kept)
            _logger.warning(
                "FolderStructure: planned_test_files returned %d files — "
                "capping at the first %d per the minimal-files policy.",
                len(out), self.DEFAULT_MAX_TEST_FILES, dropped,
            )
            return kept
        return out

    def planned_dirs(self) -> List[str]:
        """Unique directory paths referenced by the tree."""
        dirs: set = set()
        for p in self.parsed_paths():
            parent = str(Path(p).parent)
            if parent and parent != ".":
                dirs.add(parent)
        return sorted(dirs)

    def test_root(self) -> Optional[str]:
        """Best-effort guess at the directory tests should live in.

        Looks for the first directory whose name starts with ``test``
        (e.g. ``tests``, ``test``, ``tests/unit``). Falls back to
        ``tests`` if no such directory was planned.
        """
        for d in self.planned_dirs():
            base = d.split("/")[-1].lower()
            if base in {"tests", "test"} or base.startswith("test"):
                return d
        return "tests"


@dataclass
class ArchitectureDesign:
    pattern: str = ""                    # Layered / MVC / MVVM / Clean / Modular / Microservices / EventDriven / Hexagonal / DDD
    rationale: str = ""
    diagram: str = ""                    # Optional ASCII / Mermaid diagram


@dataclass
class ComponentBreakdown:
    modules: List[str] = field(default_factory=list)
    packages: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    utilities: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    models: List[str] = field(default_factory=list)
    apis: List[str] = field(default_factory=list)
    configurations: List[str] = field(default_factory=list)
    purpose_by_component: Dict[str, str] = field(default_factory=dict)


@dataclass
class DependencyPlanning:
    python_packages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    third_party_libraries: List[str] = field(default_factory=list)
    runtime_requirements: List[str] = field(default_factory=list)
    development_dependencies: List[str] = field(default_factory=list)
    build_tools: List[str] = field(default_factory=list)
    reasoning: Dict[str, str] = field(default_factory=dict)


@dataclass
class DataFlow:
    flow_diagram: str = ""               # ASCII / text diagram
    steps: List[str] = field(default_factory=list)


@dataclass
class FileResponsibility:
    responsibilities: Dict[str, str] = field(default_factory=dict)
    """{filename: purpose}"""


@dataclass
class APIPlanning:
    applicable: bool = False
    endpoints: List[Dict[str, Any]] = field(default_factory=list)
    """[{"path": "/users", "method": "GET", "request_model": "...", "response_model": "..."}]"""
    authentication: str = ""
    authorization: str = ""
    validation: List[str] = field(default_factory=list)
    error_responses: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class DatabasePlanning:
    applicable: bool = False
    database: str = ""                   # sqlite / postgres / mysql / mongodb / redis / none
    tables: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    relationships: List[str] = field(default_factory=list)
    schemas: Dict[str, str] = field(default_factory=dict)
    """{table_name: schema_definition}"""
    indexes: List[str] = field(default_factory=list)
    orm_models: List[str] = field(default_factory=list)


@dataclass
class SecurityConsiderations:
    input_validation: List[str] = field(default_factory=list)
    authentication: List[str] = field(default_factory=list)
    authorization: List[str] = field(default_factory=list)
    secret_management: List[str] = field(default_factory=list)
    environment_variables: List[str] = field(default_factory=list)
    exception_handling: List[str] = field(default_factory=list)
    logging: List[str] = field(default_factory=list)
    rate_limiting: List[str] = field(default_factory=list)
    best_practices: List[str] = field(default_factory=list)


@dataclass
class TestingStrategy:
    unit_tests: List[str] = field(default_factory=list)
    integration_tests: List[str] = field(default_factory=list)
    end_to_end_tests: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)
    negative_tests: List[str] = field(default_factory=list)
    mocking_strategy: str = ""
    coverage_goal: str = ""


@dataclass
class CodeStandards:
    naming_conventions: str = ""
    folder_organization: str = ""
    type_hints: str = ""
    documentation_style: str = ""
    docstrings: str = ""
    comments: str = ""
    logging: str = ""
    error_handling: str = ""
    formatting_rules: str = ""


@dataclass
class RisksChallenges:
    technical_risks: List[str] = field(default_factory=list)
    dependency_conflicts: List[str] = field(default_factory=list)
    difficult_modules: List[str] = field(default_factory=list)
    scalability_concerns: List[str] = field(default_factory=list)
    performance_bottlenecks: List[str] = field(default_factory=list)
    mitigation_strategies: List[str] = field(default_factory=list)


@dataclass
class ExecutionRoadmap:
    steps: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Root document
# ─────────────────────────────────────────────────────────────


@dataclass
class PlanningDocument:
    """The complete implementation blueprint produced by the Planning Agent.

    Each field is the (optional) dataclass for one of the 15 modules.
    Unchecked modules remain `None`.
    """
    project_understanding:   Optional[ProjectUnderstanding]   = None
    functional_requirements: Optional[FunctionalRequirements] = None
    folder_structure:        Optional[FolderStructure]        = None
    architecture_design:     Optional[ArchitectureDesign]     = None
    component_breakdown:     Optional[ComponentBreakdown]     = None
    dependency_planning:     Optional[DependencyPlanning]     = None
    data_flow:               Optional[DataFlow]               = None
    file_responsibilities:   Optional[FileResponsibility]     = None
    api_planning:            Optional[APIPlanning]            = None
    database_planning:       Optional[DatabasePlanning]       = None
    security_considerations: Optional[SecurityConsiderations] = None
    testing_strategy:        Optional[TestingStrategy]        = None
    code_standards:          Optional[CodeStandards]          = None
    risks_challenges:        Optional[RisksChallenges]        = None
    execution_roadmap:       Optional[ExecutionRoadmap]       = None

    # ── Metadata ──
    generated_at: float = 0.0
    requirements: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-safe dict. None values are kept (so the frontend
        can detect which modules were generated)."""
        return asdict(self)

    def selected_module_ids(self) -> List[str]:
        """Return the list of module IDs that have non-None content."""
        out = []
        for mod in PLANNING_MODULES:
            if getattr(self, mod["id"], None) is not None:
                out.append(mod["id"])
        return out

    def to_markdown(self) -> str:
        """Render the plan as readable markdown for the textarea edit view."""
        lines: List[str] = [f"# Implementation Plan\n"]
        if self.requirements:
            lines.append(f"**Requirements:** {self.requirements}\n")
        for mod in PLANNING_MODULES:
            data = getattr(self, mod["id"], None)
            if data is None:
                continue
            lines.append(f"\n## {mod['label']}\n")
            lines.append(_render_block(asdict(data)))
        return "\n".join(lines)


def _render_block(d: Any, indent: int = 0) -> str:
    """Recursively render a dict/list/scalar as readable markdown bullets."""
    pad = "  " * indent
    if isinstance(d, dict):
        if not d:
            return f"{pad}- _(empty)_\n"
        out = []
        for k, v in d.items():
            if v is None or v == "" or v == [] or v == {}:
                continue
            label = k.replace("_", " ").title()
            if isinstance(v, (dict, list)):
                out.append(f"{pad}- **{label}:**\n")
                out.append(_render_block(v, indent + 1))
            else:
                out.append(f"{pad}- **{label}:** {v}\n")
        return "".join(out)
    if isinstance(d, list):
        if not d:
            return f"{pad}- _(empty)_\n"
        out = []
        for item in d:
            if isinstance(item, (dict, list)):
                out.append(f"{pad}-\n")
                out.append(_render_block(item, indent + 1))
            else:
                out.append(f"{pad}- {item}\n")
        return "".join(out)
    return f"{pad}- {d}\n"


# ─────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────

_MODULE_CLASSES = {
    "project_understanding":   ProjectUnderstanding,
    "functional_requirements": FunctionalRequirements,
    "folder_structure":        FolderStructure,
    "architecture_design":     ArchitectureDesign,
    "component_breakdown":     ComponentBreakdown,
    "dependency_planning":     DependencyPlanning,
    "data_flow":               DataFlow,
    "file_responsibilities":   FileResponsibility,
    "api_planning":            APIPlanning,
    "database_planning":       DatabasePlanning,
    "security_considerations": SecurityConsiderations,
    "testing_strategy":        TestingStrategy,
    "code_standards":          CodeStandards,
    "risks_challenges":        RisksChallenges,
    "execution_roadmap":       ExecutionRoadmap,
}


def parse_plan_from_dict(d: Dict[str, Any], requirements: str = "") -> PlanningDocument:
    """Parse an LLM JSON payload into a PlanningDocument.

    Each module key is mapped to its dataclass. Unknown / empty modules
    stay None. Malformed nested dicts are tolerated (best-effort parse).
    """
    # Defensive: if the LLM returned a non-dict root (list / string / number),
    # we can't do anything meaningful — return an empty document.
    if not isinstance(d, dict):
        from ..logging_config import logger as _logger
        _logger.warning(
            "parse_plan_from_dict received non-dict payload (type=%s); returning empty doc",
            type(d).__name__,
        )
        doc = PlanningDocument(requirements=requirements)
        import time as _t
        doc.generated_at = _t.time()
        return doc

    doc = PlanningDocument(requirements=requirements)
    import time as _t
    doc.generated_at = _t.time()

    for key, cls in _MODULE_CLASSES.items():
        raw = d.get(key)
        if not raw or not isinstance(raw, dict):
            # Tolerate string / list / scalar values by attempting a one-shot
            # conversion: if it's a list, treat it as the first list field
            # of the dataclass; otherwise skip the module.
            if isinstance(raw, list) and raw:
                try:
                    # Try to wrap the list into the first list field of the class.
                    import dataclasses as _dc
                    first_list_field = None
                    for f in _dc.fields(cls):
                        if _dc.is_dataclass(cls):
                            origin = getattr(f.type, "__origin__", None)
                            if origin is list:
                                first_list_field = f.name
                                break
                    if first_list_field:
                        doc.__dict__[key] = cls(**{first_list_field: raw})
                except Exception:
                    pass
            continue
        try:
            doc.__dict__[key] = _safe_instantiate(cls, raw)
        except Exception:
            # Best effort — skip modules we can't parse
            continue
    return doc


def _safe_instantiate(cls, raw: Dict[str, Any]):
    """Instantiate a dataclass with only the keys it actually defines.

    Falls back to a per-field best-effort assignment if the bulk
    constructor rejects the input (e.g. wrong field types).
    """
    import dataclasses as _dc
    if not _dc.is_dataclass(cls):
        return raw
    valid_fields = {f.name for f in _dc.fields(cls)}
    filtered = {k: v for k, v in raw.items() if k in valid_fields}
    try:
        return cls(**filtered)
    except Exception:
        # Fallback: assign fields one-by-one, coercing / dropping bad values
        instance = cls()
        for k, v in filtered.items():
            try:
                setattr(instance, k, v)
            except Exception:
                continue
        return instance


def default_plan_for_modules(modules: Dict[str, bool]) -> Dict[str, bool]:
    """Fill in defaults so missing module ids default to ``False`` (none selected)."""
    return {m["id"]: bool(modules.get(m["id"], False)) for m in PLANNING_MODULES}


def all_module_ids() -> List[str]:
    return [m["id"] for m in PLANNING_MODULES]


# ─────────────────────────────────────────────────────────────────────
# ASCII tree parser — turns the planning tree into a flat list of paths
# ─────────────────────────────────────────────────────────────────────

_TEST_FILE_PATTERN = re.compile(r"(^|/)(test_|tests/|conftest\.py)$")
_TEST_DIR_PATTERN  = re.compile(r"(^|/)(tests|test)(/|$)")
_CONFIG_EXTS       = {".md", ".txt", ".toml", ".yaml", ".yml", ".cfg", ".ini", ".env", ".gitignore",
                      ".dockerignore", "Dockerfile", "docker-compose.yml", "Makefile"}

# Non-Python source extensions that MUST NEVER appear in the planned folder
# structure. The user-facing constraint is "Python only — no .html / .js /
# .ts / .css / etc.". Packaged config / project-root files listed in
# _CONFIG_EXTS are still allowed.
_FORBIDDEN_SOURCE_EXTS = {
    ".html", ".css", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".vue", ".svelte", ".scss", ".sass", ".less",
    ".sql", ".sh", ".bash", ".zsh", ".ps1",
    ".json", ".xml", ".yaml", ".yml",        # except as roots via _CONFIG_EXTS
}


def is_python_source(path: str) -> bool:
    """True if the planned path is a Python source file (``*.py``).

    Configuration / packaging files (e.g. ``pyproject.toml``,
    ``requirements.txt``) are intentionally NOT classified as Python
    source — they're handled separately by the Coder.
    """
    if not path:
        return False
    if path.endswith("/"):                  # directory entries
        return False
    return Path(path).suffix == ".py"


def is_test_path(path: str) -> bool:
    """Return True if a path looks like a test file or lives in a tests/ dir."""
    if not path:
        return False
    if _TEST_FILE_PATTERN.search(path):
        return True
    parts = path.split("/")
    return any(p.lower() in {"tests", "test"} or p.lower().startswith("test_")
               for p in parts[:-1])


def is_doc_or_config(path: str) -> bool:
    """Return True if a path is documentation or build/config metadata."""
    name = path.split("/")[-1]
    if name.startswith(".") and name != ".env":
        return True
    if any(name.endswith(ext) for ext in _CONFIG_EXTS):
        return True
    return False


def is_forbidden_non_python_source(path: str) -> bool:
    """True if the path's extension is non-Python and not a permitted config file.

    Used to enforce the "Python only" rule when the LLM slips a
    ``.html`` / ``.js`` / ``.ts`` / ``.css`` etc. into ``folder_structure.tree``.
    """
    name = path.split("/")[-1]
    if "/" not in path and not "." in name:
        return False  # bare directory entry
    ext = Path(name).suffix.lower()
    if ext in _CONFIG_EXTS:
        return False
    if ext == ".py":
        return False
    return ext in _FORBIDDEN_SOURCE_EXTS


def parse_tree(tree: str) -> List[str]:
    """Parse a simple ASCII directory tree into a list of file paths.

    The parser is depth-aware and handles:
      • Lines like ``├── foo/`` and ``└── bar.py``
      • Lines like ``│   ├── foo.py``
      • Plain indented lines like ``    foo.py``
      • The root line (e.g. ``my_project/``) which is treated as a prefix

    Empty input → empty list. Lines that don't look like file/dir entries
    (e.g. free-form notes) are skipped.
    """
    if not tree or not tree.strip():
        return []

    raw_lines = [ln for ln in tree.splitlines() if ln.strip()]

    # ── 1. Identify the root prefix from the first line ────────────
    root_prefix = ""
    if raw_lines:
        first = raw_lines[0].strip()
        # Strip any leading tree glyphs
        for glyph in ("├──", "└──", "├─", "└─", "│", "├", "└"):
            if first.startswith(glyph):
                first = first[len(glyph):].strip()
        if first and not first.endswith((".", ":", ")", "]", "}")) and " " not in first:
            root_prefix = first.rstrip("/")

    # ── 2. Compute depth + extract name from each line ─────────────
    entries: List[tuple] = []
    for raw in raw_lines:
        # Drop trailing annotations like "# package"
        ln = re.sub(r"\s+#.*$", "", raw).rstrip()
        if not ln.strip():
            continue

        # Depth is computed from the position of the branch glyph.
        # Tree notation uses 4-character indent blocks; each block equals
        # one level of nesting. So:
        #   `├── X`          → depth 1 (glyph at column 0)
        #   `│   └── Y`      → depth 2 (glyph at column 4)
        #   `│       ├── Z`  → depth 3 (glyph at column 8)
        last_branch = max(ln.rfind("├"), ln.rfind("└"))
        if last_branch == -1:
            # No branch glyph — could be the root line itself.
            decoration, entry = ln, ln.strip()
            for glyph in ("├──", "└──", "├─", "└─", "│", "├", "└"):
                if entry.startswith(glyph):
                    entry = entry[len(glyph):].strip()
            depth = 0
        else:
            decoration = ln[:last_branch]
            entry = ln[last_branch:].lstrip("├└").lstrip("─ ").strip()
            # depth = 1 + number of indent blocks preceding the branch
            # Use the position of the branch glyph (which is what the LLM
            # actually indented to) divided by the standard block size of 4.
            depth = max(1, (last_branch // 4) + 1)

        # Skip pure-prose lines
        if entry.startswith(("- ", "* ", "•")):
            continue
        if " " in entry and not entry.endswith("/"):
            continue

        entry = entry.rstrip(":")
        if entry:
            entries.append((depth, entry))

    # ── 3. Walk the entry tree and emit full paths ──────────────────
    paths: List[str] = []
    stack: Dict[int, str] = {}

    # The root itself isn't a "file" — but we record it as a parent path.
    if root_prefix:
        stack[0] = root_prefix

    for depth, entry in entries:
        # Normalise: strip trailing slash so we can compare with root_prefix.
        norm_entry = entry.rstrip("/")
        # Skip the root entry itself — we only emit its descendants.
        if root_prefix and norm_entry == root_prefix and depth == 0:
            stack[0] = norm_entry
            continue

        # The parent of this entry is whatever lives at `depth - 1`.
        # But if no parent is registered yet (e.g. the LLM emitted the root
        # without glyphs on the first line), use the root_prefix.
        parent_depth = depth - 1
        parent_path = stack.get(parent_depth)
        if parent_path is None:
            if root_prefix:
                parent_path = root_prefix
            else:
                parent_path = ""

        if parent_path:
            full = f"{parent_path}/{norm_entry}"
        else:
            full = norm_entry

        full = full.replace("//", "/")
        paths.append(full)
        stack[depth] = full

    # Deduplicate (preserves order)
    seen = set()
    deduped: List[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    return deduped
