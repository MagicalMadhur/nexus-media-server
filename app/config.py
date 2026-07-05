"""
Configuration management for the media server.
Settings are stored in SQLite and loaded at startup.
"""
import json
import os
import socket
import sqlite3
from pathlib import Path
from typing import Optional

# Base directories
PROJECT_NAME = "NexusMedia"
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"
TRANSCODED_DIR = DATA_DIR / "transcoded"
UPLOADS_DIR = BASE_DIR / "uploads"
DB_PATH = DATA_DIR / f"{PROJECT_NAME}.db"

# Ensure directories exist
for d in [DATA_DIR, THUMBNAILS_DIR, TRANSCODED_DIR, UPLOADS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# Default settings
DEFAULT_SETTINGS = {
    "media_folders": [],
    "upload_folder": str(UPLOADS_DIR),
    "allowed_video_extensions": [".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".wmv", ".m4v", ".ts"],
    "allowed_audio_extensions": [".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma", ".opus"],
    "allowed_image_extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".tiff", ".ico"],
    "allowed_document_extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv", ".json", ".xml"],
    "max_upload_size_mb": 50000,
    "thumbnail_quality": 85,
    "thumbnail_size": [320, 180],
    "streaming_chunk_size": 1048576,  # 1MB
    "enable_transcoding": True,
    "theme": "dark",
    "port": 8000,
    "scan_on_startup": True,
    "password": "",
}

# MIME type mappings
VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".flv": "video/x-flv",
    ".webm": "video/webm",
    ".wmv": "video/x-ms-wmv",
    ".m4v": "video/x-m4v",
    ".ts": "video/mp2t",
}

AUDIO_MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".wma": "audio/x-ms-wma",
    ".opus": "audio/opus",
}

IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".tiff": "image/tiff",
    ".ico": "image/x-icon",
}

# File icons mapping
FILE_ICONS = {
    # Videos
    ".mp4": "fa-file-video", ".mkv": "fa-file-video", ".avi": "fa-file-video",
    ".mov": "fa-file-video", ".flv": "fa-file-video", ".webm": "fa-file-video",
    ".wmv": "fa-file-video", ".m4v": "fa-file-video",
    # Audio
    ".mp3": "fa-file-audio", ".flac": "fa-file-audio", ".wav": "fa-file-audio",
    ".aac": "fa-file-audio", ".ogg": "fa-file-audio", ".m4a": "fa-file-audio",
    # Images
    ".jpg": "fa-file-image", ".jpeg": "fa-file-image", ".png": "fa-file-image",
    ".gif": "fa-file-image", ".bmp": "fa-file-image", ".webp": "fa-file-image",
    ".svg": "fa-file-image",
    # Documents
    ".pdf": "fa-file-pdf", ".doc": "fa-file-word", ".docx": "fa-file-word",
    ".xls": "fa-file-excel", ".xlsx": "fa-file-excel",
    ".ppt": "fa-file-powerpoint", ".pptx": "fa-file-powerpoint",
    ".txt": "fa-file-lines", ".md": "fa-file-lines",
    ".csv": "fa-file-csv", ".json": "fa-file-code", ".xml": "fa-file-code",
    # Archives
    ".zip": "fa-file-zipper", ".rar": "fa-file-zipper", ".7z": "fa-file-zipper",
    ".tar": "fa-file-zipper", ".gz": "fa-file-zipper",
    # Code
    ".py": "fa-file-code", ".js": "fa-file-code", ".html": "fa-file-code",
    ".css": "fa-file-code", ".java": "fa-file-code", ".cpp": "fa-file-code",
}


def get_local_ip() -> str:
    """Detect the local LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Doesn't actually send data, just determines the local IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class Settings:
    """Manages application settings with SQLite persistence."""

    _instance: Optional["Settings"] = None
    _settings: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """Load settings from database, falling back to defaults."""
        self._settings = DEFAULT_SETTINGS.copy()
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()
            cursor.execute("SELECT key, value FROM settings")
            for key, value in cursor.fetchall():
                try:
                    self._settings[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    self._settings[key] = value
            conn.close()
        except Exception as e:
            print(f"Warning: Could not load settings from DB: {e}")

    def get(self, key: str, default=None):
        return self._settings.get(key, default)

    def set(self, key: str, value):
        self._settings[key] = value
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Could not save setting '{key}': {e}")

    def get_all(self) -> dict:
        return self._settings.copy()

    def update(self, updates: dict):
        for key, value in updates.items():
            self.set(key, value)

    @property
    def media_folders(self) -> list:
        return self.get("media_folders", [])

    @property
    def upload_folder(self) -> str:
        return self.get("upload_folder", str(UPLOADS_DIR))

    @property
    def theme(self) -> str:
        return self.get("theme", "dark")

    @property
    def port(self) -> int:
        return self.get("port", 8000)

    @property
    def max_upload_size(self) -> int:
        return self.get("max_upload_size_mb", 50000) * 1024 * 1024

    @property
    def streaming_chunk_size(self) -> int:
        return self.get("streaming_chunk_size", 1048576)


def get_file_icon(filename: str) -> str:
    """Get Font Awesome icon class for a file extension."""
    ext = Path(filename).suffix.lower()
    return FILE_ICONS.get(ext, "fa-file")


def get_mime_type(filename: str) -> str:
    """Get MIME type for a file."""
    ext = Path(filename).suffix.lower()
    if ext in VIDEO_MIME_TYPES:
        return VIDEO_MIME_TYPES[ext]
    if ext in AUDIO_MIME_TYPES:
        return AUDIO_MIME_TYPES[ext]
    if ext in IMAGE_MIME_TYPES:
        return IMAGE_MIME_TYPES[ext]
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".txt":
        return "text/plain"
    return "application/octet-stream"


def is_video(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_MIME_TYPES


def is_audio(filename: str) -> bool:
    return Path(filename).suffix.lower() in AUDIO_MIME_TYPES


def is_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_MIME_TYPES


def is_document(filename: str) -> bool:
    settings = Settings()
    return Path(filename).suffix.lower() in settings.get("allowed_document_extensions", [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv", ".json", ".xml"])


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f} {units[i]}"


def format_duration(seconds: float) -> str:
    """Format seconds to HH:MM:SS or MM:SS."""
    if not seconds or seconds <= 0:
        return "00:00"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
