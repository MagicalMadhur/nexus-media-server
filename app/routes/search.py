"""
Global search and settings routes.
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import Settings, format_size, format_duration, UPLOADS_DIR
from app import database as db

router = APIRouter(tags=["search", "settings"])


# --- Search ---

@router.get("/api/search")
async def api_search(
    q: str = Query("", min_length=1),
    type: Optional[str] = None,
    limit: int = 30,
):
    """Global instant search across all media types."""
    if not q.strip():
        return {"results": [], "total": 0, "query": q}

    results = []
    types = [type] if type else ["video", "audio", "image", "document"]

    for ftype in types:
        items = db.get_media_files(
            file_type=ftype,
            search=q,
            limit=limit,
            sort_by="filename",
            sort_order="ASC",
        )
        for item in items:
            item["size_formatted"] = format_size(item.get("size", 0))
            item["duration_formatted"] = format_duration(item.get("duration", 0))
            results.append(item)

    # Sort by relevance (exact match first, then starts-with, then contains)
    q_lower = q.lower()
    results.sort(key=lambda x: (
        0 if x["filename"].lower() == q_lower else
        1 if x["filename"].lower().startswith(q_lower) else 2,
        x["filename"].lower()
    ))

    return {
        "results": results[:limit],
        "total": len(results),
        "query": q,
    }


# --- Settings ---

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Render the settings page."""
    settings = Settings()

    return request.app.state.templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings.get_all(),
            "theme": settings.theme,
            "page_title": "Settings",
        }
    )


@router.get("/api/settings")
async def api_get_settings():
    """API: Get all settings."""
    settings = Settings()
    return settings.get_all()


@router.post("/api/settings")
async def api_update_settings(request: Request):
    """API: Update settings."""
    settings = Settings()
    data = await request.json()

    for key, value in data.items():
        settings.set(key, value)

    return {"success": True, "settings": settings.get_all()}


@router.post("/api/add-media-folder")
async def api_add_media_folder(request: Request):
    """API: Add a media folder to scan."""
    settings = Settings()
    data = await request.json()
    folder = data.get("folder", "").strip()

    if not folder:
        raise HTTPException(status_code=400, detail="Folder path required")

    p = Path(folder)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"Folder does not exist: {folder}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {folder}")

    folders = settings.media_folders
    if folder not in folders:
        folders.append(folder)
        settings.set("media_folders", folders)

    return {"success": True, "media_folders": folders}


@router.post("/api/remove-media-folder")
async def api_remove_media_folder(request: Request):
    """API: Remove a media folder."""
    settings = Settings()
    data = await request.json()
    folder = data.get("folder", "").strip()

    folders = settings.media_folders
    if folder in folders:
        folders.remove(folder)
        settings.set("media_folders", folders)

    return {"success": True, "media_folders": folders}


@router.post("/api/scan")
async def api_trigger_scan(request: Request):
    """API: Trigger a media scan."""
    # Import scanner and run in background
    try:
        from app.services.scanner import scan_all_folders
        import threading
        thread = threading.Thread(target=scan_all_folders, daemon=True)
        thread.start()
        return {"success": True, "message": "Scan started in background"}
    except Exception as e:
        return {"success": False, "error": str(e)}
