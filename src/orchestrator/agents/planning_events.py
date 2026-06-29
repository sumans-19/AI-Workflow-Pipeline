from typing import Any, Dict

# Planning stage events
PLANNING_STARTED = "agent_started"
PLANNING_PROGRESS = "agent_progress"
PLANNING_COMPLETED = "agent_completed"
PLANNING_FAILED = "agent_failed"
PLANNING_CHECKPOINT = "checkpoint"

def create_planning_started_event() -> Dict[str, Any]:
    return {
        "type": PLANNING_STARTED,
        "data": {
            "agent": "planner",
            "message": "Planning agent started..."
        }
    }

def create_planning_progress_event(message: str) -> Dict[str, Any]:
    return {
        "type": PLANNING_PROGRESS,
        "data": {
            "agent": "planner",
            "message": message
        }
    }

def create_planning_completed_event(message: str = "Planning completed") -> Dict[str, Any]:
    return {
        "type": PLANNING_COMPLETED,
        "data": {
            "agent": "planner",
            "message": message,
            "failed": False
        }
    }

def create_planning_failed_event(reason: str) -> Dict[str, Any]:
    return {
        "type": PLANNING_FAILED,
        "data": {
            "agent": "planner",
            "reason": reason
        }
    }

def create_planning_checkpoint_event(
    plan: Dict[str, Any], 
    modules_selected: Dict[str, bool],
    modules_generated: list[str],
    plan_markdown: str
) -> Dict[str, Any]:
    return {
        "type": PLANNING_CHECKPOINT,
        "data": {
            "checkpoint_type": "planning_review",
            "message": "Planning complete. Please review the implementation plan.",
            "data": {
                "plan": plan,
                "modules_selected": modules_selected,
                "modules_generated": modules_generated,
                "plan_markdown": plan_markdown
            }
        }
    }
