"""
Music library and player routes.
"""
import urllib.parse
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.config import Settings, format_size, format_duration
from app import database as db

router = APIRouter(tags=["music"])


@router.get("/music", response_class=HTMLResponse)
async def music_library(request: Request,
                        sort: str = "date_added",
                        order: str = "DESC",
                        search: Optional[str] = None,
                        page: int = 1):
    """Render the music library page."""
    settings = Settings()
    limit = 50
    offset = (page - 1) * limit

    tracks = db.get_media_files(
        file_type="audio",
        sort_by=sort,
        sort_order=order,
        limit=limit,
        offset=offset,
        search=search,
    )

    for t in tracks:
        t["size_formatted"] = format_size(t.get("size", 0))
        t["duration_formatted"] = format_duration(t.get("duration", 0))
        t["stream_url"] = f"/api/stream/{urllib.parse.quote(t['path'], safe='')}"
        t["display_title"] = t.get("title") or t["filename"]
        t["display_artist"] = t.get("artist") or "Unknown Artist"
        t["display_album"] = t.get("album") or "Unknown Album"
        t["album_art_url"] = f"/api/album-art/{t['id']}" if t.get("album_art_path") else None
        t["is_favorite"] = db.is_favorite(t["id"])

    total = db.get_media_count("audio")
    total_pages = max(1, (total + limit - 1) // limit)

    return request.app.state.templates.TemplateResponse(
        "music_library.html",
        {
            "request": request,
            "tracks": tracks,
            "total_tracks": total,
            "current_page": page,
            "total_pages": total_pages,
            "sort": sort,
            "order": order,
            "search": search or "",
            "theme": settings.theme,
            "page_title": "Music Library",
        }
    )


@router.get("/api/music")
async def api_list_music(
    sort: str = "date_added",
    order: str = "DESC",
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    tracks = db.get_media_files(
        file_type="audio",
        sort_by=sort, sort_order=order,
        limit=limit, offset=offset, search=search,
    )
    for t in tracks:
        t["size_formatted"] = format_size(t.get("size", 0))
        t["duration_formatted"] = format_duration(t.get("duration", 0))
        t["stream_url"] = f"/api/stream/{urllib.parse.quote(t['path'], safe='')}"
        t["display_title"] = t.get("title") or t["filename"]
        t["display_artist"] = t.get("artist") or "Unknown Artist"
    return {"tracks": tracks, "total": db.get_media_count("audio")}


@router.get("/api/album-art/{media_id}")
async def api_album_art(media_id: int):
    """Serve album art for a track."""
    media = db.get_media_file_by_id(media_id)
    if not media or not media.get("album_art_path"):
        raise HTTPException(status_code=404, detail="Album art not found")

    art_path = Path(media["album_art_path"])
    if not art_path.exists():
        raise HTTPException(status_code=404, detail="Album art file missing")

    from fastapi.responses import FileResponse
    return FileResponse(str(art_path), media_type="image/jpeg")
