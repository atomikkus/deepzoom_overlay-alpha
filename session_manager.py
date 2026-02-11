"""
Session Manager for WSI Viewer
Manages multiple viewer sessions with UUID tokens, each with its own
slides directory, overlay directory, and converter instance.
"""

import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict
from converter import WSIConverter


ALLOWED_EXTENSIONS = {
    'svs', 'tif', 'tiff', 'vms', 'vmu', 'ndpi',
    'scn', 'mrxs', 'svslide', 'bif'
}


@dataclass
class Session:
    """A viewer session with its own slide/overlay configuration."""
    token: str
    slides_dir: str
    overlay_dir: Optional[str]
    single_slide: Optional[str]
    converter: WSIConverter
    cache_dir: str
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def touch(self):
        self.last_accessed = datetime.utcnow()

    def find_overlay_file(self, slide_name: str, suffix: str) -> Optional[str]:
        """Find overlay file: check overlay dir first, then slides dir."""
        target = f"{slide_name}{suffix}"
        if self.overlay_dir:
            path = Path(self.overlay_dir) / target
            if path.exists():
                return str(path)
        path = Path(self.slides_dir) / target
        if path.exists():
            return str(path)
        return None


class SessionManager:
    """Manages multiple viewer sessions with TTL-based expiration."""

    def __init__(self, default_cache_dir: str = "cache", ttl_minutes: int = 30):
        self.sessions: Dict[str, Session] = {}
        self.default_cache_dir = default_cache_dir
        self.ttl_minutes = ttl_minutes
        self._cleanup_task: Optional[asyncio.Task] = None

    def create_session(self, slides_path: str, overlay_dir: Optional[str] = None) -> Session:
        token = str(uuid.uuid4())

        # Support both directory and single-file paths
        single_slide = None
        if Path(slides_path).is_file():
            resolved = Path(slides_path).resolve()
            slides_dir = str(resolved.parent)
            single_slide = resolved.name
        else:
            slides_dir = str(Path(slides_path).resolve())

        # Validate overlay dir
        resolved_overlay = None
        if overlay_dir:
            p = Path(overlay_dir)
            if p.is_dir():
                resolved_overlay = str(p.resolve())

        converter = WSIConverter(upload_dir=slides_dir, cache_dir=self.default_cache_dir)

        session = Session(
            token=token,
            slides_dir=slides_dir,
            overlay_dir=resolved_overlay,
            single_slide=single_slide,
            converter=converter,
            cache_dir=self.default_cache_dir,
        )
        self.sessions[token] = session

        mode = f"single-slide ({single_slide})" if single_slide else "directory"
        print(f"✓ Session created: {token} [{mode}] slides={slides_dir}")
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
