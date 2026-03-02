"""
Session Manager for WSI Viewer
Manages multiple viewer sessions with UUID tokens, each with its own
slides directory and overlay directory.
"""

import uuid
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any


ALLOWED_EXTENSIONS = {
    'svs', 'tif', 'tiff', 'vms', 'vmu', 'ndpi',
    'scn', 'mrxs', 'svslide', 'bif'
}


def is_gcs_path(path: str) -> bool:
    """Return True if a path points to GCS-style location."""
    p = (path or "").strip().lower()
    return (
        p.startswith("gs://")
        or p.startswith("gcs://")
        or p.startswith("https://storage.googleapis.com/")
        or p.startswith("https://storage.cloud.google.com/")
    )


def is_url(path: str) -> bool:
    """Return True if the path is any http/https URL."""
    p = (path or "").strip().lower()
    return p.startswith("http://") or p.startswith("https://")


def is_zip_path(path: str) -> bool:
    """Return True if the path/URL points to a zip archive."""
    return (path or "").strip().lower().endswith(".zip")


def is_direct_slide_url(path: str) -> bool:
    """True if path is http(s) and the URL path (no query) ends with an allowed slide extension."""
    if not is_url(path):
        return False
    path_part = (path or "").split("?")[0].rstrip("/")
    if not path_part:
        return False
    ext = path_part.rsplit(".", 1)[-1].lower() if "." in path_part else ""
    return ext in ALLOWED_EXTENSIONS


def url_to_slide_filename(url: str) -> str:
    """From URL path (no query), return the filename (segment after last /)."""
    path_part = (url or "").split("?")[0].rstrip("/")
    return path_part.split("/")[-1] if path_part else ""


