"""
Photo gallery routes.
Pinterest-style layout with lightbox, EXIF info, slideshow.
"""
import urllib.parse
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.config import Settings, format_size, is_image
from app import database as db

router = APIRouter(tags=["photos"])


@router.get("/photos", response_class=HTMLResponse)
async def photo_gallery(request: Request,
                        folder: Optional[str] = None,
                        sort: str = "date_added",
                        order: str = "DESC",
                        page: int = 1):
    """Render the photo gallery page."""
    settings = Settings()
    limit = 40
    offset = (page - 1) * limit

    photos = db.get_media_files(
        file_type="image",
        folder=folder,
        sort_by=sort,
        sort_order=order,
        limit=limit,
        offset=offset,
    )

    for p in photos:
        p["size_formatted"] = format_size(p.get("size", 0))
        p["stream_url"] = f"/api/stream/{urllib.parse.quote(p['path'], safe='')}"
        p["thumbnail_url"] = f"/api/thumbnail/{p['id']}" if p.get("thumbnail_path") else p["stream_url"]
        p["is_favorite"] = db.is_favorite(p["id"])

    total = db.get_media_count("image")
    total_pages = max(1, (total + limit - 1) // limit)
    folders = db.get_unique_folders("image")

    return request.app.state.templates.TemplateResponse(
        "photo_gallery.html",
        {
            "request": request,
            "photos": photos,
            "total_photos": total,
            "current_page": page,
            "total_pages": total_pages,
            "sort": sort,
            "order": order,
            "current_folder": folder,
            "folders": folders,
            "theme": settings.theme,
            "page_title": "Photo Gallery",
        }
    )


@router.get("/api/photos")
async def api_list_photos(
    folder: Optional[str] = None,
    sort: str = "date_added",
    order: str = "DESC",
    limit: int = 40,
    offset: int = 0,
):
    photos = db.get_media_files(
        file_type="image", folder=folder,
        sort_by=sort, sort_order=order,
        limit=limit, offset=offset,
    )
    for p in photos:
        p["size_formatted"] = format_size(p.get("size", 0))
        p["stream_url"] = f"/api/stream/{urllib.parse.quote(p['path'], safe='')}"
        p["thumbnail_url"] = f"/api/thumbnail/{p['id']}" if p.get("thumbnail_path") else p["stream_url"]
    return {"photos": photos, "total": db.get_media_count("image")}
