import sys
# pyrefly: ignore [missing-import]
import uvicorn
from pathlib import Path

if __name__ == "__main__":
    # Add src directory to path so 'orchestrator' module can be imported
    src_dir = Path(__file__).parent / "src"
    sys.path.insert(0, str(src_dir))

    uvicorn.run(
        "orchestrator.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )
