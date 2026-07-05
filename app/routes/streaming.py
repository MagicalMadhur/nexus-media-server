"""
HTTP Range Request streaming for video/audio files.
Supports partial content, seeking, and large file streaming.
"""
import os
import stat
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import StreamingResponse, Response

from app.config import Settings, get_mime_type, BASE_DIR

router = APIRouter(prefix="/api/stream", tags=["streaming"])

# Security: Resolve safe base paths once
SAFE_BASES = []


def _get_safe_bases():
    """Get list of allowed base directories for streaming."""
    global SAFE_BASES
    settings = Settings()
    bases = []
    for folder in settings.media_folders:
        p = Path(folder).resolve()
        if p.exists():
            bases.append(p)
    # Also allow uploads directory
    upload_dir = Path(settings.upload_folder).resolve()
    if upload_dir.exists():
        bases.append(upload_dir)
    SAFE_BASES = bases
    return bases


def _is_safe_path(file_path: Path) -> bool:
    """Prevent directory traversal attacks."""
    resolved = file_path.resolve()
    bases = _get_safe_bases()
    # If no bases configured, allow any path (for initial setup)
    if not bases:
        return resolved.exists() and resolved.is_file()
    return any(
        str(resolved).startswith(str(base))
        for base in bases
    ) and resolved.exists() and resolved.is_file()


def _range_generator(file_path: str, start: int, end: int, chunk_size: int = 1024 * 1024):
    """Generator that yields chunks of a file from start to end byte."""
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = f.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data


@router.get("/{file_path:path}")
async def stream_file(request: Request, file_path: str):
    """
    Stream a file with HTTP Range Request support.
    
    This enables:
    - Instant seeking without re-downloading
    - Pause/resume
    - Large file support (20GB+)
    - Buffer-free LAN playback
    """
    settings = Settings()
    chunk_size = settings.streaming_chunk_size

    # Decode the file path
    # The path comes URL-encoded, decode it
    full_path = Path(file_path)

    # If it's not absolute, try to find it in media folders
    if not full_path.is_absolute():
        # Try each media folder
        found = False
        for folder in settings.media_folders:
            candidate = Path(folder) / file_path
            if candidate.exists() and candidate.is_file():
                full_path = candidate
                found = True
                break
        # Also check uploads
        if not found:
            candidate = Path(settings.upload_folder) / file_path
            if candidate.exists() and candidate.is_file():
                full_path = candidate
                found = True
        if not found:
            raise HTTPException(status_code=404, detail="File not found")

    full_path = full_path.resolve()

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Get file info
    file_size = full_path.stat().st_size
    content_type = get_mime_type(full_path.name)

    # Parse Range header
    range_header = request.headers.get("range")

    if range_header:
        try:
            range_spec = range_header.replace("bytes=", "").strip()
            range_parts = range_spec.split("-")
            start = int(range_parts[0]) if range_parts[0] else 0
            end = int(range_parts[1]) if range_parts[1] else file_size - 1
        except (ValueError, IndexError):
            start = 0
            end = file_size - 1

        # Clamp values
        start = max(0, start)
        end = min(end, file_size - 1)

        if start >= file_size:
            raise HTTPException(
                status_code=416,
                detail="Range Not Satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"}
            )

        content_length = end - start + 1

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        }

        return StreamingResponse(
            _range_generator(str(full_path), start, end, chunk_size),
            status_code=206,
            headers=headers,
            media_type=content_type,
        )
    else:
        # No range header — stream the entire file
        # For large files, still stream in chunks
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        }

        return StreamingResponse(
            _range_generator(str(full_path), 0, file_size - 1, chunk_size),
            status_code=200,
            headers=headers,
            media_type=content_type,
        )


@router.head("/{file_path:path}")
async def stream_file_head(request: Request, file_path: str):
    """HEAD request for stream — browsers use this to determine Range support."""
    settings = Settings()
    full_path = Path(file_path)

    if not full_path.is_absolute():
        for folder in settings.media_folders:
            candidate = Path(folder) / file_path
            if candidate.exists():
                full_path = candidate
                break
        else:
            candidate = Path(settings.upload_folder) / file_path
            if candidate.exists():
                full_path = candidate

    full_path = full_path.resolve()
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    file_size = full_path.stat().st_size
    content_type = get_mime_type(full_path.name)

    return Response(
        status_code=200,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=86400",
        }
    )
