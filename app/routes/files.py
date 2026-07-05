"""
File explorer and upload routes.
Full file management: browse, upload, create, rename, delete, move, copy, zip download.
"""
import os
import io
import shutil
import zipfile
import time
import urllib.parse
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import asyncio

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.config import (
    Settings, format_size, get_file_icon, get_mime_type,
    is_video, is_audio, is_image, BASE_DIR
)
from app import database as db

router = APIRouter(tags=["files"])


def _safe_resolve(path_str: str, settings: Settings) -> Path:
    """Resolve a path safely, preventing directory traversal."""
    p = Path(path_str).resolve()
    # Allow access to media folders, upload folder
    allowed = [Path(f).resolve() for f in settings.media_folders]
    allowed.append(Path(settings.upload_folder).resolve())

    if not allowed:
        # No folders configured yet, allow any existing path
        if p.exists():
            return p
        raise HTTPException(status_code=403, detail="Access denied")

    for base in allowed:
        try:
            p.relative_to(base)
            return p
        except ValueError:
            continue

    raise HTTPException(status_code=403, detail="Access denied — path outside allowed directories")


def _get_file_info(path: Path) -> dict:
    """Get file/folder info dictionary."""
    try:
        stat = path.stat()
        is_dir = path.is_dir()
        ext = path.suffix.lower() if not is_dir else ""
        return {
            "name": path.name,
            "path": str(path),
            "is_dir": is_dir,
            "size": stat.st_size if not is_dir else 0,
            "size_formatted": format_size(stat.st_size) if not is_dir else "",
            "extension": ext,
            "icon": "fa-folder" if is_dir else get_file_icon(path.name),
            "mime_type": get_mime_type(path.name) if not is_dir else "",
            "modified": stat.st_mtime,
            "modified_formatted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "is_video": is_video(path.name) if not is_dir else False,
            "is_audio": is_audio(path.name) if not is_dir else False,
            "is_image": is_image(path.name) if not is_dir else False,
        }
    except (PermissionError, OSError) as e:
        return {
            "name": path.name,
            "path": str(path),
            "is_dir": False,
            "size": 0,
            "size_formatted": "",
            "extension": "",
            "icon": "fa-file",
            "mime_type": "",
            "modified": 0,
            "modified_formatted": "",
            "is_video": False,
            "is_audio": False,
            "is_image": False,
            "error": str(e),
        }


@router.get("/explorer", response_class=HTMLResponse)
@router.get("/explorer/{path_str:path}", response_class=HTMLResponse)
async def file_explorer(request: Request, path_str: str = ""):
    """Render the file explorer page."""
    settings = Settings()

    if not path_str:
        # Show root: list configured folders
        items = []
        for folder in settings.media_folders:
            fp = Path(folder)
            if fp.exists():
                items.append(_get_file_info(fp))
        upload_dir = Path(settings.upload_folder)
        if upload_dir.exists():
            items.append(_get_file_info(upload_dir))
        current_path = ""
        parent_path = ""
        breadcrumbs = [{"name": "Home", "path": ""}]
    else:
        current = _safe_resolve(path_str, settings)
        if not current.exists():
            raise HTTPException(status_code=404, detail="Path not found")

        if current.is_file():
            # If it's a file, go to parent directory
            current = current.parent

        items = []
        try:
            for item in sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.name.startswith('.'):
                    continue  # Skip hidden files
                items.append(_get_file_info(item))
        except PermissionError:
            pass

        current_path = str(current)
        parent_path = str(current.parent) if current.parent != current else ""

        # Build breadcrumbs
        breadcrumbs = [{"name": "Home", "path": ""}]
        parts = current.parts
        for i in range(len(parts)):
            partial = Path(*parts[:i + 1])
            breadcrumbs.append({
                "name": parts[i],
                "path": str(partial),
            })

    return request.app.state.templates.TemplateResponse(
        "explorer.html",
        {
            "request": request,
            "items": items,
            "current_path": current_path,
            "parent_path": parent_path,
            "breadcrumbs": breadcrumbs,
            "theme": settings.theme,
            "page_title": "File Explorer",
        }
    )


# --- File API Endpoints ---

