"""
Dashboard route — the beautiful home page.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.config import Settings, format_size, get_local_ip
from app import database as db

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main dashboard."""
    settings = Settings()
    stats = db.get_stats()
    continue_watching = db.get_continue_watching(limit=10)
    recently_added = db.get_recently_added(limit=12)
    favorites = db.get_favorites(limit=8)
    pinned_folders = db.get_pinned_folders()

    local_ip = get_local_ip()
    port = settings.port

    return request.app.state.templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "continue_watching": continue_watching,
            "recently_added": recently_added,
            "favorites": favorites,
            "pinned_folders": pinned_folders,
            "local_ip": local_ip,
            "port": port,
            "server_url": f"http://{local_ip}:{port}",
            "total_size_formatted": format_size(stats.get("total_size", 0)),
            "video_size_formatted": format_size(stats.get("video_size", 0)),
            "audio_size_formatted": format_size(stats.get("audio_size", 0)),
            "image_size_formatted": format_size(stats.get("image_size", 0)),
            "theme": settings.theme,
            "page_title": "Dashboard",
        }
    )
