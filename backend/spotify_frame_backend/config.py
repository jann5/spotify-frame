import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BACKEND_ROOT / "data"

load_dotenv(BACKEND_ROOT / ".env")


@dataclass
class Settings:
    host: str
    port: int
    public_base_url: Optional[str]
    log_level: str
    librespot_state_path: Path
    librespot_state_ttl_seconds: int
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    spotify_read_scope: str
    spotify_control_scope: str
    token_cache_path: Path
    control_token_cache_path: Path
    cover_path: Path
    cover_meta_path: Path


def load_settings() -> Settings:
    data_dir = DEFAULT_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip() or None

    return Settings(
        host=os.getenv("BACKEND_HOST", "0.0.0.0"),
        port=int(os.getenv("BACKEND_PORT", "8000")),
        public_base_url=public_base_url,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        librespot_state_path=Path(
            os.getenv("LIBRESPOT_STATE_PATH", "/run/spotify-frame/librespot-state.json")
        ),
        librespot_state_ttl_seconds=int(os.getenv("LIBRESPOT_STATE_TTL_SECONDS", "15")),
        spotify_client_id=os.getenv("SPOTIPY_CLIENT_ID", "").strip(),
        spotify_client_secret=os.getenv("SPOTIPY_CLIENT_SECRET", "").strip(),
        spotify_redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI", "").strip(),
        spotify_read_scope="user-read-currently-playing user-read-playback-state",
        spotify_control_scope="user-modify-playback-state",
        token_cache_path=data_dir / ".spotify-token.json",
        control_token_cache_path=data_dir / ".spotify-control-token.json",
        cover_path=data_dir / "cover.jpg",
        cover_meta_path=data_dir / "cover-meta.json",
    )
