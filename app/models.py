"""
Pydantic models for API request/response schemas.
"""
from pydantic import BaseModel
from typing import Optional, List


class FileItem(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int = 0
    size_formatted: str = ""
    extension: str = ""
    icon: str = "fa-file"
    mime_type: str = ""
    modified: float = 0
    modified_formatted: str = ""
    is_video: bool = False
    is_audio: bool = False
    is_image: bool = False
    thumbnail_url: Optional[str] = None
    media_id: Optional[int] = None


class UploadResponse(BaseModel):
    success: bool
    filename: str
    path: str
    size: int
    message: str = ""


class MediaFileResponse(BaseModel):
    id: int
    path: str
    filename: str
    extension: str
    file_type: str
    size: int
    size_formatted: str = ""
    duration: Optional[float] = None
    duration_formatted: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None
    resolution: str = ""
    thumbnail_url: Optional[str] = None
    stream_url: str = ""
    parent_folder: str = ""
    date_added: Optional[float] = None
    is_favorite: bool = False
    watch_progress: float = 0
    watch_position: float = 0
    # Audio
    artist: Optional[str] = None
    album: Optional[str] = None
    title: Optional[str] = None


class SearchResult(BaseModel):
    files: List[FileItem] = []
    media: List[MediaFileResponse] = []
    total: int = 0
    query: str = ""


class SettingsUpdate(BaseModel):
    media_folders: Optional[List[str]] = None
    upload_folder: Optional[str] = None
    max_upload_size_mb: Optional[int] = None
    thumbnail_quality: Optional[int] = None
    enable_transcoding: Optional[bool] = None
    theme: Optional[str] = None
    port: Optional[int] = None
    scan_on_startup: Optional[bool] = None
    password: Optional[str] = None


class WatchProgressUpdate(BaseModel):
    media_id: int
    position: float
    duration: float


class FavoriteToggle(BaseModel):
    media_id: int


class StatsResponse(BaseModel):
    video_count: int = 0
    audio_count: int = 0
    image_count: int = 0
    document_count: int = 0
    total_count: int = 0
    total_size: int = 0
    total_size_formatted: str = ""
    favorites_count: int = 0
