"""
Database setup and operations for the media server.
Uses SQLite for metadata storage, watch history, favorites, etc.
"""
import sqlite3
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from app.config import DB_PATH


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS media_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT NOT NULL,
            file_type TEXT NOT NULL,  -- 'video', 'audio', 'image', 'document', 'other'
            size INTEGER DEFAULT 0,
            mime_type TEXT,
            parent_folder TEXT,
            -- Video/Audio specific
            duration REAL,
            width INTEGER,
            height INTEGER,
            codec TEXT,
            bitrate INTEGER,
            -- Image specific
            exif_data TEXT,
            -- Audio specific
            artist TEXT,
            album TEXT,
            title TEXT,
            track_number INTEGER,
            album_art_path TEXT,
            -- Metadata
            thumbnail_path TEXT,
            date_added REAL DEFAULT (strftime('%s', 'now')),
            date_modified REAL,
            date_scanned REAL DEFAULT (strftime('%s', 'now')),
            tags TEXT DEFAULT '[]'
        );

        CREATE INDEX IF NOT EXISTS idx_media_type ON media_files(file_type);
        CREATE INDEX IF NOT EXISTS idx_media_ext ON media_files(extension);
        CREATE INDEX IF NOT EXISTS idx_media_folder ON media_files(parent_folder);
        CREATE INDEX IF NOT EXISTS idx_media_filename ON media_files(filename);
        CREATE INDEX IF NOT EXISTS idx_media_date ON media_files(date_added);

        CREATE TABLE IF NOT EXISTS watch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER UNIQUE NOT NULL,
            position REAL DEFAULT 0,
            duration REAL DEFAULT 0,
            progress REAL DEFAULT 0,  -- 0.0 to 1.0
            last_watched REAL DEFAULT (strftime('%s', 'now')),
            watch_count INTEGER DEFAULT 1,
            completed INTEGER DEFAULT 0,
            FOREIGN KEY (media_id) REFERENCES media_files(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_history_media ON watch_history(media_id);
        CREATE INDEX IF NOT EXISTS idx_history_date ON watch_history(last_watched);

        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER UNIQUE NOT NULL,
            date_added REAL DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (media_id) REFERENCES media_files(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS pinned_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            date_added REAL DEFAULT (strftime('%s', 'now'))
        );

        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            date_created REAL DEFAULT (strftime('%s', 'now')),
            date_modified REAL DEFAULT (strftime('%s', 'now'))
        );

        CREATE TABLE IF NOT EXISTS playlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            media_id INTEGER NOT NULL,
            position INTEGER DEFAULT 0,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            FOREIGN KEY (media_id) REFERENCES media_files(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    conn.commit()
    conn.close()
    print("✓ Database initialized")


# --- Media Files ---

def upsert_media_file(data: dict) -> int:
    """Insert or update a media file record. Returns the row ID."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO media_files (
            path, filename, extension, file_type, size, mime_type,
            parent_folder, duration, width, height, codec, bitrate,
            exif_data, artist, album, title, track_number,
            album_art_path, thumbnail_path, date_modified, tags
        ) VALUES (
            :path, :filename, :extension, :file_type, :size, :mime_type,
            :parent_folder, :duration, :width, :height, :codec, :bitrate,
            :exif_data, :artist, :album, :title, :track_number,
            :album_art_path, :thumbnail_path, :date_modified, :tags
        )
        ON CONFLICT(path) DO UPDATE SET
            size = :size,
            duration = :duration,
            width = :width,
            height = :height,
            codec = :codec,
            bitrate = :bitrate,
            exif_data = :exif_data,
            artist = :artist,
            album = :album,
            title = :title,
            track_number = :track_number,
            album_art_path = :album_art_path,
            thumbnail_path = :thumbnail_path,
            date_modified = :date_modified,
            date_scanned = strftime('%s', 'now'),
            tags = :tags
    """, {
        "path": data.get("path", ""),
        "filename": data.get("filename", ""),
        "extension": data.get("extension", ""),
        "file_type": data.get("file_type", "other"),
        "size": data.get("size", 0),
        "mime_type": data.get("mime_type", ""),
        "parent_folder": data.get("parent_folder", ""),
        "duration": data.get("duration"),
        "width": data.get("width"),
        "height": data.get("height"),
        "codec": data.get("codec"),
        "bitrate": data.get("bitrate"),
        "exif_data": json.dumps(data.get("exif_data")) if data.get("exif_data") else None,
        "artist": data.get("artist"),
        "album": data.get("album"),
        "title": data.get("title"),
        "track_number": data.get("track_number"),
        "album_art_path": data.get("album_art_path"),
        "thumbnail_path": data.get("thumbnail_path"),
        "date_modified": data.get("date_modified"),
        "tags": json.dumps(data.get("tags", [])),
    })

    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_media_files(file_type: Optional[str] = None, folder: Optional[str] = None,
                    sort_by: str = "date_added", sort_order: str = "DESC",
                    limit: int = 50, offset: int = 0,
                    search: Optional[str] = None) -> List[Dict]:
    """Get media files with filtering and sorting."""
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM media_files WHERE 1=1"
    params = []

    if file_type:
        query += " AND file_type = ?"
        params.append(file_type)

    if folder:
        query += " AND parent_folder = ?"
        params.append(folder)

    if search:
        query += " AND (filename LIKE ? OR path LIKE ? OR title LIKE ? OR artist LIKE ? OR album LIKE ?)"
        search_term = f"%{search}%"
        params.extend([search_term] * 5)

    allowed_sorts = {"date_added", "filename", "size", "duration", "date_modified"}
    if sort_by not in allowed_sorts:
        sort_by = "date_added"
    sort_order = "ASC" if sort_order.upper() == "ASC" else "DESC"

    query += f" ORDER BY {sort_by} {sort_order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_media_file_by_id(media_id: int) -> Optional[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM media_files WHERE id = ?", (media_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_media_file_by_path(path: str) -> Optional[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM media_files WHERE path = ?", (path,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_media_count(file_type: Optional[str] = None) -> int:
    conn = get_db()
    cursor = conn.cursor()
    if file_type:
        cursor.execute("SELECT COUNT(*) FROM media_files WHERE file_type = ?", (file_type,))
    else:
        cursor.execute("SELECT COUNT(*) FROM media_files")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def delete_media_file(path: str):
    conn = get_db()
    conn.execute("DELETE FROM media_files WHERE path = ?", (path,))
    conn.commit()
    conn.close()


def get_unique_folders(file_type: Optional[str] = None) -> List[str]:
    conn = get_db()
    cursor = conn.cursor()
    if file_type:
        cursor.execute("SELECT DISTINCT parent_folder FROM media_files WHERE file_type = ? ORDER BY parent_folder", (file_type,))
    else:
        cursor.execute("SELECT DISTINCT parent_folder FROM media_files ORDER BY parent_folder")
    folders = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    return folders


# --- Watch History ---

def update_watch_history(media_id: int, position: float, duration: float):
    """Update or create watch history entry."""
    conn = get_db()
    cursor = conn.cursor()
    progress = position / duration if duration > 0 else 0
    completed = 1 if progress > 0.9 else 0

    cursor.execute("""
        INSERT INTO watch_history (media_id, position, duration, progress, completed)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(media_id) DO UPDATE SET
            position = ?,
            duration = ?,
            progress = ?,
            completed = ?,
            last_watched = strftime('%s', 'now'),
            watch_count = watch_count + 1
    """, (media_id, position, duration, progress, completed,
          position, duration, progress, completed))

    conn.commit()
    conn.close()


def get_continue_watching(limit: int = 20) -> List[Dict]:
    """Get videos that are partially watched."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.*, h.position, h.duration as watch_duration, h.progress, h.last_watched
        FROM watch_history h
        JOIN media_files m ON h.media_id = m.id
        WHERE h.completed = 0 AND h.progress > 0.01 AND h.progress < 0.9
        ORDER BY h.last_watched DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_watch_history(limit: int = 50) -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.*, h.position, h.duration as watch_duration, h.progress, h.last_watched, h.watch_count
        FROM watch_history h
        JOIN media_files m ON h.media_id = m.id
        ORDER BY h.last_watched DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_watch_position(media_id: int) -> Optional[float]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT position FROM watch_history WHERE media_id = ?", (media_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# --- Favorites ---

def toggle_favorite(media_id: int) -> bool:
    """Toggle favorite status. Returns True if now favorited."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM favorites WHERE media_id = ?", (media_id,))
    if cursor.fetchone():
        cursor.execute("DELETE FROM favorites WHERE media_id = ?", (media_id,))
        result = False
    else:
        cursor.execute("INSERT INTO favorites (media_id) VALUES (?)", (media_id,))
        result = True
    conn.commit()
    conn.close()
    return result


def is_favorite(media_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM favorites WHERE media_id = ?", (media_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_favorites(limit: int = 50, offset: int = 0) -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.*, f.date_added as fav_date
        FROM favorites f
        JOIN media_files m ON f.media_id = m.id
        ORDER BY f.date_added DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# --- Pinned Folders ---

def pin_folder(path: str, name: str):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO pinned_folders (path, name) VALUES (?, ?)", (path, name))
    conn.commit()
    conn.close()


def unpin_folder(path: str):
    conn = get_db()
    conn.execute("DELETE FROM pinned_folders WHERE path = ?", (path,))
    conn.commit()
    conn.close()


def get_pinned_folders() -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pinned_folders ORDER BY date_added DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# --- Recently Added ---

def get_recently_added(limit: int = 20) -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM media_files
        ORDER BY date_added DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# --- Stats ---

def get_stats() -> Dict:
    conn = get_db()
    cursor = conn.cursor()

    stats = {}
    for ftype in ["video", "audio", "image", "document"]:
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM media_files WHERE file_type = ?", (ftype,))
        row = cursor.fetchone()
        stats[f"{ftype}_count"] = row[0]
        stats[f"{ftype}_size"] = row[1]

    cursor.execute("SELECT COUNT(*) FROM media_files")
    stats["total_count"] = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(size), 0) FROM media_files")
    stats["total_size"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM favorites")
    stats["favorites_count"] = cursor.fetchone()[0]

    conn.close()
    return stats