@dataclass
class Session:
    """A viewer session with its own slide/overlay/thumbnail configuration."""
    token: str
    slide_paths: List[str]  # List of slide paths (GCS URLs or local paths)
    overlay_paths: List[str]  # Raw overlay paths (dirs, local zips, or zip URLs)
    thumbnail_paths: List[str]  # Raw thumbnail sources (local dir, local zip, zip URL, or GCS prefix)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    # Populated after zip download+extraction; used by find_overlay_file
    overlay_extracted_dir: Optional[str] = field(default=None)
    # Per-slide overlay dirs (slide_name -> path). When set, overlays are resolved from api_slides
    # so each slide's tca_url zip is extracted to its own dir and never mixed with others.
    overlay_extracted_by_slide: Optional[Dict[str, str]] = field(default=None)
    thumbnail_extracted_dir: Optional[str] = field(default=None)
    metadata: Optional[Dict] = field(default=None)  # Optional: width, height, mpp, objective_power, vendor, thumbnail_url
    # When set, slides/thumbnails come from external API (create_session_pid)
    api_slides: Optional[List[Dict[str, Any]]] = field(default=None)  # List of {slide_id, slide_url, thumbnail_url, tca_url, meta_data, ...}
    default_slide_id: Optional[str] = field(default=None)  # Requested slide_id to open by default (first in list)

    def touch(self):
        self.last_accessed = datetime.utcnow()

    def find_overlay_file(self, slide_name: str, suffix: str) -> Optional[str]:
        """Find overlay file: check extracted zip dir first, then plain directories.
        Tries both {slide_name}{suffix} (e.g. 1087-25_density.png) and
        slide{suffix} (e.g. slide_density.png) for each location."""
        candidates = [f"{slide_name}{suffix}", f"slide{suffix}", suffix.lstrip("_")]

        def _first_existing(directory: Path) -> Optional[str]:
            for name in candidates:
                p = directory / name
                if p.exists():
                    return str(p)
            return None

        # 1a. Per-slide overlay dirs (api_slides): each slide's zip in its own dir — no cross-talk
        if self.overlay_extracted_by_slide and slide_name in self.overlay_extracted_by_slide:
            root = Path(self.overlay_extracted_by_slide[slide_name])
            if root.exists():
                hit = _first_existing(root)
                if hit:
                    return hit
                for subdir in root.iterdir():
                    if subdir.is_dir():
                        hit = _first_existing(subdir)
                        if hit:
                            return hit

        # 1b. Single extracted overlay dir (flat list of overlay_paths)
        if self.overlay_extracted_dir and not self.overlay_extracted_by_slide:
            root = Path(self.overlay_extracted_dir)
            hit = _first_existing(root)
            if hit:
                return hit
            for subdir in root.iterdir():
                if subdir.is_dir():
                    hit = _first_existing(subdir)
                    if hit:
                        return hit

        # 2. Search static overlay directories (skip URLs / zip paths)
        for overlay_path in self.overlay_paths:
            if is_gcs_path(overlay_path) or is_url(overlay_path) or is_zip_path(overlay_path):
                continue  # These are resolved via overlay_extracted_dir
            hit = _first_existing(Path(overlay_path))
            if hit:
                return hit

        # 3. Fall back to slide directories
        for slide_path in self.slide_paths:
            if not is_gcs_path(slide_path):
                p = Path(slide_path)
                directory = p if p.is_dir() else p.parent
                hit = _first_existing(directory)
                if hit:
                    return hit

        return None

    def _find_in_thumbnail_sources(self, slide_name: str, suffix: str) -> Optional[str]:
        """Look for a file in thumbnail_extracted_dir and local thumbnail_paths only."""
        target = f"{slide_name}{suffix}"
        if self.thumbnail_extracted_dir:
            root = Path(self.thumbnail_extracted_dir)
            path = root / target
            if path.exists():
                return str(path)
            for subdir in root.iterdir():
                if subdir.is_dir():
                    path = subdir / target
                    if path.exists():
                        return str(path)
        for tp in self.thumbnail_paths:
            if is_gcs_path(tp) or is_url(tp) or is_zip_path(tp):
                continue
            path = Path(tp) / target
            if path.exists():
                return str(path)
        return None

    def find_thumbnail(self, slide_name: str) -> Optional[str]:
        """Find thumbnail image. Overlay/slide dirs first, then thumbnail_paths (dirs + extracted zip). Names: _thumbnail.png, _thumb.png, _tb.png."""
        # 1. Overlay and slide dirs (existing behavior)
        for suffix in ('_thumbnail.png', '_thumb.png', '_tb.png'):
            p = self.find_overlay_file(slide_name, suffix)
            if p:
                return p
        # 2. Dedicated thumbnail sources (dirs + thumbnail_extracted_dir)
        for suffix in ('_thumbnail.png', '_thumb.png', '_tb.png'):
            p = self._find_in_thumbnail_sources(slide_name, suffix)
            if p:
                return p
        return None

    def cleanup_extracted(self):
        """Remove temp directories created during zip extraction."""
        if self.overlay_extracted_dir and Path(self.overlay_extracted_dir).exists():
            shutil.rmtree(self.overlay_extracted_dir, ignore_errors=True)
            self.overlay_extracted_dir = None
        self.overlay_extracted_by_slide = None
        if self.thumbnail_extracted_dir and Path(self.thumbnail_extracted_dir).exists():
            shutil.rmtree(self.thumbnail_extracted_dir, ignore_errors=True)
            self.thumbnail_extracted_dir = None


