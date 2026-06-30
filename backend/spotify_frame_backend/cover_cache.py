import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests


class CoverCache:
    def __init__(self, cover_path: Path, metadata_path: Path):
        self.cover_path = cover_path
        self.metadata_path = metadata_path
        self.logger = logging.getLogger("spotify_frame.cover_cache")
        self.cover_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._metadata = self._load_metadata()

    def has_cover(self) -> bool:
        return self.cover_path.exists()

    def ensure_cover(self, image_url: str, cache_key: str) -> bool:
        if not image_url:
            return False

        if self.cover_path.exists() and self._metadata.get("cache_key") == cache_key:
            return True

        self.logger.info("Refreshing cached cover for %s", cache_key)
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()

        temp_path = self.cover_path.with_suffix(".tmp")
        temp_path.write_bytes(response.content)
        temp_path.replace(self.cover_path)

        self._metadata = {
            "cache_key": cache_key,
            "image_url": image_url,
            "updated_at": int(time.time()),
        }
        self._save_metadata()
        return True

    def get_public_cover_url(self, base_url: str) -> Optional[str]:
        if not self.has_cover():
            return None
        cover_url = base_url.rstrip("/") + "/cover.jpg"
        version = self._metadata.get("updated_at")
        if version:
            return cover_url + "?v=" + str(version)
        return cover_url

    def _load_metadata(self) -> dict:
        if not self.metadata_path.exists():
            return {}

        try:
            return json.loads(self.metadata_path.read_text())
        except Exception as exc:
            self.logger.warning("Failed to read cover metadata: %s", exc)
            return {}

    def _save_metadata(self) -> None:
        self.metadata_path.write_text(json.dumps(self._metadata, indent=2))
