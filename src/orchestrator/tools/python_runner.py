import os
import re
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

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


# Directories that must NEVER be added to PYTHONPATH even if they contain __init__.py.
# Including .venv/site-packages causes pip/_pytest to shadow stdlib (e.g. importlib._bootstrap).
_SKIP_DIRS = frozenset({
    ".venv", "venv", ".env", "env",
    "__pycache__", ".git", ".hg", ".svn",
    "node_modules", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".tox", "dist", "build", ".eggs", ".idea", ".vscode",
})

# Errors that indicate the Python interpreter itself is broken (not a test failure).
_ENV_ERROR_MARKERS = (
    "Could not import runpy module",
    "ModuleNotFoundError: No module named 'importlib",
    "ModuleNotFoundError: No module named '_io'",
    "ModuleNotFoundError: No module named 'posixpath'",
    "ModuleNotFoundError: No module named 'os'",
    "Fatal Python error",
    "Python path configuration:",
)


class PythonRunner:
    PYTEST_TIMEOUT_SECONDS = 60
    CONTAINER_IMAGE = os.getenv("PYTEST_DOCKER_IMAGE", "ai-dev-orchestrator-pytest:latest")
    DOCKERFILE_RELATIVE_PATH = "docker/pytest-runner.Dockerfile"

    @staticmethod
    def run_pytest(directory: str, force_local: bool = False):
        start = time.time()
        execution_mode = "unknown"
        try:
            if not os.path.exists(directory):
                return PythonRunner._build_result(False, f"Directory {directory} does not exist.", 0.0, 0.0, execution_mode, start)

            abs_directory = os.path.abspath(directory)

            if force_local:
                logger.info("execution_mode=local_forced — User forced local execution")
                execution_mode = "local_forced"
                fallback_result = PythonRunner._run_pytest_locally(abs_directory)
                passed, output, coverage, report_data = fallback_result
                # Detect environment-level failures vs actual test failures.
                if not passed and PythonRunner._is_env_error(output):
                    execution_mode = "local_env_error"
                    output = PythonRunner._format_env_error(output, "User forced local execution")
                else:
                    output = f"User requested local execution.\n\n{output}"
                return PythonRunner._build_result(passed, output, coverage, 0.0, execution_mode, start, report_data)

            if docker is None:
                logger.info("execution_mode=local_no_docker_sdk — Docker SDK not installed, falling back to local pytest")
                execution_mode = "local_no_docker_sdk"
                fallback_result = PythonRunner._run_pytest_locally(abs_directory)
                passed, output, coverage, report_data = fallback_result
                if not passed and PythonRunner._is_env_error(output):
                    execution_mode = "local_env_error"
                    output = PythonRunner._format_env_error(output, "Docker SDK not installed")
                else:
                    output = f"Docker SDK not installed, falling back to local pytest.\n\n{output}"
                return PythonRunner._build_result(passed, output, coverage, 0.0, execution_mode, start, report_data)

            try:
                logger.info("execution_mode=docker_container — running tests in Docker (%s)", PythonRunner.CONTAINER_IMAGE)
                execution_mode = "docker_container"
                success, output, coverage, report_data = PythonRunner._run_pytest_in_container(abs_directory)
                return PythonRunner._build_result(success, output, coverage, 0.0, execution_mode, start, report_data)
            except DockerException as e:
                logger.warning("Docker unavailable (%s). Falling back to local pytest.", e)
                execution_mode = "local_fallback_docker_error"
                fallback_result = PythonRunner._run_pytest_locally(abs_directory)
                passed, output, coverage, report_data = fallback_result
                if not passed and PythonRunner._is_env_error(output):
                    execution_mode = "local_env_error"
                    output = PythonRunner._format_env_error(output, f"Docker unavailable ({e})")
                else:
                    output = f"Docker unavailable, falling back to local pytest. Reason: {e}\n\n{output}"
                return PythonRunner._build_result(passed, output, coverage, 0.0, execution_mode, start, report_data)

        except Exception as e:
            logger.error("Error running tests: %s", e)
            return PythonRunner._build_result(False, f"Error running tests: {str(e)}", 0.0, 0.0, execution_mode, start)

    @staticmethod
    def _is_env_error(output: str) -> bool:
        """Return True when the failure looks like an interpreter/environment problem,
        not an actual test assertion failure."""
        if not output:
            return False
        return any(marker in output for marker in _ENV_ERROR_MARKERS)

    @staticmethod
    def _format_env_error(output: str, reason: str) -> str:
        """Wrap an environment-level failure with actionable advice."""
        return (
            f"{reason}.\n\n"
            "The local Python interpreter could not bootstrap (e.g. a broken virtual environment).\n"
            "Recommended actions:\n"
            "  1. Switch test-execution mode to 'Docker' in the top-right toolbar.\n"
            "  2. Or set TEST_USE_SYSTEM_PYTHON=1 in your .env to bypass venv creation.\n"
            "  3. Or delete the .venv folder inside the run's workspace and retry.\n\n"
            "--- Original error ---\n"
            f"{output}"
        )

    @staticmethod
    def _walk_python_paths(root: Path) -> list[str]:
        """Walk the workspace and collect directories that should be on PYTHONPATH.

        Critically skips virtualenv, cache, and VCS directories so that
        .venv/Lib/site-packages/{pip,_pytest,...} never shadows the stdlib.
        """
        paths: set[str] = {str(root)}
        root_str = str(root)

        # os.walk lets us prune dirnames in-place, avoiding descent into skip dirs.
        for dirpath, dirnames, filenames in os.walk(root_str):
            # Prune skipped directories so we never descend into them.
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

            current = Path(dirpath)

            # Collect package roots: if this dir contains __init__.py, its PARENT
            # is the importable package root.
            if "__init__.py" in filenames:
                parent = str(current.parent)
                if parent not in paths and not any(part in _SKIP_DIRS for part in current.parent.parts):
                    paths.add(parent)

            # Collect src/ layout directories.
            if current.name == "src" and current.is_dir():
                cleaned = str(current).replace("\\\\?\\", "")
                if not any(part in _SKIP_DIRS for part in current.parts):
                    paths.add(cleaned)

        return list(paths)

    @staticmethod
    def _validate_venv_python(venv_python: str) -> tuple[bool, str]:
        """Verify the venv Python can import critical stdlib modules.

        Returns (ok, message). A healthy venv must be able to import runpy,
        importlib._bootstrap, warnings, email.message — these are what break
        when pip/_pytest shadow the stdlib.
        """
        probe = (
            "import runpy, importlib._bootstrap, warnings, email.message, "
            "importlib.machinery, inspect; print('VENV_OK')"
        )
        try:
            r = subprocess.run(
                [venv_python, "-c", probe],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if r.returncode == 0 and "VENV_OK" in r.stdout:
                return True, "ok"
            return False, (r.stderr or r.stdout or "unknown error").strip()
        except subprocess.TimeoutExpired:
            return False, "venv health check timed out"
        except Exception as e:
            return False, f"venv health check raised {type(e).__name__}: {e}"

    @staticmethod
    def _build_result(passed: bool, output: str, coverage_line: float, coverage_branch: float, execution_mode: str, start: float, report_data: Optional[Dict[str, Any]] = None) -> dict:
        return {
            "passed": passed,
            "output": output,
            "coverage": coverage_line,
            "coverage_line": coverage_line,
            "coverage_branch": coverage_branch,
            "execution_mode": execution_mode,
            "duration_seconds": round(time.time() - start, 3),
            "report_data": report_data or {},
            "env_error": execution_mode == "local_env_error",
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
            "pip install pytest-json-report pytest-cov; "
            "export PYTHONPATH=/workspace:/workspace/src:$PYTHONPATH; "
            "pytest /workspace -v --tb=short --cov=/workspace --cov-report=term-missing --json-report --json-report-file=/workspace/.report.json"
        )

        container = None
        try:
            container = client.containers.run(
                image=PythonRunner.CONTAINER_IMAGE,
                command=["sh", "-lc", pytest_command],
                mounts=[
                    docker.types.Mount(
                        target="/workspace",
                        source=abs_directory,
                        type="bind",
                        read_only=False
                    )
                ],
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
            
            report_data = PythonRunner._parse_json_report(os.path.join(abs_directory, ".report.json"))
            
            return success, output, coverage, report_data

        except Exception as e:
            if container is not None:
                try:
                    container.kill()
                except (DockerException, NotFound):
                    pass

            if "Read timed out" in str(e) or "timed out" in str(e).lower():
                return False, "Test execution timed out.", 0.0, {}
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
        # Strip long path prefix if present to avoid Python venv / ensurepip bugs on Windows
        exec_dir = abs_directory
        if exec_dir.startswith("\\\\?\\"):
            exec_dir = exec_dir[4:]

        logger.info("Running local pytest in: %s", exec_dir)

        # Escape hatch: TEST_USE_SYSTEM_PYTHON=1 skips venv creation entirely
        # and uses the system Python directly. Useful when venv creation fails
        # on this machine (e.g. corrupted Python install, permission issues).
        force_system = os.getenv("TEST_USE_SYSTEM_PYTHON", "0") == "1"

        # Create a virtual environment for isolation
        venv_dir = os.path.join(exec_dir, ".venv")
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe") if os.name == "nt" else os.path.join(venv_dir, "bin", "python")

        # Clean up broken virtual environments (e.g. from previously failed ensurepip)
        if os.path.exists(venv_dir) and not os.path.exists(venv_python):
            logger.warning("Found broken virtual environment at %s (missing python binary). Cleaning it up.", venv_dir)
            import shutil
            try:
                shutil.rmtree(venv_dir)
            except Exception as e:
                logger.error("Failed to clean up broken venv: %s", e)

        use_global = force_system  # honor escape hatch
        if not force_system and not os.path.exists(venv_dir):
            logger.info("Creating virtual environment at %s", venv_dir)
            try:
                subprocess.run(
                    [sys.executable, "-m", "venv", ".venv"],
                    cwd=exec_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception as e:
                logger.warning("Failed to create virtual environment: %s. Falling back to global Python environment.", e)
                use_global = True
                if os.path.exists(venv_dir):
                    import shutil
                    try:
                        shutil.rmtree(venv_dir)
                    except Exception:
                        pass

        # Determine executable prefix
        if use_global or not os.path.exists(venv_python):
            logger.info("Using global Python environment for dependencies and tests.")
            run_cmd_prefix = [sys.executable]
        else:
            # HEALTH CHECK: verify the venv Python can actually import stdlib.
            # Without this, a broken venv silently produces the
            # "ModuleNotFoundError: No module named 'importlib._bootstrap'" cascade.
            ok, msg = PythonRunner._validate_venv_python(venv_python)
            if not ok:
                logger.warning(
                    "Virtual environment at %s is broken (health check failed: %s). "
                    "Deleting it and falling back to global Python.",
                    venv_python, msg[:200],
                )
                import shutil
                try:
                    shutil.rmtree(venv_dir)
                except Exception:
                    pass
                use_global = True
                run_cmd_prefix = [sys.executable]
            else:
                logger.info("Using virtual environment Python at %s (health check passed)", venv_python)
                run_cmd_prefix = [venv_python]

        req_file = PythonRunner._find_requirements_file(Path(exec_dir))
        if req_file:
            logger.info("Installing dependencies from %s", req_file)
            try:
                subprocess.run(
                    run_cmd_prefix + ["-m", "pip", "install", "-r", req_file],
                    capture_output=True,
                    text=True,
                    timeout=PythonRunner.PYTEST_TIMEOUT_SECONDS,
                    cwd=exec_dir,
                )
            except subprocess.TimeoutExpired:
                logger.warning("Dependency installation timed out for %s", req_file)

        # Ensure pytest plugins are installed
        subprocess.run(run_cmd_prefix + ["-m", "pip", "install", "pytest", "pytest-json-report", "pytest-cov"], capture_output=True)

        # Build PYTHONPATH so generated packages are importable.
        # CRITICAL: must skip .venv, __pycache__, etc. — otherwise pip/_pytest
        # shadow stdlib and break the import chain.
        python_paths = PythonRunner._walk_python_paths(Path(exec_dir))

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        logger.info("Local pytest PYTHONPATH entries: %d", len(python_paths))

        command = run_cmd_prefix + [
            "-m",
            "pytest",
            exec_dir,
            "-v",
            "--tb=short",
            f"--cov={exec_dir}",
            "--cov-report=term-missing",
            "--json-report",
            "--json-report-file=.report.json",
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=PythonRunner.PYTEST_TIMEOUT_SECONDS,
                cwd=exec_dir,
                env=env,
            )

            output = result.stdout + result.stderr
            success = result.returncode == 0
            coverage = PythonRunner._extract_coverage(output, success)

            report_data = PythonRunner._parse_json_report(os.path.join(exec_dir, ".report.json"))

            return success, output, coverage, report_data

        except subprocess.TimeoutExpired:
            return False, "Test execution timed out.", 0.0, {}

    @staticmethod
    def _extract_coverage(output: str, success: bool) -> float:
        cov_match = re.search(r"TOTAL.*?(\d+)%", output)
        if cov_match:
            return float(cov_match.group(1))
        if success:
            return 100.0
        return 0.0

    @staticmethod
    def _parse_json_report(filepath: str) -> Dict[str, Any]:
        """Parses the generated pytest-json-report file to extract structured test metrics."""
        report = {
            "summary": {"collected": 0, "passed": 0, "failed": 0, "skipped": 0, "xfailed": 0, "total": 0},
            "failures": []
        }
        try:
            if not os.path.exists(filepath):
                return report
                
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            s = data.get("summary", {})
            report["summary"]["collected"] = s.get("collected", 0)
            report["summary"]["passed"] = s.get("passed", 0)
            report["summary"]["failed"] = s.get("failed", 0)
            report["summary"]["skipped"] = s.get("skipped", 0)
            report["summary"]["xfailed"] = s.get("xfailed", 0)
            report["summary"]["total"] = s.get("total", 0)
            
            for test in data.get("tests", []):
                if test.get("outcome") == "failed":
                    call_phase = test.get("call", {})
                    crash = call_phase.get("crash", {})
                    longrepr = call_phase.get("longrepr", "")
                    
                    # Extract the assertion / expected vs actual if it exists
                    assertion = ""
                    expected_actual = ""
                    if "E   AssertionError:" in longrepr:
                        lines = longrepr.splitlines()
                        for i, line in enumerate(lines):
                            if "E   AssertionError:" in line:
                                assertion = line.replace("E   AssertionError:", "").strip()
                                # Grab next few lines for expected/actual
                                next_lines = lines[i+1:i+6]
                                expected_actual = "\n".join([ln.replace("E   ", "") for ln in next_lines if ln.startswith("E   ")])
                                break
                                
                    report["failures"].append({
                        "nodeid": test.get("nodeid", ""),
                        "file": crash.get("path", ""),
                        "lineno": crash.get("lineno", 0),
                        "test_name": test.get("nodeid", "").split("::")[-1],
                        "error_type": crash.get("message", "").split(":")[0] if ":" in crash.get("message", "") else "Error",
                        "exception": crash.get("message", ""),
                        "traceback": longrepr,
                        "assertion": assertion,
                        "expected_actual": expected_actual
                    })
        except Exception as e:
            logger.warning("Failed to parse pytest json report: %s", e)
            
        return report

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
