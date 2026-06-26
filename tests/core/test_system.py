import sys
import os
import glob
import shutil

from orchestrator.core.workflow import WorkflowOrchestrator
from orchestrator.core.context import WorkflowContext
from orchestrator.agents.coder import CoderAgent
from orchestrator.agents.tester import TesterAgent as OrchestratorTesterAgent
from orchestrator.agents.reviewer import ReviewerAgent

# 1. Setup Configuration
OUTPUT_DIR = "output"
TEST_REQUIREMENT = "Create a Python function that subtracts two numbers and returns the result."


class FakeLLM:
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        prompt_lower = user_prompt.lower()

        if "source code:" in prompt_lower and "target path:" in prompt_lower:
            return "def test_default():\n    assert True\n"

        if "file:" in prompt_lower and "code:" in prompt_lower:
            return '{"issues": []}'

        if "hello world" in prompt_lower:
            return (
                '{"files": [{"path": "main.py", "source_code": "def hello_world():\\n    return \\\"hello\\\"\\n"}], '
                '"summary": "ok"}'
            )

        return (
            '{"files": [{"path": "calculator/operations.py", "source_code": "def subtract(a, b):\\n    return a - b\\n"}], '
            '"summary": "ok"}'
        )

def setup_environment():
    """Clean the output directory before testing."""
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"✅ Environment Reset: '{OUTPUT_DIR}' folder cleaned.")

def test_coder_agent_isolation():
    """Test if Coder Agent can talk to LLM and generate code."""
    print("\n--- TEST 1: Coder Agent Isolation ---")
    agent = CoderAgent(llm=FakeLLM())
    context = WorkflowContext(requirements="Write a hello world function.", mode="GENERATE")
    
    result_context = agent.execute(context)
    
    assert result_context.success, f"Coder Agent failed: {result_context.error_message}"
    assert len(result_context.source_code) > 0, "No code generated."
    assert "def " in list(result_context.source_code.values())[0], "Generated code doesn't look like a function."
    print("✅ Coder Agent Isolation: PASS")

def test_full_pipeline():
    """Test the entire Orchestrator flow: Code -> Test -> Validation."""
    print("\n--- TEST 2: Full Pipeline Execution ---")
    
    # Initialize Orchestrator
    fake_llm = FakeLLM()
    orchestrator = WorkflowOrchestrator(
        coder=CoderAgent(llm=fake_llm),
        tester=OrchestratorTesterAgent(llm=fake_llm),
        reviewer=ReviewerAgent(llm=fake_llm),
    )
    
    # Run
    result_context = orchestrator.run(TEST_REQUIREMENT)
    
    # Verify Files Exist
    workspace = result_context.workspace_path or OUTPUT_DIR
    py_files = glob.glob(os.path.join(workspace, "**", "*.py"), recursive=True)
    test_files = glob.glob(os.path.join(workspace, "**", "test_*.py"), recursive=True)
    
    assert len(py_files) >= 1, "No source files generated in output."
    assert len(test_files) >= 1, "No test files generated in output."
    
    # Verify Content (Basic sanity check)
    source_code = ""
    for f in py_files:
        with open(f, 'r') as file:
            source_code += file.read()
            
    assert "subtract" in source_code.lower(), "Generated code does not match requirement (subtract)."
    
    print(f"✅ Files Generated: {[os.path.basename(f) for f in py_files]}")
    print("✅ Full Pipeline: PASS")

def test_error_handling():
    """Test if the system handles invalid modes gracefully."""
    print("\n--- TEST 3: Error Handling (Invalid Mode) ---")
    from orchestrator.agents.coder import CoderAgent
    
    agent = CoderAgent()
    # Context with an unsupported mode
    context = WorkflowContext(requirements="Test", mode="INVALID_MODE")
    
    result = agent.execute(context)
    
    assert not result.success, "Agent should have reported failure for invalid mode."
    assert "Unknown mode" in result.error_message, "Error message format incorrect."
    print("✅ Error Handling: PASS")

if __name__ == "__main__":
    print("====================")
    print(" STARTING SYSTEM TESTS")
    print("====================")
    
    setup_environment()
    
    try:
        test_coder_agent_isolation()
        test_full_pipeline()
        test_error_handling()
        
        print("\n========================================")
        print(" 🎉 ALL SYSTEM TESTS PASSED SUCCESSFULLY")
        print("========================================")
        print(f"You can inspect the generated files in the '{OUTPUT_DIR}' folder.")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
    except Exception as e:
        print(f"\n❗ CRITICAL ERROR: {e}")