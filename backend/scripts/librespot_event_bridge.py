#!/usr/bin/env python3
import json
import os
import tempfile
import time
from pathlib import Path


DEFAULT_STATE_PATH = Path("/run/spotify-frame/librespot-state.json")


def main() -> int:
    configured_state_path = safe_string(os.getenv("SPOTIFY_FRAME_STATE_PATH"))
    state_path = Path(configured_state_path).expanduser() if configured_state_path else DEFAULT_STATE_PATH

    state = load_state(state_path)
    apply_event(state, os.environ)
    write_state(state_path, state)
    return 0


def load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {
            "schema": 1,
            "source": "raspotify",
            "connected": False,
            "playing": False,
            "title": "",
            "artist": "",
            "artists": [],
            "album": "",
            "track_id": "",
            "uri": "",
            "progress_ms": 0,
            "duration_ms": 0,
            "cover_source_url": "",
            "cover_urls": [],
            "user_name": "",
        }

    try:
        return json.loads(state_path.read_text())
    except Exception:
        return {
            "schema": 1,
            "source": "raspotify",
        }


def apply_event(state: dict, environ: dict) -> None:
    event = safe_string(environ.get("PLAYER_EVENT")).lower()
    now = int(time.time())

    state["schema"] = 1
    state["source"] = "raspotify"
    state["last_event"] = event
    state["updated_at"] = now

    if event == "track_changed":
        covers = split_lines(environ.get("COVERS"))
        artists = split_lines(environ.get("ARTISTS"))
        state["track_id"] = safe_string(environ.get("TRACK_ID"))
        state["uri"] = safe_string(environ.get("URI"))
        state["title"] = safe_string(environ.get("NAME"))
        state["artists"] = artists
        state["artist"] = ", ".join(artists)
        state["album"] = safe_string(environ.get("ALBUM"))
        state["duration_ms"] = parse_int(environ.get("DURATION_MS"))
        state["progress_ms"] = 0
        state["cover_urls"] = covers
        state["cover_source_url"] = covers[0] if covers else ""
        state["connected"] = True
        return

    if event in ("playing", "paused", "seeked", "position_correction"):
        track_id = safe_string(environ.get("TRACK_ID"))
        if track_id:
            state["track_id"] = track_id
        state["progress_ms"] = parse_int(environ.get("POSITION_MS"), state.get("progress_ms", 0))
        if event == "playing":
            state["playing"] = True
            state["connected"] = True
        elif event == "paused":
            state["playing"] = False
            state["connected"] = True
        return

    if event in ("loading", "preloading", "preload_next"):
        track_id = safe_string(environ.get("TRACK_ID"))
        if track_id:
            state["track_id"] = track_id
        return

    if event in ("stopped", "end_of_track", "unavailable"):
        state["playing"] = False
        track_id = safe_string(environ.get("TRACK_ID"))
        if track_id:
            state["track_id"] = track_id
        return

    if event == "session_connected":
        state["connected"] = True
        state["user_name"] = safe_string(environ.get("USER_NAME"))
        state["connection_id"] = safe_string(environ.get("CONNECTION_ID"))
        return

    if event == "session_disconnected":
        state["connected"] = False
        state["playing"] = False
        state["user_name"] = safe_string(environ.get("USER_NAME"))
        state["connection_id"] = safe_string(environ.get("CONNECTION_ID"))
        clear_track(state)
        return

    if event == "session_client_changed":
        state["client_id"] = safe_string(environ.get("CLIENT_ID"))
        state["client_name"] = safe_string(environ.get("CLIENT_NAME"))
        state["client_brand_name"] = safe_string(environ.get("CLIENT_BRAND_NAME"))
        state["client_model_name"] = safe_string(environ.get("CLIENT_MODEL_NAME"))
        return

    if event == "sink":
        state["sink_status"] = safe_string(environ.get("SINK_STATUS"))


def clear_track(state: dict) -> None:
    state["title"] = ""
    state["artist"] = ""
    state["artists"] = []
    state["album"] = ""
    state["track_id"] = ""
    state["uri"] = ""
    state["progress_ms"] = 0
    state["duration_ms"] = 0
    state["cover_source_url"] = ""
    state["cover_urls"] = []


def write_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(state_path.parent, 0o755)
    except OSError:
        pass

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(state_path.parent),
        delete=False,
    ) as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_name = handle.name

    os.chmod(temp_name, 0o644)
    Path(temp_name).replace(state_path)


def split_lines(value) -> list:
    return [item.strip() for item in str(value or "").splitlines() if item.strip()]


def parse_int(value, fallback=0) -> int:
    try:
        return int(value)
    except Exception:
        return int(fallback)


def safe_string(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


if __name__ == "__main__":
    raise SystemExit(main())
