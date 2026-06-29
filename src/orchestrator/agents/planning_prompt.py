from typing import Dict
from .planning_models import MODULE_REGISTRY

def build_planning_system_prompt() -> str:
    """Build the static system prompt for the planning agent."""
    return (
        "You are an expert Software Architect and Project Planner.\n"
        "Your task is to analyze the user's requirements and generate a structured implementation plan.\n"
        "Follow these rules strictly:\n"
        "1. Output ONLY valid JSON matching the requested schema.\n"
        "2. Do not include markdown code fences (```json) around your output.\n"
        "3. Only generate the modules that are requested in the JSON schema.\n"
        "4. Be as detailed and comprehensive as possible.\n"
    )

def build_planning_user_prompt(
    requirements: str,
    project_name: str,
    project_type: str,
    selected_modules: Dict[str, bool]
) -> str:
    """Build the user prompt requesting specific planning modules."""
    
    prompt = [
        f"Project Name: {project_name}",
        f"Project Type: {project_type}",
        f"Requirements:\n{requirements}\n",
        "Please generate a detailed implementation plan containing ONLY the following sections:\n"
    ]
    
    for mod_id, is_selected in selected_modules.items():
        if is_selected and mod_id in MODULE_REGISTRY:
            mod_class = MODULE_REGISTRY[mod_id]
            desc = mod_class.__doc__.strip().split('\n')[0] if mod_class.__doc__ else "Detailed planning section."
            prompt.append(f"- {mod_id}: {desc}")
            
    prompt.append(
        "\nRemember to output ONLY valid JSON that matches the JSON schema provided in the function definition, "
        "and ONLY include the top-level keys for the sections requested above."
    )
    
    return "\n".join(prompt)
