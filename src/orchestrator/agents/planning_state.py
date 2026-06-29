import dataclasses
from typing import Dict, List, Optional
from .planning_models import PlanningDocument

@dataclasses.dataclass
class PlanningState:
    """State of the planning stage for a specific session."""
    status: str = "pending"  # pending, in_progress, checkpoint, complete, error
    selected_modules: Dict[str, bool] = dataclasses.field(default_factory=dict)
    plan: Optional[PlanningDocument] = None
    plan_markdown: str = ""
    error_message: Optional[str] = None
    logs: List[str] = dataclasses.field(default_factory=list)
    
    # Context injected from active session
    requirements: str = ""
    project_name: str = ""
    project_type: str = ""
