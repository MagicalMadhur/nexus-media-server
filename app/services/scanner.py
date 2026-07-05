"""
Media scanner service.
Scans configured folders for media files, extracts metadata,
generates thumbnails, and stores in database.
Uses watchdog for real-time filesystem monitoring.
"""
import os
import time
import subprocess
import json
import threading
from pathlib import Path
from typing import Optional, Dict

from app.config import (
    Settings, is_video, is_audio, is_image, is_document,
    get_mime_type, THUMBNAILS_DIR, DATA_DIR
)
from app import database as db

# Scanner state
_scan_running = False
_scan_progress = {"current": 0, "total": 0, "current_file": "", "status": "idle"}


def get_scan_progress() -> dict:
    return _scan_progress.copy()


def _extract_video_metadata(file_path: str) -> Dict:
    """Extract video metadata using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {}

        data = json.loads(result.stdout)
        video_stream = None
        audio_streams = []

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and not video_stream:
                video_stream = stream
            elif stream.get("codec_type") == "audio":
                audio_streams.append(stream)

        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0))

        meta = {
            "duration": duration,
            "bitrate": int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else None,
        }

        if video_stream:
            meta["width"] = int(video_stream.get("width", 0))
            meta["height"] = int(video_stream.get("height", 0))
            meta["codec"] = video_stream.get("codec_name", "")

        return meta
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, Exception) as e:
        return {}


def _extract_audio_metadata(file_path: str) -> Dict:
    """Extract audio metadata using mutagen."""
    try:
        import mutagen
        from mutagen.easyid3 import EasyID3
        from mutagen.mp3 import MP3
        from mutagen.flac import FLAC

        audio = mutagen.File(file_path, easy=True)
        if not audio:
            return {}

        meta = {
            "duration": audio.info.length if hasattr(audio, "info") and hasattr(audio.info, "length") else None,
            "artist": audio.get("artist", [None])[0] if audio.get("artist") else None,
            "album": audio.get("album", [None])[0] if audio.get("album") else None,
            "title": audio.get("title", [None])[0] if audio.get("title") else None,
        }

        # Try to get track number
        track = audio.get("tracknumber", [None])[0] if audio.get("tracknumber") else None
        if track:
            try:
                meta["track_number"] = int(track.split("/")[0])
            except (ValueError, IndexError):
                pass

        # Extract album art
        try:
            raw_audio = mutagen.File(file_path)
            if hasattr(raw_audio, "pictures") and raw_audio.pictures:
                art_data = raw_audio.pictures[0].data
                art_path = THUMBNAILS_DIR / f"albumart_{Path(file_path).stem}.jpg"
                with open(art_path, "wb") as f:
                    f.write(art_data)
                meta["album_art_path"] = str(art_path)
            elif hasattr(raw_audio, "tags"):
                tags = raw_audio.tags
                if tags:
                    # MP3 APIC tags
                    for key in tags:
                        if "APIC" in str(key):
                            art_data = tags[key].data
                            art_path = THUMBNAILS_DIR / f"albumart_{Path(file_path).stem}.jpg"
                            with open(art_path, "wb") as f:
                                f.write(art_data)
                            meta["album_art_path"] = str(art_path)
                            break
        except Exception:
            pass

        return meta
    except Exception as e:
        return {}


def _generate_video_thumbnail(file_path: str, media_id: int) -> Optional[str]:
    """Generate a thumbnail for a video file using ffmpeg."""
    try:
        thumb_path = THUMBNAILS_DIR / f"thumb_{media_id}.jpg"
        if thumb_path.exists():
            return str(thumb_path)

        # Capture frame at 10% of video duration
        cmd = [
            "ffmpeg", "-i", file_path,
            "-ss", "00:00:05",  # 5 seconds in
            "-vframes", "1",
            "-vf", "scale=320:-1",
            "-q:v", "5",
            "-y",
            str(thumb_path)
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode == 0 and thumb_path.exists():
            return str(thumb_path)
        return None
    except Exception:
        return None


def _generate_image_thumbnail(file_path: str, media_id: int) -> Optional[str]:
    """Generate a thumbnail for an image file using Pillow."""
    try:
        from PIL import Image

        thumb_path = THUMBNAILS_DIR / f"thumb_{media_id}.jpg"
        if thumb_path.exists():
            return str(thumb_path)

        settings = Settings()
        size = tuple(settings.get("thumbnail_size", [320, 180]))
        quality = settings.get("thumbnail_quality", 85)

        img = Image.open(file_path)
        img.thumbnail((size[0], size[0]))  # Maintain aspect ratio

        # Handle RGBA
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img.save(str(thumb_path), "JPEG", quality=quality)
        return str(thumb_path)
    except Exception:
        return None


def _get_image_exif(file_path: str) -> Optional[dict]:
    """Extract EXIF data from an image."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        img = Image.open(file_path)
        exif_data = img._getexif()
        if not exif_data:
            return None

        exif = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if isinstance(value, bytes):
                continue  # Skip binary data
            exif[str(tag)] = str(value)
        return exif
    except Exception:
        return None


