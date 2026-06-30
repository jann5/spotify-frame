import argparse

from spotify_frame_backend.config import load_settings
from spotify_frame_backend.logging_utils import configure_logging
from spotify_frame_backend.spotify_service import SpotifyService
from spotify_frame_backend.cover_cache import CoverCache


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["read", "control"],
        default="read",
        help="Authorize read access for display polling or control access for playback buttons.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    settings = load_settings()
    configure_logging(settings.log_level)
    cover_cache = CoverCache(settings.cover_path, settings.cover_meta_path)
    service = SpotifyService(settings, cover_cache)

    print("Spotify Frame authorization (" + args.mode + ")")
    print("")
    print("1. Open this URL in a browser and approve access:")
    print(service.get_authorize_url(args.mode))
    print("")
    print("2. After Spotify redirects to your redirect URI, copy the FULL redirect URL.")
    print("3. Paste it below and press Enter.")
    print("")

    response_url = input("Redirect URL: ").strip()
    token_info = service.complete_authorization(response_url, args.mode)
    print("")
    print("Authorization saved.")
    print("Access token expires at:", token_info.get("expires_at"))


if __name__ == "__main__":
    main()
