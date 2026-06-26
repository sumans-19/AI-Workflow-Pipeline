from orchestrator.tools.file_manager import FileManager


def test_run_workspace_structure(tmp_path):
    paths = FileManager.ensure_run_dirs(str(tmp_path), "run-123")
    assert (tmp_path / "runs" / "run-123" / "workspace").exists()
    assert (tmp_path / "runs" / "run-123" / "artifacts").exists()
    assert paths["workspace"].endswith("workspace")