class SessionManager:
    """Manages multiple viewer sessions with TTL-based expiration."""

    def __init__(self, ttl_minutes: int = 30):
        self.sessions: Dict[str, Session] = {}
        self.ttl_minutes = ttl_minutes
        self._cleanup_task: Optional[asyncio.Task] = None

    def create_session(
        self,
        slide_paths: List[str],
        overlay_paths: List[str] = None,
        thumbnail_paths: List[str] = None,
        metadata: Optional[Dict] = None,
        api_slides: Optional[List[Dict[str, Any]]] = None,
        default_slide_id: Optional[str] = None,
        token: Optional[str] = None,
    ) -> Session:
        if token is None:
            token = str(uuid.uuid4())

        if overlay_paths is None:
            overlay_paths = []
        if thumbnail_paths is None:
            thumbnail_paths = []

        # Normalize all slide paths
        normalized_slide_paths = []
        for path in slide_paths:
            path = path.strip()
            if is_direct_slide_url(path):
                # Direct HTTP(S) URL to a single slide (public or signed); keep as-is
                normalized_slide_paths.append(path)
            elif is_gcs_path(path):
                # Keep GCS paths as-is
                normalized_slide_paths.append(path)
            else:
                # Resolve local paths
                p = Path(path)
                if p.exists():
                    normalized_slide_paths.append(str(p.resolve()))
                else:
                    print(f"Warning: Slide path does not exist: {path}")
        
        # Normalize overlay paths
        normalized_overlay_paths = []
        for path in overlay_paths:
            path = path.strip()
            if is_url(path):
                # http/https URL (e.g. signed URL to a .zip): keep as-is, resolved later
                normalized_overlay_paths.append(path)
            elif is_gcs_path(path):
                normalized_overlay_paths.append(path)
            else:
                p = Path(path)
                if p.is_dir():
                    normalized_overlay_paths.append(str(p.resolve()))
                elif p.is_file() and is_zip_path(path):
                    # Local zip archive: keep resolved absolute path
                    normalized_overlay_paths.append(str(p.resolve()))
                else:
                    print(f"Warning: Overlay path does not exist or is not a directory/zip: {path}")

        # Normalize thumbnail paths (same rules as overlay: dir, local zip, URL zip, GCS)
        normalized_thumbnail_paths = []
        for path in thumbnail_paths:
            path = path.strip()
            if is_url(path) or is_gcs_path(path):
                normalized_thumbnail_paths.append(path)
            else:
                p = Path(path)
                if p.is_dir():
                    normalized_thumbnail_paths.append(str(p.resolve()))
                elif p.is_file() and is_zip_path(path):
                    normalized_thumbnail_paths.append(str(p.resolve()))
                else:
                    print(f"Warning: Thumbnail path does not exist or is not a directory/zip: {path}")

        session = Session(
            token=token,
            slide_paths=normalized_slide_paths,
            overlay_paths=normalized_overlay_paths,
            thumbnail_paths=normalized_thumbnail_paths,
            metadata=metadata,
            api_slides=api_slides,
            default_slide_id=default_slide_id,
        )
        self.sessions[token] = session

        print(f"✓ Session created: {token}")
        print(f"  Slide paths ({len(normalized_slide_paths)}): {normalized_slide_paths}")
        print(f"  Overlay paths ({len(normalized_overlay_paths)}): {normalized_overlay_paths}")
        print(f"  Thumbnail paths ({len(normalized_thumbnail_paths)}): {normalized_thumbnail_paths}")
        return session

    def get_session(self, token: str) -> Optional[Session]:
        session = self.sessions.get(token)
        if session:
            session.touch()
        return session

    def delete_session(self, token: str) -> bool:
        if token in self.sessions:
            session = self.sessions.pop(token)
            session.cleanup_extracted()
            print(f"✗ Session deleted: {token}")
            return True
        return False

    def cleanup_expired(self):
        now = datetime.utcnow()
        expired = [
            t for t, s in self.sessions.items()
            if (now - s.last_accessed).total_seconds() > self.ttl_minutes * 60
        ]
        for t in expired:
            print(f"Session expired (idle {self.ttl_minutes}min): {t}")
            self.delete_session(t)
        return len(expired)

    async def start_cleanup_loop(self, interval_minutes: int = 5):
        async def _loop():
            while True:
                await asyncio.sleep(interval_minutes * 60)
                count = self.cleanup_expired()
                if count:
                    print(f"Cleanup: removed {count} expired session(s), {len(self.sessions)} active")
        self._cleanup_task = asyncio.create_task(_loop())

    def stop_cleanup_loop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
