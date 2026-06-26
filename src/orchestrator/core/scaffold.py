"""Project scaffold data models for full-stack project generation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class ProjectType(Enum):
    FASTAPI_APP = "fastapi"
    FLASK_APP = "flask"
    CLI_TOOL = "cli"
    LIBRARY = "library"
    SCRIPT = "script"


@dataclass
class GeneratedFile:
    """Represents a single file in a generated project."""
    path: str           # relative path within project, e.g. "src/myapp/models.py"
    content: str        # file content
    language: str = "python"
    is_test: bool = False
    is_config: bool = False


@dataclass
class ProjectScaffold:
    """Represents a complete generated project."""
    name: str
    project_type: ProjectType = ProjectType.LIBRARY
    files: List[GeneratedFile] = field(default_factory=list)

    def add_file(self, path: str, content: str, **kwargs):
        self.files.append(GeneratedFile(path=path, content=content, **kwargs))

    def get_source_files(self) -> List[GeneratedFile]:
        return [f for f in self.files if not f.is_test and not f.is_config]

    def get_test_files(self) -> List[GeneratedFile]:
        return [f for f in self.files if f.is_test]

    def get_config_files(self) -> List[GeneratedFile]:
        return [f for f in self.files if f.is_config]

    def to_source_code_dict(self) -> Dict[str, str]:
        """Convert to the format expected by WorkflowContext.source_code."""
        return {f.path: f.content for f in self.files}

    @staticmethod
    def from_source_code(
        source_code: Dict[str, str],
        project_name: str,
        project_type: str = "library",
    ) -> "ProjectScaffold":
        """Create a ProjectScaffold from a source_code dict."""
        ptype = ProjectType(project_type) if project_type in [e.value for e in ProjectType] else ProjectType.LIBRARY
        scaffold = ProjectScaffold(name=project_name, project_type=ptype)
        for path, content in source_code.items():
            is_test = path.startswith("tests/") or path.startswith("test_")
            is_config = path in (
                "pyproject.toml", "requirements.txt", ".env.example",
                ".gitignore", "Dockerfile", "docker-compose.yml",
                "README.md", "setup.py", "setup.cfg",
            )
            scaffold.add_file(path=path, content=content, is_test=is_test, is_config=is_config)
        return scaffold
