"""
WebRTC Signaling Server and Live Stream Routes
"""
import uuid
from typing import Dict
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from app.config import Settings

router = APIRouter(tags=["webrtc"])

# WebRTC State
broadcaster_ws = None
viewers: Dict[str, WebSocket] = {}

@router.get("/live", response_class=HTMLResponse)
async def live_stream_page(request: Request):
    settings = Settings()
    return request.app.state.templates.TemplateResponse(
        "live_stream.html",
        {
            "request": request,
            "theme": settings.theme,
            "page_title": "Live Screen Share",
            "broadcaster_active": broadcaster_ws is not None
        }
    )

@router.websocket("/ws/webrtc")
async def webrtc_signaling(websocket: WebSocket):
    global broadcaster_ws
    await websocket.accept()
    
    client_id = str(uuid.uuid4())
    is_broadcaster = False
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "broadcaster_join":
                if broadcaster_ws is not None:
                    await websocket.send_json({"type": "error", "message": "Another stream is already active."})
                else:
                    broadcaster_ws = websocket
                    is_broadcaster = True
                    # Notify existing viewers that a stream started
                    for v_id, v_ws in viewers.items():
                        await v_ws.send_json({"type": "broadcaster_connected"})
                        
            elif msg_type == "viewer_join":
                viewers[client_id] = websocket
                if broadcaster_ws:
                    await broadcaster_ws.send_json({"type": "viewer_joined", "viewer_id": client_id})
                else:
                    await websocket.send_json({"type": "no_broadcaster"})
                    
            elif msg_type == "offer" and is_broadcaster:
                target = data.get("viewer_id")
                if target in viewers:
                    await viewers[target].send_json({
                        "type": "offer",
                        "sdp": data.get("sdp")
                    })
                    
            elif msg_type == "answer" and not is_broadcaster:
                if broadcaster_ws:
                    await broadcaster_ws.send_json({
                        "type": "answer",
                        "viewer_id": client_id,
                        "sdp": data.get("sdp")
                    })
                    
            elif msg_type == "ice_candidate":
                candidate = data.get("candidate")
                if is_broadcaster:
                    target = data.get("viewer_id")
                    if target in viewers:
                        await viewers[target].send_json({
                            "type": "ice_candidate",
                            "candidate": candidate
                        })
                else:
                    if broadcaster_ws:
                        await broadcaster_ws.send_json({
                            "type": "ice_candidate",
                            "viewer_id": client_id,
                            "candidate": candidate
                        })
                        
    except WebSocketDisconnect:
        if is_broadcaster:
            broadcaster_ws = None
            for v_id, v_ws in viewers.items():
                try:
                    await v_ws.send_json({"type": "broadcaster_disconnected"})
                except:
                    pass
        else:
            if client_id in viewers:
                del viewers[client_id]
            if broadcaster_ws:
                try:
                    await broadcaster_ws.send_json({"type": "viewer_left", "viewer_id": client_id})
                except:
                    pass
