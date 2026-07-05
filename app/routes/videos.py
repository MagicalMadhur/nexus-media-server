"""
Video library and player routes.
"""
import os
import urllib.parse
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import Settings, format_size, format_duration, get_local_ip, is_video
from app import database as db

router = APIRouter(tags=["videos"])


@router.get("/videos", response_class=HTMLResponse)
async def video_library(request: Request,
                        sort: str = "date_added",
                        order: str = "DESC",
                        folder: Optional[str] = None,
                        search: Optional[str] = None,
                        page: int = 1):
    """Render the video library page."""
    settings = Settings()
    limit = 30
    offset = (page - 1) * limit

    videos = db.get_media_files(
        file_type="video",
        folder=folder,
        sort_by=sort,
        sort_order=order,
        limit=limit,
        offset=offset,
        search=search
    )

    # Enhance video data
    for v in videos:
        v["size_formatted"] = format_size(v.get("size", 0))
        v["duration_formatted"] = format_duration(v.get("duration", 0))
        v["resolution"] = f"{v.get('width', '?')}x{v.get('height', '?')}" if v.get("width") else ""
        v["stream_url"] = f"/api/stream/{urllib.parse.quote(v['path'], safe='')}"
        v["thumbnail_url"] = f"/api/thumbnail/{v['id']}" if v.get("thumbnail_path") else None
        v["is_favorite"] = db.is_favorite(v["id"])
        pos = db.get_watch_position(v["id"])
        v["watch_position"] = pos if pos else 0
        v["watch_progress"] = (pos / v["duration"] * 100) if pos and v.get("duration") else 0

    total_videos = db.get_media_count("video")
    total_pages = max(1, (total_videos + limit - 1) // limit)
    folders = db.get_unique_folders("video")
    
    continue_watching = db.get_continue_watching(limit=10)

    return request.app.state.templates.TemplateResponse(
        "video_library.html",
        {
            "request": request,
            "videos": videos,
            "continue_watching": continue_watching,
            "total_videos": total_videos,
            "current_page": page,
            "total_pages": total_pages,
            "sort": sort,
            "order": order,
            "current_folder": folder,
            "search": search or "",
            "folders": folders,
            "theme": settings.theme,
            "page_title": "Video Library",
        }
    )


@router.get("/player/{media_id}", response_class=HTMLResponse)
async def video_player(request: Request, media_id: int):
    """Render the video player page."""
    settings = Settings()
    video = db.get_media_file_by_id(media_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video["size_formatted"] = format_size(video.get("size", 0))
    video["duration_formatted"] = format_duration(video.get("duration", 0))
    video["resolution"] = f"{video.get('width', '?')}x{video.get('height', '?')}" if video.get("width") else ""
    video["stream_url"] = f"/api/stream/{urllib.parse.quote(video['path'], safe='')}"
    video["is_favorite"] = db.is_favorite(video["id"])

    # Get watch position for resume
    watch_position = db.get_watch_position(media_id) or 0

    # Get subtitle files (same name, different extension in same directory)
    subtitle_files = []
    video_path = Path(video["path"])
    video_dir = video_path.parent
    video_stem = video_path.stem
    subtitle_exts = [".srt", ".vtt", ".ass", ".ssa"]
    if video_dir.exists():
        for f in video_dir.iterdir():
            if f.stem.startswith(video_stem) and f.suffix.lower() in subtitle_exts:
                label = f.stem.replace(video_stem, "").strip("._- ") or "Default"
                subtitle_files.append({
                    "label": label,
                    "src": f"/api/stream/{urllib.parse.quote(str(f), safe='')}",
                    "ext": f.suffix.lower(),
                })

    # Get adjacent videos for next/previous
    all_videos = db.get_media_files(
        file_type="video",
        folder=video.get("parent_folder"),
        sort_by="filename",
        sort_order="ASC",
        limit=1000
    )
    current_idx = next((i for i, v in enumerate(all_videos) if v["id"] == media_id), -1)
    prev_video = all_videos[current_idx - 1] if current_idx > 0 else None
    next_video = all_videos[current_idx + 1] if current_idx < len(all_videos) - 1 else None

    return request.app.state.templates.TemplateResponse(
        "video_player.html",
        {
            "request": request,
            "video": video,
            "watch_position": watch_position,
            "subtitle_files": subtitle_files,
            "prev_video": prev_video,
            "next_video": next_video,
            "theme": settings.theme,
            "server_url": f"http://{get_local_ip()}:{settings.port}",
            "page_title": video["filename"],
        }
    )


# --- API Endpoints ---

@router.get("/api/videos")
async def api_list_videos(
    sort: str = "date_added",
    order: str = "DESC",
    folder: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 30,
    offset: int = 0
):
    """API: List videos with filtering."""
    videos = db.get_media_files(
        file_type="video", folder=folder,
        sort_by=sort, sort_order=order,
        limit=limit, offset=offset, search=search
    )
    for v in videos:
        v["size_formatted"] = format_size(v.get("size", 0))
        v["duration_formatted"] = format_duration(v.get("duration", 0))
        v["stream_url"] = f"/api/stream/{urllib.parse.quote(v['path'], safe='')}"
        v["thumbnail_url"] = f"/api/thumbnail/{v['id']}" if v.get("thumbnail_path") else None

    return {"videos": videos, "total": db.get_media_count("video")}


@router.post("/api/watch-progress")
async def api_update_watch_progress(request: Request):
    """API: Update watch progress for a video."""
    data = await request.json()
    media_id = data.get("media_id")
    position = data.get("position", 0)
    duration = data.get("duration", 0)

    if not media_id:
        raise HTTPException(status_code=400, detail="media_id required")

    db.update_watch_history(media_id, position, duration)
    return {"success": True}


@router.post("/api/favorite")
async def api_toggle_favorite(request: Request):
    """API: Toggle favorite status."""
    data = await request.json()
    media_id = data.get("media_id")
    if not media_id:
        raise HTTPException(status_code=400, detail="media_id required")

    is_fav = db.toggle_favorite(media_id)
    return {"success": True, "is_favorite": is_fav}


@router.get("/api/thumbnail/{media_id}")
async def api_get_thumbnail(media_id: int):
    """Serve a cached thumbnail."""
    media = db.get_media_file_by_id(media_id)
    if not media or not media.get("thumbnail_path"):
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    thumb_path = Path(media["thumbnail_path"])
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing")

    from fastapi.responses import FileResponse
    return FileResponse(str(thumb_path), media_type="image/jpeg")
