from orchestrator.core.context import FeedbackItem
from orchestrator.core.guardrails import evaluate_guardrails


def test_guardrail_detects_forbidden_operations():
    old_code = "def add(a, b):\n    return a + b\n"
    new_code = "import os\ndef add(a, b):\n    os.system('echo hi')\n    return a + b\n"
    feedback = [FeedbackItem(location="add()")]

    result = evaluate_guardrails(old_code, new_code, feedback, "calc.py")
    assert result["violations"], "Expected forbidden-operation violations"

