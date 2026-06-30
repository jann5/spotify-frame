from flask import Flask, jsonify, request, send_file

from spotify_frame_backend.config import load_settings
from spotify_frame_backend.cover_cache import CoverCache
from spotify_frame_backend.logging_utils import configure_logging
from spotify_frame_backend.spotify_service import SpotifyService


SCHEMA_VERSION = "1"


def create_app() -> Flask:
    settings = load_settings()
    configure_logging(settings.log_level)
    cover_cache = CoverCache(settings.cover_path, settings.cover_meta_path)
    spotify_service = SpotifyService(settings, cover_cache)

    app = Flask(__name__)
    app.config["SETTINGS"] = settings
    app.config["COVER_CACHE"] = cover_cache
    app.config["SPOTIFY_SERVICE"] = spotify_service

    @app.get("/api/now")
    def api_now():
        base_url = settings.public_base_url or request.host_url.rstrip("/")
        payload = spotify_service.fetch_now_playing(base_url)
        return _json_response(payload)

    @app.post("/api/control")
    def api_control():
        payload = request.get_json(silent=True) or {}
        action = payload.get("action", "")
        response_payload = spotify_service.execute_control(action)
        return _json_response(response_payload)

    @app.get("/cover.jpg")
    def cover():
        if not cover_cache.has_cover():
            return _json_response({"ok": False, "error": "cover not cached", "updated_at": 0}, 404)

        response = send_file(str(settings.cover_path), mimetype="image/jpeg")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return _json_response(spotify_service.health_payload())

    return app


def _json_response(payload, status_code=200):
    response = jsonify(payload)
    response.status_code = status_code
    response.headers["X-Spotify-Frame-Schema"] = SCHEMA_VERSION
    response.headers["Cache-Control"] = "no-store"
    return response
