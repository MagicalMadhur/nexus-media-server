"""
Document library routes.
Displays scanned PDF and text documents in a list view.
"""
import urllib.parse
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.config import Settings, format_size, get_file_icon
from app import database as db

router = APIRouter(tags=["documents"])


@router.get("/documents", response_class=HTMLResponse)
async def document_library(request: Request,
                           folder: Optional[str] = None,
                           sort: str = "date_added",
                           order: str = "DESC",
                           page: int = 1):
    """Render the document library page."""
    settings = Settings()
    limit = 50
    offset = (page - 1) * limit

    documents = db.get_media_files(
        file_type="document",
        folder=folder,
        sort_by=sort,
        sort_order=order,
        limit=limit,
        offset=offset,
    )

    for d in documents:
        d["size_formatted"] = format_size(d.get("size", 0))
        d["stream_url"] = f"/api/stream/{urllib.parse.quote(d['path'], safe='')}"
        d["icon"] = get_file_icon(d["filename"])
        d["is_favorite"] = db.is_favorite(d["id"])

    total = db.get_media_count("document")
    total_pages = max(1, (total + limit - 1) // limit)
    folders = db.get_unique_folders("document")

    return request.app.state.templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "documents": documents,
            "total_documents": total,
            "current_page": page,
            "total_pages": total_pages,
            "sort": sort,
            "order": order,
            "current_folder": folder,
            "folders": folders,
            "theme": settings.theme,
            "page_title": "Documents",
        }
    )
