"""
Session Manager for WSI Viewer
Manages multiple viewer sessions with UUID tokens, each with its own
slides directory and overlay directory.
"""

import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List


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


@dataclass
class Session:
    """A viewer session with its own slide/overlay configuration."""
    token: str
    slide_paths: List[str]  # List of slide paths (GCS URLs or local paths)
    overlay_paths: List[str]  # List of overlay directories
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def touch(self):
        self.last_accessed = datetime.utcnow()

    def find_overlay_file(self, slide_name: str, suffix: str) -> Optional[str]:
        """Find overlay file: search all overlay paths in order."""
        target = f"{slide_name}{suffix}"
        
        # Search all overlay directories
        for overlay_path in self.overlay_paths:
            if is_gcs_path(overlay_path):
                # GCS overlay not yet supported, skip for now
                continue
            else:
                # Check local path
                path = Path(overlay_path) / target
                if path.exists():
                    return str(path)
        
        # Also check in each slide directory
        for slide_path in self.slide_paths:
            if not is_gcs_path(slide_path):
                # For local paths, check if it's a directory or file
                p = Path(slide_path)
                if p.is_dir():
                    check_path = p / target
                else:
                    check_path = p.parent / target
                
                if check_path.exists():
                    return str(check_path)
        
        return None


class SessionManager:
    """Manages multiple viewer sessions with TTL-based expiration."""

    def __init__(self, ttl_minutes: int = 30):
        self.sessions: Dict[str, Session] = {}
        self.ttl_minutes = ttl_minutes
        self._cleanup_task: Optional[asyncio.Task] = None

    def create_session(self, slide_paths: List[str], overlay_paths: List[str] = None) -> Session:
        token = str(uuid.uuid4())

        # Normalize overlay paths
        if overlay_paths is None:
            overlay_paths = []

        # Normalize all slide paths
        normalized_slide_paths = []
        for path in slide_paths:
            path = path.strip()
            if is_gcs_path(path):
                # Keep GCS paths as-is
                normalized_slide_paths.append(path)
            else:
                # Resolve local paths
                p = Path(path)
                if p.exists():
                    normalized_slide_paths.append(str(p.resolve()))
                else:
                    print(f"Warning: Slide path does not exist: {path}")
        
        # Normalize overlay paths (local only for now)
        normalized_overlay_paths = []
        for path in overlay_paths:
            if is_gcs_path(path):
                # GCS overlays not yet supported, but keep for future
                normalized_overlay_paths.append(path)
            else:
                p = Path(path)
                if p.is_dir():
                    normalized_overlay_paths.append(str(p.resolve()))
                else:
                    print(f"Warning: Overlay path does not exist or is not a directory: {path}")

        session = Session(
            token=token,
            slide_paths=normalized_slide_paths,
            overlay_paths=normalized_overlay_paths,
        )
        self.sessions[token] = session

        print(f"✓ Session created: {token}")
        print(f"  Slide paths ({len(normalized_slide_paths)}): {normalized_slide_paths}")
        print(f"  Overlay paths ({len(normalized_overlay_paths)}): {normalized_overlay_paths}")
        return session

    def get_session(self, token: str) -> Optional[Session]:
        session = self.sessions.get(token)
        if session:
            session.touch()
        return session

    def delete_session(self, token: str) -> bool:
        if token in self.sessions:
            del self.sessions[token]
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
            print(f"⏰ Session expired (idle {self.ttl_minutes}min): {t}")
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
