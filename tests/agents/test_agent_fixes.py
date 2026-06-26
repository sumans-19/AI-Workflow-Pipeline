from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.agents.coder import CoderAgent
from orchestrator.agents.tester import TesterAgent as OrchestratorTesterAgent
from orchestrator.core.context import WorkflowContext


def test_tester_agent_ignores_non_python_files(monkeypatch, temp_dir):
    llm = MagicMock()
    llm.generate.return_value = "def test_ok():\n    assert True\n"

    file_manager = MagicMock()
    file_manager.write_file.return_value = "written"

    runner = MagicMock()
    runner.run_pytest.return_value = {
        "passed": True,
        "output": "ok",
        "coverage_line": 100,
        "coverage_branch": 100,
        "execution_mode": "pytest",
        "duration_seconds": 0.1,
    }

    monkeypatch.setattr("orchestrator.agents.tester.display_code", lambda *args, **kwargs: None)

    agent = OrchestratorTesterAgent(llm=llm, file_manager=file_manager, runner=runner)
    context = WorkflowContext(requirements="test", mode="GENERATE")
    context.workspace_path = temp_dir
    context.source_code = {
        "src/app.py": "def add(a, b):\n    return a + b\n",
        "README.md": "# docs",
        "pyproject.toml": "[project]\nname = 'demo'",
    }

    result = agent.execute(context)

    assert result.success is True
    assert llm.generate.call_count == 1
    assert file_manager.write_file.call_count == 1
    assert Path(file_manager.write_file.call_args.args[0]).as_posix() == "tests/test_app.py"


def test_coder_agent_rejects_truncated_python():
    llm = MagicMock()
    llm.generate.return_value = (
        '{"files": [{"path": "src/app.py", "source_code": "def broken(:\\n    pass\\n"}], "summary": "done"}'
    )

    agent = CoderAgent(llm=llm)
    context = WorkflowContext(requirements="generate code", mode="GENERATE")

    result = agent.execute(context)

    assert result.success is False
    assert result.error_message is not None
    assert "syntactically invalid" in result.error_message