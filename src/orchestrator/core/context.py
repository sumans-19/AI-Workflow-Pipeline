from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import time
import uuid


@dataclass
class FeedbackItem:
    """A single structured feedback entry tied to a specific code location."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = ""
    checkpoint: str = "CODE_REVIEW"
    source: str = "human"          # "human", "reviewer", "tester", "validator"
    severity: str = "major"        # "critical", "major", "minor", "suggestion"
    category: str = "bug"          # "bug", "test", "style", "security", "docs"
    description: str = ""
    location: Optional[str] = None # e.g. "calculator.py:L15" or "add_numbers()"
    file_path: Optional[str] = None
    symbol: Optional[str] = None
    location_start: Optional[int] = None
    location_end: Optional[int] = None
    action: str = "fix"            # "fix", "keep", "rewrite"
    resolved: bool = False
    status: str = "open"           # "open", "in_progress", "resolved", "wontfix"
    author: str = "human"
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolution_note: str = ""


@dataclass
class WorkflowContext:
    # Inputs
    requirements: str = ""
    mode: str = "GENERATE"
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    run_root: str = ""
    workspace_path: str = ""
    artifacts_path: str = ""
    metrics_path: str = ""
    logs_path: str = ""
    last_test_log_path: Optional[str] = None
    validation_report: Dict[str, Any] = field(default_factory=dict)

    # Pipeline stage tracking
    stage: str = "CODING"  # CODING, TESTING, REVIEWING, VALIDATING, COMPLETE, REJECTED

    # State
    current_step: str = "INIT"

    # Project mode fields
    project_name: str = ""
    project_type: str = "library"     # "fastapi", "flask", "cli", "library", "script"
    is_project_mode: bool = False
    project_tree: str = ""

    # Artifacts
    source_code: Dict[str, str] = field(default_factory=dict)
    test_code: Dict[str, str] = field(default_factory=dict)
    test_results: Dict[str, Any] = field(default_factory=dict)
    review_issues: List[str] = field(default_factory=list)
    emitted_files: set[str] = field(default_factory=set)

    # Code history — snapshots of source_code at each iteration for diffing/rollback
    code_history: List[Dict[str, str]] = field(default_factory=list)

    # Structured HITL feedback
    feedback_items: List[FeedbackItem] = field(default_factory=list)

    # Retry
    retry_count: int = 0
    max_retries: int = 3

    # Audit log of human decisions
    human_actions: List[Dict] = field(default_factory=list)

    # Status
    success: bool = False
    error_message: Optional[str] = None

    # Runtime metrics (populated by workflow)
    metrics: Dict[str, Any] = field(default_factory=dict)
    metrics_history: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    quality_gates: Dict[str, Any] = field(default_factory=dict)
    attempts_by_stage: Dict[str, int] = field(default_factory=dict)

    # Callback for emitting structured agent events (e.g. over WebSocket)
    emit_event: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def snapshot_code(self):
        """Save current source_code as a historical snapshot."""
        if self.source_code:
            self.code_history.append(dict(self.source_code))

    def previous_code(self) -> Optional[Dict[str, str]]:
        """Return the most recent code snapshot, or None if first iteration."""
        return self.code_history[-1] if self.code_history else None

    def unresolved_feedback(self) -> List[FeedbackItem]:
        """Return feedback items that haven't been resolved yet."""
        return [f for f in self.feedback_items if not f.resolved and f.status != "wontfix"]

    def mark_feedback_resolved(self, item: FeedbackItem, note: str = ""):
        item.resolved = True
        item.status = "resolved"
        item.resolved_at = time.time()
        item.resolution_note = note

    def add_human_action(self, stage: str, action: str, feedback: str = ""):
        """Record a human decision in the audit log."""
        self.human_actions.append({
            "stage": stage,
            "action": action,
            "feedback": feedback,
            "timestamp": time.time(),
            "attempt": self.retry_count + 1,
        })
