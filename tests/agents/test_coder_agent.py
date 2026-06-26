import sys

from orchestrator.core.context import WorkflowContext
from orchestrator.agents.coder import CoderAgent

def run_coder_test():
    print("--- Testing Coder Agent Isolation ---")
    
    # 1. Setup Context
    context = WorkflowContext(
        requirements="Create a python function that calculates the factorial of a number.",
        mode="GENERATE"
    )
    
    # 2. Initialize Agent
    agent = CoderAgent()
    
    # 3. Execute
    updated_context = agent.execute(context)
    
    # 4. Verify Results
    if updated_context.success:
        print("\n✅ Agent Execution Successful")
        print("\n--- Generated Code ---")
        for filename, code in updated_context.source_code.items():
            print(f"File: {filename}")
            print(code)
    else:
        print(f"\n❌ Agent Execution Failed: {updated_context.error_message}")

if __name__ == "__main__":
    run_coder_test()