def scan_file(file_path: Path) -> Optional[int]:
    """Scan a single file and add/update it in the database."""
    try:
        if not file_path.exists() or not file_path.is_file():
            return None

        ext = file_path.suffix.lower()
        stat = file_path.stat()

        # Determine file type
        if is_video(file_path.name):
            file_type = "video"
        elif is_audio(file_path.name):
            file_type = "audio"
        elif is_image(file_path.name):
            file_type = "image"
        elif is_document(file_path.name):
            file_type = "document"
        else:
            file_type = "other"

        data = {
            "path": str(file_path),
            "filename": file_path.name,
            "extension": ext,
            "file_type": file_type,
            "size": stat.st_size,
            "mime_type": get_mime_type(file_path.name),
            "parent_folder": str(file_path.parent),
            "date_modified": stat.st_mtime,
            "duration": None,
            "width": None,
            "height": None,
            "codec": None,
            "bitrate": None,
            "exif_data": None,
            "artist": None,
            "album": None,
            "title": None,
            "track_number": None,
            "album_art_path": None,
            "thumbnail_path": None,
            "tags": [],
        }

        # Extract type-specific metadata
        if file_type == "video":
            meta = _extract_video_metadata(str(file_path))
            data.update({k: v for k, v in meta.items() if v is not None})
        elif file_type == "audio":
            meta = _extract_audio_metadata(str(file_path))
            data.update({k: v for k, v in meta.items() if v is not None})
        elif file_type == "image":
            exif = _get_image_exif(str(file_path))
            if exif:
                data["exif_data"] = exif
            # Get image dimensions
            try:
                from PIL import Image
                img = Image.open(str(file_path))
                data["width"], data["height"] = img.size
            except Exception:
                pass

        # Save to database
        media_id = db.upsert_media_file(data)

        # Generate thumbnails in background
        if file_type == "video":
            thumb = _generate_video_thumbnail(str(file_path), media_id)
            if thumb:
                conn = db.get_db()
                conn.execute("UPDATE media_files SET thumbnail_path = ? WHERE id = ?", (thumb, media_id))
                conn.commit()
                conn.close()
        elif file_type == "image":
            thumb = _generate_image_thumbnail(str(file_path), media_id)
            if thumb:
                conn = db.get_db()
                conn.execute("UPDATE media_files SET thumbnail_path = ? WHERE id = ?", (thumb, media_id))
                conn.commit()
                conn.close()

        return media_id
    except Exception as e:
        print(f"  [!] Error scanning {file_path}: {e}")
        return None


