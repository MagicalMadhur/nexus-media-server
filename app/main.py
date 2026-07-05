"""
Home Media Server & File Manager
Main FastAPI application entry point.
"""
import os
import io
import sys
import threading
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import Settings, get_local_ip, format_size, format_duration, BASE_DIR
from app.database import init_db
from app.services.mdns import MDNSService

logger = logging.getLogger(__name__)

# Global mDNS service instance
mdns_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — runs on startup and shutdown."""
    # --- Startup ---
    # Force UTF-8 output on Windows
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    print("\n" + "=" * 60)
    print("  [HOME] Media Server & File Manager")
    print("=" * 60)

    # Initialize database
    init_db()

    # Load settings
    settings = Settings()
    local_ip = get_local_ip()
    port = settings.port

    print(f"\n  [NET] Server URL: http://{local_ip}:{port}")
    print(f"  [PC]  Local URL:  http://localhost:{port}")

    # Generate QR code
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=1, border=1)
        qr.add_data(f"http://{local_ip}:{port}")
        qr.make(fit=True)
        f = io.StringIO()
        qr.print_ascii(out=f)
        f.seek(0)
        print(f"\n  [QR] Scan to connect:\n")
        for line in f.getvalue().splitlines():
            print(f"    {line}")
    except ImportError:
        print("  [i] Install 'qrcode' for QR code display")

    # Start media scan in background
    if settings.get("scan_on_startup", True) and settings.media_folders:
        from app.services.scanner import scan_all_folders, start_watchdog
        print(f"\n  [FOLDERS] Configured media folders:")
        for folder in settings.media_folders:
            print(f"     > {folder}")

        # Scan in background thread
        scan_thread = threading.Thread(target=scan_all_folders, daemon=True)
        scan_thread.start()

        # Start file watcher
        start_watchdog()
    else:
        print("\n  [i] No media folders configured. Go to Settings to add folders.")

    print(f"\n{'=' * 60}")
    print(f"  [OK] Server ready! Access from any device on your network.")
    print(f"{'=' * 60}\n")

    # Start mDNS broadcaster in a separate thread to prevent blocking the event loop
    global mdns_service
    mdns_service = MDNSService(port=port, name="home")
    import asyncio
    await asyncio.to_thread(mdns_service.start)

    yield

    # --- Shutdown ---
    print("\n[STOP] Shutting down...")
    try:
        from app.services.scanner import stop_watchdog
        stop_watchdog()
    except Exception as e:
        logger.error(f"Error stopping watchdog: {e}")
        
    if mdns_service:
        await asyncio.to_thread(mdns_service.stop)


# Create FastAPI app
app = FastAPI(
    title="Home Media Server",
    description="Self-hosted media server and file manager",
    version="1.0.0",
    lifespan=lifespan,
)

# Static files
static_dir = BASE_DIR / "app" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates
templates_dir = BASE_DIR / "app" / "templates"
templates_dir.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Add custom Jinja2 filters
templates.env.filters["format_size"] = format_size
templates.env.filters["format_duration"] = format_duration

# Store templates in app state for access in routes
app.state.templates = templates

# Include routers
from app.routes.dashboard import router as dashboard_router
from app.routes.videos import router as videos_router
from app.routes.streaming import router as streaming_router
from app.routes.files import router as files_router
from app.routes.photos import router as photos_router
from app.routes.music import router as music_router
from app.routes.search import router as search_router
from app.routes.documents import router as documents_router
from app.routes.webrtc import router as webrtc_router
from app.routes.cast import router as cast_router

app.include_router(dashboard_router)
app.include_router(webrtc_router)
app.include_router(videos_router)
app.include_router(streaming_router)
app.include_router(files_router)
app.include_router(photos_router)
app.include_router(music_router)
app.include_router(search_router)
app.include_router(documents_router)
app.include_router(cast_router, tags=["Cast"])


# --- API Status ---
@app.get("/api/status")
async def api_status():
    settings = Settings()
    local_ip = get_local_ip()
    from app.services.scanner import get_scan_progress
    return {
        "status": "running",
        "server_url": f"http://{local_ip}:{settings.port}",
        "local_ip": local_ip,
        "port": settings.port,
        "theme": settings.theme,
        "scan_progress": get_scan_progress(),
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve a 204 No Content for favicon to prevent 404s."""
    return Response(status_code=204)

@app.get("/sw.js", include_in_schema=False)
async def serve_service_worker():
    return FileResponse(os.path.join(BASE_DIR, "static", "sw.js"), media_type="application/javascript")

@app.get("/manifest.json", include_in_schema=False)
async def serve_manifest():
    return FileResponse(os.path.join(BASE_DIR, "static", "manifest.json"), media_type="application/manifest+json")


@app.get("/api/qr-code")
async def api_qr_code():
    """Generate QR code as PNG image."""
    try:
        import qrcode
        settings = Settings()
        local_ip = get_local_ip()
        url = f"http://{local_ip}:{settings.port}"

        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="white", back_color="#0f0f23")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        from fastapi.responses import StreamingResponse
        return StreamingResponse(buffer, media_type="image/png")
    except ImportError:
        from fastapi.responses import Response
        return Response(status_code=404, content="qrcode package not installed")


# --- Run directly ---
if __name__ == "__main__":
    import uvicorn
    import asyncio
    from app.services.ssl_cert import ensure_ssl_certs
    from app.config import BASE_DIR
    
    settings = Settings()
    
    # Ensure SSL certificates exist for the secure broadcasting port
    data_dir = BASE_DIR / "data"
    cert_path, key_path = ensure_ssl_certs(data_dir)
    
    async def run_both():
        config_http = uvicorn.Config(
            "app.main:app",
            host="0.0.0.0",
            port=settings.port,
            reload=False
        )
        server_http = uvicorn.Server(config_http)
        
        config_https = uvicorn.Config(
            "app.main:app",
            host="0.0.0.0",
            port=8443,
            ssl_keyfile=key_path,
            ssl_certfile=cert_path,
            log_level="warning",
            reload=False,
            lifespan="off"
        )
        server_https = uvicorn.Server(config_https)
        
        # Run both on the same event loop
        await asyncio.gather(server_http.serve(), server_https.serve())
        
    asyncio.run(run_both())
