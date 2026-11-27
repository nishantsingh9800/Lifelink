from pathlib import Path
import sys
import traceback

from fastapi import FastAPI
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_app() -> FastAPI:
    try:
        from backend.app.main import create_app

        return create_app()
    except Exception as exc:  # pragma: no cover
        err_app = FastAPI(title="LifeLink Startup Diagnostic")
        err_type = type(exc).__name__
        err_msg = str(exc)
        err_tb = traceback.format_exc()

        @err_app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
        async def _startup_error(path: str = ""):
            return JSONResponse(
                status_code=500,
                content={
                    "error_type": err_type,
                    "error": err_msg,
                    "traceback": err_tb.splitlines()[-10:],
                },
            )

        return err_app


app = _build_app()
