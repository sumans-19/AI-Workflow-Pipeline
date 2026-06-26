@echo off
REM Start the Uvicorn server for the Pipeline Agents backend
REM We explicitly exclude output and workspace directories so that
REM generated code and test files do not trigger a backend reload.

uvicorn orchestrator.web.app:app --app-dir src --host 0.0.0.0 --port 8000 --reload --reload-dir src --reload-exclude "output/*" --reload-exclude "workspace/*" --reload-exclude "generated/*" --reload-exclude "test_artifacts/*"