@router.get("/api/files")
async def api_list_files(path: str = "", sort: str = "name", order: str = "asc"):
    """API: List files in a directory."""
    settings = Settings()

    if not path:
        items = []
        for folder in settings.media_folders:
            fp = Path(folder)
            if fp.exists():
                items.append(_get_file_info(fp))
        upload_dir = Path(settings.upload_folder)
        if upload_dir.exists():
            items.append(_get_file_info(upload_dir))
        return {"items": items, "path": "", "parent": ""}

    current = _safe_resolve(path, settings)
    if not current.exists() or not current.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    items = []
    try:
        for item in current.iterdir():
            if item.name.startswith('.'):
                continue
            items.append(_get_file_info(item))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Sort
    reverse = order.lower() == "desc"
    if sort == "name":
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()), reverse=reverse)
    elif sort == "size":
        items.sort(key=lambda x: (not x["is_dir"], x["size"]), reverse=reverse)
    elif sort == "date":
        items.sort(key=lambda x: (not x["is_dir"], x["modified"]), reverse=reverse)
    elif sort == "type":
        items.sort(key=lambda x: (not x["is_dir"], x["extension"]), reverse=reverse)
    else:
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

    return {
        "items": items,
        "path": str(current),
        "parent": str(current.parent) if current.parent != current else "",
    }


@router.post("/api/upload")
async def api_upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    destination: str = Form("")
):
    """API: Upload files with progress tracking."""
    settings = Settings()
    dest_dir = Path(destination) if destination else Path(settings.upload_folder)

    if not dest_dir.exists():
        dest_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for file in files:
        if not file.filename:
            continue

        # Sanitize filename
        safe_name = Path(file.filename).name
        target = dest_dir / safe_name

        # Handle name conflicts
        counter = 1
        while target.exists():
            stem = Path(safe_name).stem
            ext = Path(safe_name).suffix
            target = dest_dir / f"{stem} ({counter}){ext}"
            counter += 1

        try:
            # Stream write to disk
            total_written = 0
            with open(target, "wb") as f:
                while chunk := await file.read(1024 * 1024):  # 1MB chunks
                    f.write(chunk)
                    total_written += len(chunk)

            results.append({
                "success": True,
                "filename": target.name,
                "path": str(target),
                "size": total_written,
                "size_formatted": format_size(total_written),
            })
        except Exception as e:
            results.append({
                "success": False,
                "filename": safe_name,
                "error": str(e),
            })

    return {"results": results}


