import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import docker
    from docker.errors import DockerException, NotFound
except ImportError:  # pragma: no cover - environment-dependent
    docker = None

    class DockerException(Exception):
        pass

    class NotFound(Exception):
        pass

from ..logging_config import logger


class PythonRunner:
    PYTEST_TIMEOUT_SECONDS = 60
    CONTAINER_IMAGE = os.getenv("PYTEST_DOCKER_IMAGE", "ai-dev-orchestrator-pytest:latest")
    DOCKERFILE_RELATIVE_PATH = "docker/pytest-runner.Dockerfile"

    @staticmethod
    def run_pytest(directory: str):
        start = time.time()
        execution_mode = "unknown"
        try:
            if not os.path.exists(directory):
                return PythonRunner._build_result(False, f"Directory {directory} does not exist.", 0.0, 0.0, execution_mode, start)

            abs_directory = os.path.abspath(directory)

            if docker is None:
                logger.info("execution_mode=local_no_docker_sdk — Docker SDK not installed, falling back to local pytest")
                execution_mode = "local_no_docker_sdk"
                fallback_result = PythonRunner._run_pytest_locally(abs_directory)
                fallback_output = (
                    "Docker SDK not installed, falling back to local pytest.\n\n"
                    f"{fallback_result[1]}"
                )
                return PythonRunner._build_result(
                    fallback_result[0], fallback_output, fallback_result[2], 0.0, execution_mode, start
                )

            try:
                logger.info("execution_mode=docker_container — running tests in Docker (%s)", PythonRunner.CONTAINER_IMAGE)
                execution_mode = "docker_container"
                success, output, coverage = PythonRunner._run_pytest_in_container(abs_directory)
                return PythonRunner._build_result(success, output, coverage, 0.0, execution_mode, start)
            except DockerException as e:
                logger.warning("Docker unavailable (%s). Falling back to local pytest.", e)
                execution_mode = "local_fallback_docker_error"
                fallback_result = PythonRunner._run_pytest_locally(abs_directory)
                fallback_output = f"Docker unavailable, falling back to local pytest. Reason: {e}\n\n{fallback_result[1]}"
                return PythonRunner._build_result(
                    fallback_result[0], fallback_output, fallback_result[2], 0.0, execution_mode, start
                )

        except Exception as e:
            logger.error("Error running tests: %s", e)
            return PythonRunner._build_result(False, f"Error running tests: {str(e)}", 0.0, 0.0, execution_mode, start)

    @staticmethod
    def _build_result(passed: bool, output: str, coverage_line: float, coverage_branch: float, execution_mode: str, start: float) -> dict:
        return {
            "passed": passed,
            "output": output,
            "coverage": coverage_line,
            "coverage_line": coverage_line,
            "coverage_branch": coverage_branch,
            "execution_mode": execution_mode,
            "duration_seconds": round(time.time() - start, 3),
        }

    @staticmethod
    def _run_pytest_in_container(abs_directory: str):
        client = docker.from_env()
        client.ping()

        if not PythonRunner._ensure_pytest_image(client):
            raise DockerException(
                "Unable to prepare pytest image for container execution. "
                "Configure Docker networking or prebuild the image."
            )

        pytest_command = (
            "REQ=$(find /workspace -maxdepth 4 -name requirements.txt -print -quit); "
            "if [ -n \"$REQ\" ]; then pip install -r \"$REQ\"; fi; "
            "export PYTHONPATH=/workspace:/workspace/src:$PYTHONPATH; "
            "pytest /workspace -v --tb=short --cov=/workspace --cov-report=term-missing"
        )

        container = None
        try:
            container = client.containers.run(
                image=PythonRunner.CONTAINER_IMAGE,
                command=["sh", "-lc", pytest_command],
                volumes={abs_directory: {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                detach=True,
                stderr=True,
                stdout=True,
            )

            logger.info("Container started: %s, mounted %s -> /workspace", container.short_id, abs_directory)

            start_time = time.time()
            output_lines = []
            for raw_line in container.logs(stream=True, stdout=True, stderr=True, follow=True):
                elapsed = time.time() - start_time
                if elapsed > PythonRunner.PYTEST_TIMEOUT_SECONDS:
                    logger.warning("Docker test run timed out. Killing container...")
                    container.kill()
                    return False, "Test execution timed out.", 0.0

                decoded = raw_line.decode("utf-8", errors="replace")
                if decoded:
                    output_lines.append(decoded)
                    for line in decoded.rstrip().splitlines():
                        logger.debug("[docker][pytest] %s", line)

            result = container.wait(timeout=5)
            output = "".join(output_lines)
            success = result.get("StatusCode", 1) == 0
            coverage = PythonRunner._extract_coverage(output, success)
            logger.info("Docker test run completed. status=%s coverage=%s%%", result.get("StatusCode", 1), coverage)
            return success, output, coverage

        except Exception as e:
            if container is not None:
                try:
                    container.kill()
                except (DockerException, NotFound):
                    pass

            if "Read timed out" in str(e) or "timed out" in str(e).lower():
                return False, "Test execution timed out.", 0.0
            raise
        finally:
            if container is not None:
                try:
                    logger.debug("Removing container: %s", container.short_id)
                    container.remove(force=True)
                except (DockerException, NotFound):
                    pass

    @staticmethod
    def _run_pytest_locally(abs_directory: str):
        logger.info("Running local pytest in: %s", abs_directory)

        req_file = PythonRunner._find_requirements_file(Path(abs_directory))
        if req_file:
            logger.info("Installing dependencies from %s", req_file)
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", req_file],
                    capture_output=True,
                    text=True,
                    timeout=PythonRunner.PYTEST_TIMEOUT_SECONDS,
                    cwd=abs_directory,
                )
            except subprocess.TimeoutExpired:
                logger.warning("Dependency installation timed out for %s", req_file)

        # Build PYTHONPATH so generated packages are importable.
        # Generated projects may place packages under:
        #   workspace/<project>/src/<package>/
        #   workspace/<project>/<package>/
        #   workspace/src/<package>/
        #   workspace/<package>/
        python_paths: list[str] = [abs_directory]
        root = Path(abs_directory)
        for init_file in root.rglob("__init__.py"):
            # The package root is the *parent* of the directory containing __init__.py
            pkg_dir = init_file.parent  # e.g. workspace/proj/src/todo_app
            pkg_root = str(pkg_dir.parent)  # e.g. workspace/proj/src
            if pkg_root not in python_paths:
                python_paths.append(pkg_root)

        # Also add any `src/` directories found directly (pip src-layout convention)
        for src_dir in root.rglob("src"):
            src_str = str(src_dir)
            if src_dir.is_dir() and src_str not in python_paths:
                python_paths.append(src_str)

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        logger.info("Local pytest PYTHONPATH: %s", env["PYTHONPATH"])

        command = [
            "pytest",
            abs_directory,
            "-v",
            "--tb=short",
            f"--cov={abs_directory}",
            "--cov-report=term-missing",
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=PythonRunner.PYTEST_TIMEOUT_SECONDS,
                cwd=abs_directory,
                env=env,
            )

            output = result.stdout + result.stderr
            success = result.returncode == 0
            coverage = PythonRunner._extract_coverage(output, success)

            return success, output, coverage

        except subprocess.TimeoutExpired:
            return False, "Test execution timed out.", 0.0

    @staticmethod
    def _extract_coverage(output: str, success: bool) -> float:
        cov_match = re.search(r"TOTAL.*?(\d+)%", output)
        if cov_match:
            return float(cov_match.group(1))
        if success:
            return 100.0
        return 0.0

    @staticmethod
    def _find_requirements_file(root: Path) -> Optional[str]:
        direct = root / "requirements.txt"
        if direct.exists():
            return str(direct)

        candidates = sorted(root.rglob("requirements.txt"))
        if candidates:
            return str(candidates[0])
        return None

    @staticmethod
    def _ensure_pytest_image(client) -> bool:
        try:
            client.images.get(PythonRunner.CONTAINER_IMAGE)
            logger.debug("Using existing Docker image: %s", PythonRunner.CONTAINER_IMAGE)
            return True
        except Exception:
            pass

        repo_root = Path(__file__).resolve().parents[3]
        dockerfile_path = repo_root / PythonRunner.DOCKERFILE_RELATIVE_PATH

        if not dockerfile_path.exists():
            logger.warning("Dockerfile not found: %s", dockerfile_path)
            return False

        logger.info("Building Docker image %s from %s...", PythonRunner.CONTAINER_IMAGE, dockerfile_path)
        try:
            _, build_logs = client.images.build(
                path=str(repo_root),
                dockerfile=PythonRunner.DOCKERFILE_RELATIVE_PATH,
                tag=PythonRunner.CONTAINER_IMAGE,
                rm=True,
            )
            for entry in build_logs:
                if "stream" in entry:
                    for line in entry["stream"].rstrip().splitlines():
                        logger.debug("[docker][build] %s", line)
            logger.info("Built Docker image: %s", PythonRunner.CONTAINER_IMAGE)
            return True
        except Exception as exc:
            logger.error("Failed to build Docker image: %s", exc)
            return False
