from orchestrator.tools.python_runner import PythonRunner


def test_python_runner_result_shape():
    result = PythonRunner._build_result(
        passed=True,
        output="ok",
        coverage_line=88.0,
        coverage_branch=0.0,
        execution_mode="local",
        start=0.0,
    )
    assert "coverage_line" in result
    assert "coverage_branch" in result
    assert "duration_seconds" in result
    assert result["coverage_line"] == 88.0