@router.post("/api/upload-chunk")
async def api_upload_chunk(
    request: Request,
    chunk: UploadFile = File(...),
    filename: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    destination: str = Form("")
):
    """API: Upload files in chunks to support massive files."""
    settings = Settings()
    dest_dir = Path(destination) if destination else Path(settings.upload_folder)

    if not dest_dir.exists():
        dest_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name
    final_target = dest_dir / safe_name

    if chunk_index == 0:
        # Handle conflicts only on first chunk
        counter = 1
        stem = Path(safe_name).stem
        ext = Path(safe_name).suffix
        while final_target.exists():
            final_target = dest_dir / f"{stem} ({counter}){ext}"
            counter += 1
        
        safe_name = final_target.name
        part_target = dest_dir / f"{safe_name}.part"
        # Create/truncate the part file
        part_target.write_bytes(b"")
    else:
        # For subsequent chunks, we use the resolved filename passed by the client
        part_target = dest_dir / f"{safe_name}.part"

    try:
        # Append chunk
        with open(part_target, "ab") as f:
            while data := await chunk.read(1024 * 1024):
                f.write(data)
                
        completed = chunk_index >= total_chunks - 1
        
        # Once all chunks are uploaded, rename to final file
        if completed:
            if final_target.exists():
                final_target.unlink()
            part_target.rename(final_target)
                
        return {
            "success": True, 
            "filename": safe_name,
            "completed": completed
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/create-folder")
async def api_create_folder(request: Request):
    """API: Create a new folder."""
    settings = Settings()
    data = await request.json()
    parent = data.get("parent", "")
    name = data.get("name", "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Folder name required")

    # Sanitize
    name = name.replace("/", "").replace("\\", "").replace("..", "")

    if parent:
        parent_path = _safe_resolve(parent, settings)
    else:
        parent_path = Path(settings.upload_folder)

    new_folder = parent_path / name
    if new_folder.exists():
        raise HTTPException(status_code=409, detail="Folder already exists")

    new_folder.mkdir(parents=True, exist_ok=True)
    return {"success": True, "path": str(new_folder), "name": name}


@router.post("/api/rename")
async def api_rename(request: Request):
    """API: Rename a file or folder."""
    settings = Settings()
    data = await request.json()
    path = data.get("path", "")
    new_name = data.get("new_name", "").strip()

    if not path or not new_name:
        raise HTTPException(status_code=400, detail="Path and new_name required")

    new_name = new_name.replace("/", "").replace("\\", "").replace("..", "")
    source = _safe_resolve(path, settings)
    target = source.parent / new_name

    if target.exists():
        raise HTTPException(status_code=409, detail="A file with that name already exists")

    source.rename(target)

    # Update database if it's a media file
    db.delete_media_file(str(source))

    return {"success": True, "old_path": str(source), "new_path": str(target)}


@router.post("/api/delete")
async def api_delete(request: Request):
    """API: Delete files or folders."""
    settings = Settings()
    data = await request.json()
    paths = data.get("paths", [])

    if not paths:
        raise HTTPException(status_code=400, detail="No paths specified")

    results = []
    for p in paths:
        try:
            target = _safe_resolve(p, settings)
            if target.is_dir():
                shutil.rmtree(str(target), ignore_errors=True)
            else:
                # Windows File Lock handling:
                # If a video was just playing, the OS might take a moment to release the file handle.
                max_retries = 3
                for i in range(max_retries):
                    try:
                        target.unlink()
                        break
                    except PermissionError as e:
                        if i == max_retries - 1:
                            raise e
                        await asyncio.sleep(0.5)
                        
            db.delete_media_file(str(target))
            results.append({"path": p, "success": True})
        except Exception as e:
            results.append({"path": p, "success": False, "error": str(e)})

    return {"results": results}


@router.post("/api/move")
async def api_move(request: Request):
    """API: Move files/folders to a new location."""
    settings = Settings()
    data = await request.json()
    paths = data.get("paths", [])
    destination = data.get("destination", "")

    if not paths or not destination:
        raise HTTPException(status_code=400, detail="paths and destination required")

    dest = _safe_resolve(destination, settings)
    if not dest.is_dir():
        raise HTTPException(status_code=400, detail="Destination must be a directory")

    results = []
    for p in paths:
        try:
            source = _safe_resolve(p, settings)
            target = dest / source.name
            shutil.move(str(source), str(target))
            db.delete_media_file(str(source))
            results.append({"path": p, "new_path": str(target), "success": True})
        except Exception as e:
            results.append({"path": p, "success": False, "error": str(e)})

    return {"results": results}


@router.post("/api/copy")
async def api_copy(request: Request):
    """API: Copy files/folders."""
    settings = Settings()
    data = await request.json()
    paths = data.get("paths", [])
    destination = data.get("destination", "")

    if not paths or not destination:
        raise HTTPException(status_code=400, detail="paths and destination required")

    dest = _safe_resolve(destination, settings)
    if not dest.is_dir():
        raise HTTPException(status_code=400, detail="Destination must be a directory")

    results = []
    for p in paths:
        try:
            source = _safe_resolve(p, settings)
            target = dest / source.name
            if source.is_dir():
                shutil.copytree(str(source), str(target))
            else:
                shutil.copy2(str(source), str(target))
            results.append({"path": p, "new_path": str(target), "success": True})
        except Exception as e:
            results.append({"path": p, "success": False, "error": str(e)})

    return {"results": results}


@router.get("/api/download-zip")
async def api_download_zip(paths: str = Query(...)):
    """API: Download multiple files/folders as ZIP."""
    settings = Settings()
    path_list = paths.split("|")

    if not path_list:
        raise HTTPException(status_code=400, detail="No paths specified")

    def zip_generator():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in path_list:
                try:
                    target = Path(p).resolve()
                    if target.is_file():
                        zf.write(str(target), target.name)
                    elif target.is_dir():
                        for file_path in target.rglob("*"):
                            if file_path.is_file():
                                arcname = str(file_path.relative_to(target.parent))
                                zf.write(str(file_path), arcname)
                except Exception:
                    continue
        buffer.seek(0)
        yield buffer.read()

    return StreamingResponse(
        zip_generator(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=download_{int(time.time())}.zip"}
    )


@router.get("/api/folder-size")
async def api_folder_size(path: str = Query(...)):
    """API: Calculate folder size."""
    settings = Settings()
    target = _safe_resolve(path, settings)

    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")

    total = 0
    file_count = 0
    folder_count = 0

    for item in target.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
            file_count += 1
        elif item.is_dir():
            folder_count += 1

    return {
        "path": str(target),
        "size": total,
        "size_formatted": format_size(total),
        "file_count": file_count,
        "folder_count": folder_count,
    }
