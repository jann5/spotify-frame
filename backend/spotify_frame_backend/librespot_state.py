import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LibrespotSnapshot:
    updated_at: int
    title: str
    artist: str
    album: str
    playing: bool
    progress_ms: int
    duration_ms: int
    cover_source_url: Optional[str]
    track_id: str
    user_name: str
    connected: bool


class LibrespotStateReader:
    def __init__(self, state_path: Path, max_age_seconds: int):
        self.state_path = state_path
        self.max_age_seconds = max_age_seconds
        self.logger = logging.getLogger("spotify_frame.librespot_state")

    def read_snapshot(self) -> Optional[LibrespotSnapshot]:
        if not self.state_path.exists():
            return None

        try:
            payload = json.loads(self.state_path.read_text())
        except Exception as exc:
            self.logger.warning("Failed to read librespot state: %s", exc)
            return None

        updated_at = self._parse_int(payload.get("updated_at"))
        if updated_at <= 0:
            return None

        age_seconds = int(time.time()) - updated_at
        if self.max_age_seconds > 0 and age_seconds > self.max_age_seconds:
            return None

        artist = self._safe_string(payload.get("artist"))
        if not artist:
            artists = payload.get("artists") or []
            if isinstance(artists, list):
                artist = ", ".join(
                    [self._safe_string(item) for item in artists if self._safe_string(item)]
                )

        cover_source_url = self._safe_string(payload.get("cover_source_url")) or None

        return LibrespotSnapshot(
            updated_at=updated_at,
            title=self._safe_string(payload.get("title")),
            artist=artist,
            album=self._safe_string(payload.get("album")),
            playing=bool(payload.get("playing", False)),
            progress_ms=max(0, self._parse_int(payload.get("progress_ms"))),
            duration_ms=max(0, self._parse_int(payload.get("duration_ms"))),
            cover_source_url=cover_source_url,
            track_id=self._safe_string(payload.get("track_id")),
            user_name=self._safe_string(payload.get("user_name")),
            connected=bool(payload.get("connected", False)),
        )

    def _parse_int(self, value) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    def _safe_string(self, value) -> str:
        if value is None:
            return ""
        return str(value).strip()
