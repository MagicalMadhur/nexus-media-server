"""
Magic Cast Route for forcing connected TVs to display a specific file.
"""
import os
import shutil
import uuid
import json
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from app.config import BASE_DIR, Settings

router = APIRouter()
settings = Settings()

CAST_DIR = os.path.join(BASE_DIR, "data", "MagicCasts")
os.makedirs(CAST_DIR, exist_ok=True)

# Active WebSocket connections
active_connections: List[WebSocket] = []

@router.websocket("/ws/cast")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # We don't expect messages from the client right now, just keeping it alive
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

@router.post("/api/cast/upload")
async def upload_magic_cast(file: UploadFile = File(...), password: str = Form(None)):
    try:
        # Save file to MagicCasts folder
        file_ext = os.path.splitext(file.filename)[1].lower()
        unique_name = f"cast_{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(CAST_DIR, unique_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        file_url = f"/api/cast/view/{unique_name}"
        viewer_url = f"/cast/viewer?url={file_url}"
        if password:
            import urllib.parse
            viewer_url += f"&pwd={urllib.parse.quote(password)}"
        
        # Broadcast to all TVs
        dead_connections = []
        for connection in active_connections:
            try:
                await connection.send_text(json.dumps({
                    "type": "force_cast",
                    "url": viewer_url
                }))
            except Exception:
                dead_connections.append(connection)
                
        for dc in dead_connections:
            if dc in active_connections:
                active_connections.remove(dc)
            
        return {"success": True, "url": file_url}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

from fastapi.responses import FileResponse

@router.get("/api/cast/view/{filename}")
async def view_magic_cast(filename: str):
    file_path = os.path.join(CAST_DIR, filename)
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "Cast not found"})
    return FileResponse(file_path)

from fastapi import Request
from fastapi.responses import HTMLResponse

@router.get("/cast/viewer", response_class=HTMLResponse)
async def magic_cast_viewer(request: Request, url: str):
    """Render a dedicated custom viewer for Magic Casts"""
    return request.app.state.templates.TemplateResponse(
        "cast_viewer.html",
        {"request": request, "url": url}
    )
