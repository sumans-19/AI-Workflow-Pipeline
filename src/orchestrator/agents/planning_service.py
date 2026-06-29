from typing import Optional
from .planning_agent import PlanningAgent
from .planning_state import PlanningState
from ..core.context import WorkflowContext

class PlanningService:
    """Service wrapping the PlanningAgent for execution and context integration."""
    
    def __init__(self, agent: Optional[PlanningAgent] = None):
        self.agent = agent or PlanningAgent()
        
    def generate_plan(self, state: PlanningState, context: WorkflowContext) -> PlanningState:
        """Executes the planning agent and updates state."""
        try:
            # Sync state requirements to context for the agent
            context.requirements = state.requirements
            context.project_name = state.project_name
            context.project_type = state.project_type
            context.planning_modules = state.selected_modules
            
            # Execute the agent
            context = self.agent.execute(context)
            
            if context.success and context.plan:
                state.plan = context.plan
                state.plan_markdown = context.plan.to_markdown()
                state.status = "checkpoint"
                state.error_message = None
            else:
                state.status = "error"
                state.error_message = context.error_message or "Planning agent failed without specific error."
                
        except Exception as e:
            state.status = "error"
            state.error_message = f"Planning service error: {str(e)}"
            
        return state