def scan_folder(folder_path: str):
    """Scan a folder recursively for media files."""
    global _scan_progress

    settings = Settings()
    allowed_exts = set(
        settings.get("allowed_video_extensions", []) +
        settings.get("allowed_audio_extensions", []) +
        settings.get("allowed_image_extensions", []) +
        settings.get("allowed_document_extensions", [])
    )

    folder = Path(folder_path)
    if not folder.exists():
        print(f"  [!] Folder does not exist: {folder_path}")
        return

    # Count files first
    files_to_scan = []
    for item in folder.rglob("*"):
        if item.is_file() and item.suffix.lower() in allowed_exts and not item.name.startswith("."):
            files_to_scan.append(item)

    _scan_progress["total"] += len(files_to_scan)
    print(f"  [DIR] Scanning {folder_path}: {len(files_to_scan)} media files found")

    for i, file_path in enumerate(files_to_scan):
        _scan_progress["current"] += 1
        _scan_progress["current_file"] = file_path.name
        scan_file(file_path)


def scan_all_folders():
    """Scan all configured media folders."""
    global _scan_running, _scan_progress

    if _scan_running:
        print("  [i] Scan already running")
        return

    _scan_running = True
    _scan_progress = {"current": 0, "total": 0, "current_file": "", "status": "scanning"}

    settings = Settings()
    folders = settings.media_folders

    print(f"\n[SCAN] Starting media scan of {len(folders)} folder(s)...")
    start_time = time.time()

    # Also scan uploads
    upload_dir = settings.upload_folder
    all_folders = folders + [upload_dir]

    for folder in all_folders:
        scan_folder(folder)

    # Clean up deleted files
    _clean_deleted_files()

    elapsed = time.time() - start_time
    _scan_progress["status"] = "complete"
    _scan_running = False

    stats = db.get_stats()
    print(f"[OK] Scan complete in {elapsed:.1f}s")
    print(f"   Videos: {stats['video_count']} | Images: {stats['image_count']} | Audio: {stats['audio_count']}")


def _clean_deleted_files():
    """Remove database entries for files that no longer exist."""
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, path FROM media_files")
    rows = cursor.fetchall()

    deleted = 0
    for row in rows:
        if not Path(row["path"]).exists():
            cursor.execute("DELETE FROM media_files WHERE id = ?", (row["id"],))
            deleted += 1

    if deleted:
        conn.commit()
        print(f"  [DEL] Removed {deleted} entries for deleted files")
    conn.close()


# --- Watchdog File System Monitor ---

_observer = None


def start_watchdog():
    """Start watching media folders for changes."""
    global _observer
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        settings = Settings()

        class MediaEventHandler(FileSystemEventHandler):
            def __init__(self):
                self._debounce = {}

            def _should_process(self, path):
                ext = Path(path).suffix.lower()
                allowed = set(
                    settings.get("allowed_video_extensions", []) +
                    settings.get("allowed_audio_extensions", []) +
                    settings.get("allowed_image_extensions", []) +
                    settings.get("allowed_document_extensions", [])
                )
                return ext in allowed

            def on_created(self, event):
                if not event.is_directory and self._should_process(event.src_path):
                    # Debounce - wait for file write to complete
                    def delayed_scan():
                        time.sleep(2)
                        print(f"  [NEW] File detected: {Path(event.src_path).name}")
                        scan_file(Path(event.src_path))

                    threading.Thread(target=delayed_scan, daemon=True).start()

            def on_deleted(self, event):
                if not event.is_directory:
                    db.delete_media_file(event.src_path)

            def on_moved(self, event):
                if not event.is_directory:
                    db.delete_media_file(event.src_path)
                    if self._should_process(event.dest_path):
                        scan_file(Path(event.dest_path))

        handler = MediaEventHandler()
        _observer = Observer()

        folders = settings.media_folders + [settings.upload_folder]
        for folder in folders:
            if Path(folder).exists():
                _observer.schedule(handler, folder, recursive=True)
                print(f"  [WATCH] Watching: {folder}")

        _observer.start()
        print("[OK] File watcher started")
    except ImportError:
        print("  [!] watchdog not installed, file watching disabled")
    except Exception as e:
        print(f"  [!] Could not start file watcher: {e}")


def stop_watchdog():
    """Stop the file system watcher."""
    global _observer
    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None
        print("[OK] File watcher stopped")
