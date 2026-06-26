import sys
import os
import glob
import shutil

from orchestrator.core.workflow import WorkflowOrchestrator
from orchestrator.agents.coder import CoderAgent
from orchestrator.agents.tester import TesterAgent as OrchestratorTesterAgent
from orchestrator.agents.reviewer import ReviewerAgent

def cleanup():
    if os.path.exists("output"):
        shutil.rmtree("output")


class FakeLLM:
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        prompt_lower = user_prompt.lower()

        if "source code:" in prompt_lower and "target path:" in prompt_lower:
            return "def test_default():\n    assert True\n"

        if "file:" in prompt_lower and "code:" in prompt_lower:
            return '{"issues": []}'

        return (
            '{"files": [{"path": "main.py", "source_code": "def is_prime(n):\\n    return n > 1\\n"}], '
            '"summary": "ok"}'
        )

def test_pipeline():
    print("--- Testing Full Pipeline: Coder + Tester ---")
    
    # 1. Setup
    cleanup()
    os.environ["ORCHESTRATOR_AUTO_APPROVE"] = "1"
    fake_llm = FakeLLM()
    orchestrator = WorkflowOrchestrator(
        coder=CoderAgent(llm=fake_llm),
        tester=OrchestratorTesterAgent(llm=fake_llm),
        reviewer=ReviewerAgent(llm=fake_llm),
    )
    
    # 2. Run Pipeline
    requirement = "Create a Python function that checks if a number is prime."
    result_context = orchestrator.run(requirement)
    
    # 3. Verify Files Exist (Generic check)
    workspace = result_context.workspace_path or "output"
    py_files = glob.glob(os.path.join(workspace, "**", "*.py"), recursive=True)
    test_files = glob.glob(os.path.join(workspace, "**", "test_*.py"), recursive=True)
    
    assert len(py_files) > 0, "No source code created!"
    assert len(test_files) > 0, "No test code created!"
    
    print(f"\n✅ Full Pipeline Test Passed. Found {len(py_files)} files.")
    print("Files generated:", [os.path.basename(f) for f in py_files])
    
    # Optional: Cleanup
    # cleanup()

if __name__ == "__main__":
    test_pipeline()