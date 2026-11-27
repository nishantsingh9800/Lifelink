from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from backend.app.main import app
except Exception as exc:  # pragma: no cover - defensive serverless startup surface
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="LifeLink Startup Error")
    _err_type = type(exc).__name__
    _err_msg = str(exc)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def _startup_failed(path: str = ""):
        return JSONResponse(
            status_code=500,
            content={"detail": "Application failed to initialize.", "error_type": _err_type, "error": _err_msg},
        )


__all__ = ["app"]
