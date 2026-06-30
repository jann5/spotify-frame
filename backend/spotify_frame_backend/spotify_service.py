import logging
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import spotipy
from spotipy import CacheFileHandler, Spotify
from spotipy.oauth2 import SpotifyOAuth

from spotify_frame_backend.config import Settings
from spotify_frame_backend.cover_cache import CoverCache
from spotify_frame_backend.librespot_state import LibrespotStateReader, LibrespotSnapshot


class SpotifyBackendError(Exception):
    pass


class SpotifyService:
    def __init__(self, settings: Settings, cover_cache: CoverCache):
        self.settings = settings
        self.cover_cache = cover_cache
        self.logger = logging.getLogger("spotify_frame.spotify")
        self._read_auth_manager = None
        self._control_auth_manager = None
        self._read_spotify_client = None
        self._control_spotify_client = None
        self._control_user_id = None
        self._control_user_id_checked = False
        self.librespot_state = LibrespotStateReader(
            settings.librespot_state_path,
            settings.librespot_state_ttl_seconds,
        )

    def get_authorize_url(self, mode: str = "read") -> str:
        return self._get_auth_manager(mode).get_authorize_url()

    def complete_authorization(self, response_url: str, mode: str = "read") -> dict:
        auth_manager = self._get_auth_manager(mode)
        code = auth_manager.parse_response_code(response_url)
        if not code:
            raise SpotifyBackendError("Could not extract authorization code from redirect URL.")
        return auth_manager.get_access_token(code, check_cache=False)

    def health_payload(self) -> Dict[str, object]:
        local_snapshot = self.librespot_state.read_snapshot()
        return {
            "ok": True,
            "service": "spotify-frame-backend",
            "spotify_configured": self.is_configured(),
            "token_cached": self.settings.token_cache_path.exists(),
            "control_token_cached": self.settings.control_token_cache_path.exists(),
            "librespot_state_path": str(self.settings.librespot_state_path),
            "librespot_state_available": local_snapshot is not None,
            "librespot_state_updated_at": local_snapshot.updated_at if local_snapshot else 0,
            "updated_at": int(time.time()),
        }

    def fetch_now_playing(self, base_url: str) -> Dict[str, object]:
        local_payload = self._fetch_librespot_now_playing(base_url)
        if local_payload is not None:
            return local_payload

        return self._fetch_spotify_now_playing(base_url)

    def _fetch_librespot_now_playing(self, base_url: str) -> Optional[Dict[str, object]]:
        snapshot = self.librespot_state.read_snapshot()
        if snapshot is None:
            return None

        cover_url = self._cache_cover(snapshot, base_url)
        can_control, control_reason = self._get_control_capability(snapshot)

        if not snapshot.title:
            payload = {
                "ok": True,
                "source": "raspotify",
                "title": "Nothing playing",
                "artist": "",
                "album": "",
                "playing": False,
                "progress_ms": 0,
                "duration_ms": 0,
                "cover_url": None,
                "updated_at": snapshot.updated_at,
                "can_control": can_control,
            }
        else:
            payload = {
                "ok": True,
                "source": "raspotify",
                "title": snapshot.title,
                "artist": snapshot.artist,
                "album": snapshot.album,
                "playing": snapshot.playing,
                "progress_ms": snapshot.progress_ms,
                "duration_ms": snapshot.duration_ms,
                "cover_url": cover_url,
                "updated_at": snapshot.updated_at,
                "can_control": can_control,
            }

        if control_reason:
            payload["control_unavailable_reason"] = control_reason

        return payload

    def _fetch_spotify_now_playing(self, base_url: str) -> Dict[str, object]:
        updated_at = int(time.time())

        try:
            spotify = self._get_read_client()
            current = spotify.current_user_playing_track()
        except Exception as exc:
            error_message = self._format_error(exc)
            self.logger.warning("Spotify fetch failed: %s", error_message)
            return {
                "ok": False,
                "error": error_message,
                "updated_at": updated_at,
                "can_control": self.settings.control_token_cache_path.exists(),
            }

        if not current or not current.get("item"):
            return {
                "ok": True,
                "source": "spotify",
                "title": "Nothing playing",
                "artist": "",
                "album": "",
                "playing": False,
                "progress_ms": 0,
                "duration_ms": 0,
                "cover_url": None,
                "updated_at": updated_at,
                "can_control": self.settings.control_token_cache_path.exists(),
            }

        item = current.get("item") or {}
        album = item.get("album") or {}
        images = album.get("images") or []
        image_url = images[0]["url"] if images else None
        track_id = item.get("id") or item.get("uri") or item.get("name") or str(updated_at)
        cover_cache_key = track_id + ":" + (image_url or "no-cover")
        cover_url = None

        if image_url:
            try:
                self.cover_cache.ensure_cover(image_url, cover_cache_key)
                cover_url = self.cover_cache.get_public_cover_url(base_url)
            except Exception as exc:
                self.logger.warning("Cover refresh failed: %s", exc)

        artists = item.get("artists") or []
        artist_name = ", ".join(
            [artist.get("name", "") for artist in artists if artist.get("name")]
        )

        return {
            "ok": True,
            "source": "spotify",
            "title": item.get("name", "Unknown title"),
            "artist": artist_name,
            "album": album.get("name", ""),
            "playing": bool(current.get("is_playing")),
            "progress_ms": int(current.get("progress_ms") or 0),
            "duration_ms": int(item.get("duration_ms") or 0),
            "cover_url": cover_url,
            "updated_at": updated_at,
            "can_control": self.settings.control_token_cache_path.exists(),
        }

    def execute_control(self, action: str) -> Dict[str, object]:
        updated_at = int(time.time())
        normalized_action = (action or "").strip().lower()

        try:
            spotify = self._get_control_client()

            if normalized_action == "play":
                spotify.start_playback()
            elif normalized_action == "pause":
                spotify.pause_playback()
            elif normalized_action == "next":
                spotify.next_track()
            elif normalized_action == "previous":
                spotify.previous_track()
            else:
                raise SpotifyBackendError("Unknown control action.")
        except Exception as exc:
            error_message = self._format_error(exc)
            self.logger.warning("Spotify control failed (%s): %s", normalized_action, error_message)
            return {
                "ok": False,
                "error": error_message,
                "updated_at": updated_at,
            }

        self.logger.info("Spotify control executed: %s", normalized_action)
        return {
            "ok": True,
            "action": normalized_action,
            "updated_at": updated_at,
        }

    def is_configured(self) -> bool:
        return bool(
            self.settings.spotify_client_id
            and self.settings.spotify_client_secret
            and self.settings.spotify_redirect_uri
        )

    def _cache_cover(self, snapshot: LibrespotSnapshot, base_url: str) -> Optional[str]:
        if not snapshot.cover_source_url:
            return None

        track_key = snapshot.track_id or snapshot.title or str(snapshot.updated_at)
        cover_cache_key = track_key + ":" + snapshot.cover_source_url

        try:
            self.cover_cache.ensure_cover(snapshot.cover_source_url, cover_cache_key)
            return self.cover_cache.get_public_cover_url(base_url)
        except Exception as exc:
            self.logger.warning("Cover refresh failed: %s", exc)
            return None

    def _get_control_capability(
        self, snapshot: LibrespotSnapshot
    ) -> Tuple[bool, Optional[str]]:
        if not self.is_configured():
            return False, "Playback control backend is not configured."

        if not self.settings.control_token_cache_path.exists():
            return False, "Authorize playback on backend."

        active_user_name = (snapshot.user_name or "").strip().lower()
        control_user_name = self._get_control_user_id()
        if active_user_name and control_user_name and active_user_name != control_user_name:
            return False, "Touch control works only for the authorized Spotify account."

        return True, None

    def _get_control_user_id(self) -> str:
        if self._control_user_id_checked:
            return self._control_user_id or ""

        self._control_user_id_checked = True
        try:
            spotify = self._get_control_client()
            profile = spotify.current_user() or {}
            self._control_user_id = (profile.get("id") or "").strip().lower()
        except Exception as exc:
            self.logger.warning("Failed to resolve control account: %s", self._format_error(exc))
            self._control_user_id = ""

        return self._control_user_id or ""

    def _get_read_client(self) -> Spotify:
        if not self.is_configured():
            raise SpotifyBackendError(
                "Spotify credentials missing. Fill backend/.env first."
            )

        auth_manager = self._get_auth_manager("read")
        token_info = auth_manager.validate_token(auth_manager.cache_handler.get_cached_token())
        if not token_info:
            raise SpotifyBackendError(
                "Spotify authorization missing. Run python backend/authorize.py first."
            )

        if self._read_spotify_client is None:
            self._read_spotify_client = spotipy.Spotify(
                auth_manager=auth_manager,
                requests_timeout=10,
                retries=2,
            )

        return self._read_spotify_client

    def _get_control_client(self) -> Spotify:
        if not self.is_configured():
            raise SpotifyBackendError(
                "Spotify credentials missing. Fill backend/.env first."
            )

        auth_manager = self._get_auth_manager("control")
        token_info = auth_manager.validate_token(auth_manager.cache_handler.get_cached_token())
        if not token_info:
            raise SpotifyBackendError(
                "Playback control not authorized on backend."
            )

        if self._control_spotify_client is None:
            self._control_spotify_client = spotipy.Spotify(
                auth_manager=auth_manager,
                requests_timeout=10,
                retries=2,
            )

        return self._control_spotify_client

    def _get_auth_manager(self, mode: str) -> SpotifyOAuth:
        if mode == "control":
            if self._control_auth_manager is None:
                self._control_auth_manager = self._build_auth_manager(
                    self.settings.spotify_control_scope,
                    self.settings.control_token_cache_path,
                )
            return self._control_auth_manager

        if self._read_auth_manager is None:
            self._read_auth_manager = self._build_auth_manager(
                self.settings.spotify_read_scope,
                self.settings.token_cache_path,
            )
        return self._read_auth_manager

    def _build_auth_manager(self, scope: str, cache_path) -> SpotifyOAuth:
        cache_handler = CacheFileHandler(cache_path=str(cache_path))
        return SpotifyOAuth(
            client_id=self.settings.spotify_client_id,
            client_secret=self.settings.spotify_client_secret,
            redirect_uri=self.settings.spotify_redirect_uri,
            scope=scope,
            cache_handler=cache_handler,
            open_browser=False,
        )

    def _format_error(self, exc: Exception) -> str:
        if isinstance(exc, SpotifyBackendError):
            return str(exc)

        message = str(exc).strip()
        if not message:
            return exc.__class__.__name__

        parsed = urlparse(message)
        if parsed.scheme and parsed.netloc:
            return exc.__class__.__name__

        return message
