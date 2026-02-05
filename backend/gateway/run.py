"""Run the LLM gateway service."""

from pathlib import Path
import sys
import uvicorn


if __name__ == "__main__":
    # Ensure `backend/` is on sys.path so `gateway.*` and `app.*` imports work
    backend_dir = Path(__file__).resolve().parents[1]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    uvicorn.run("gateway.main:app", host="0.0.0.0", port=8010, reload=True)
