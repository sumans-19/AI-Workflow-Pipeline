"""Quick-start helper: run backend + frontend simultaneously."""
import subprocess
import sys
import os

ROOT = os.path.dirname(__file__)
WEB_DIR = os.path.join(ROOT, "web")

print("Starting AI Dev Platform...")
print("  Backend  → http://localhost:8000")
print("  Frontend → http://localhost:5173")
print("  Press Ctrl+C to stop both.\n")

backend = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "orchestrator.web.app:app", "--reload", "--port", "8000"],
    cwd=ROOT,
)
frontend = subprocess.Popen(
    ["npm", "run", "dev"],
    cwd=WEB_DIR,
    shell=True,
)

try:
    backend.wait()
except KeyboardInterrupt:
    backend.terminate()
    frontend.terminate()
    print("\nStopped.")
