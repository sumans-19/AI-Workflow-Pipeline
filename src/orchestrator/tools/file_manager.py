import json
import dataclasses
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


class FileManager:
    @staticmethod
    def _safe_path(path: Path) -> Path:
        """Prepend the Windows extended-length path prefix (\\\\?\\) to
        bypass the 260-character MAX_PATH limitation.  On non-Windows
        platforms this is a no-op.
        """
        if sys.platform == "win32":
            abs_path = str(path.resolve())
            if not abs_path.startswith("\\\\?\\"):
                return Path("\\\\?\\" + abs_path)
        return path

    @staticmethod
    def write_file(filename: str, content: str, directory: str = "output"):
        path = FileManager._safe_path(Path(directory) / filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write(content)
        return str(path)

    @staticmethod
    def read_file(filepath: str) -> str:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def ensure_run_dirs(base_dir: str, run_id: str) -> Dict[str, str]:
        run_root = FileManager._safe_path(Path(base_dir) / "runs" / run_id)
        workspace = run_root / "workspace"
        artifacts = run_root / "artifacts"
        metrics = run_root / "metrics"
        logs = run_root / "logs"
        for item in (workspace, artifacts, metrics, logs):
            item.mkdir(parents=True, exist_ok=True)
        return {
            "run_root": str(run_root),
            "workspace": str(workspace),
            "artifacts": str(artifacts),
            "metrics": str(metrics),
            "logs": str(logs),
        }

    @staticmethod
    def write_json(filename: str, payload: Any, directory: str) -> str:
        path = FileManager._safe_path(Path(directory) / filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            def _default(o):
                # dataclasses -> dict
                if dataclasses.is_dataclass(o):
                    return dataclasses.asdict(o)
                # objects with __dict__
                if hasattr(o, "__dict__"):
                    return o.__dict__
                # fallback to str
                return str(o)

            json.dump(payload, handle, indent=2, default=_default)
        return str(path)

    # ------------------------------------------------------------------
    # Project structure support
    # ------------------------------------------------------------------

    @staticmethod
    def create_project_structure(base_dir: str, project_name: str, files: Dict[str, str]) -> str:
        """Create a complete project directory and write all files.

        Args:
            base_dir: Parent directory where the project folder will be created.
            project_name: Name of the project (used as directory name).
            files: Dict mapping relative file paths to their content.

        Returns:
            The project root path as a string.
        """
        project_root = FileManager._safe_path(Path(base_dir) / project_name)
        for rel_path, content in files.items():
            file_path = project_root / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        return str(project_root)

    @staticmethod
    def build_project_tree(project_root: str, max_depth: int = 4) -> str:
        """Return a string representation of the project directory tree.

        Shows the directory structure in a tree-like format, skipping
        __pycache__, .git, and .pytest_cache directories.
        """
        skip_dirs = {"__pycache__", ".git", ".pytest_cache", ".ruff_cache", "node_modules"}
        root = Path(project_root)
        if not root.exists():
            return f"{root.name}/ (not found)"

        lines = [f"{root.name}/"]
        FileManager._walk_tree(root, lines, prefix="", max_depth=max_depth, skip_dirs=skip_dirs)
        return "\n".join(lines)

    @staticmethod
    def _walk_tree(
        directory: Path,
        lines: List[str],
        prefix: str,
        max_depth: int,
        skip_dirs: set,
        current_depth: int = 0,
    ):
        if current_depth >= max_depth:
            return

        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        entries = [e for e in entries if e.name not in skip_dirs]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            lines.append(f"{prefix}{connector}{entry.name}")

            if entry.is_dir():
                extension = "    " if is_last else "|   "
                FileManager._walk_tree(
                    entry, lines, prefix + extension, max_depth,
                    skip_dirs, current_depth + 1,
                )

    # ------------------------------------------------------------------
    # Git initialization
    # ------------------------------------------------------------------

    @staticmethod
    def git_init(project_path: str) -> bool:
        """Initialize a git repository at the given path.

        Returns:
            True if git init succeeded, False if git is not available.
        """
        try:
            subprocess.run(
                ["git", "init", project_path],
                capture_output=True,
                check=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
