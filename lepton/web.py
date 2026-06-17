"""FastAPI backend for the Lepton thermal camera web interface.

One CaptureManager owns the hardware; this module only serves its latest JPEG
and stats to browser clients and forwards setting changes back to it.
"""
import os

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lepton.camera import CaptureManager, COLORMAP_IDS

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")

BOUNDARY = "frame"


class Settings(BaseModel):
    emissivity: float | None = None
    background_temp: float | None = None
    colormap: str | None = None
    ffc: bool | None = None


def create_app(manager: CaptureManager) -> FastAPI:
    app = FastAPI(title="Lepton Thermal Camera")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))

    @app.get("/stream.mjpg")
    def stream():
        def generate():
            while True:
                jpeg = manager.wait_for_frame(timeout=2.0)
                if jpeg is None:
                    continue
                yield (b"--" + BOUNDARY.encode() + b"\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                       + jpeg + b"\r\n")

        return StreamingResponse(
            generate(),
            media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        )

    @app.get("/stats")
    def stats():
        return JSONResponse(manager.get_stats())

    @app.get("/meta")
    def meta():
        from lepton.radiometry import EMISSIVITY
        return JSONResponse({
            "materials": EMISSIVITY,
            "colormaps": list(COLORMAP_IDS.keys()),
        })

    @app.post("/settings")
    def settings(s: Settings):
        manager.update_settings(
            emissivity=s.emissivity,
            background_temp=s.background_temp,
            colormap=s.colormap,
        )
        if s.ffc:
            manager.request_ffc()
        return JSONResponse(manager.get_stats())

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app
