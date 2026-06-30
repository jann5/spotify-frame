# Spotify Frame Backend

Thin LAN backend for the old Android photo frame. The preferred mode is a local `raspotify/librespot` event bridge on the Mac/Raspberry Pi, with Spotify Web API kept as fallback and for same-account playback controls.

## Endpoints

- `GET /api/now`
- `POST /api/control`
- `GET /cover.jpg`
- `GET /health`

All JSON responses include the header `X-Spotify-Frame-Schema: 1`.

## JSON contract

Success:

```json
{
  "ok": true,
  "source": "raspotify",
  "title": "Song title",
  "artist": "Artist",
  "album": "Album",
  "playing": true,
  "progress_ms": 12345,
  "duration_ms": 200000,
  "cover_url": "http://192.168.1.50:8000/cover.jpg",
  "updated_at": 1234567890,
  "can_control": true
}
```

Nothing playing:

```json
{
  "ok": true,
  "source": "raspotify",
  "title": "Nothing playing",
  "artist": "",
  "album": "",
  "playing": false,
  "progress_ms": 0,
  "duration_ms": 0,
  "cover_url": null,
  "updated_at": 1234567890,
  "can_control": false,
  "control_unavailable_reason": "Touch control works only for the authorized Spotify account."
}
```

Backend error:

```json
{
  "ok": false,
  "error": "short readable error",
  "updated_at": 1234567890
}
```

## Setup

Create a virtualenv:

```sh
cd /Users/jannawrot/Documents/Codex/2026-06-26/we-are-hacking-an-old-android
python3 -m venv work/.venv-backend
source work/.venv-backend/bin/activate
pip install -r backend/requirements.txt
```

Create the backend env file:

```sh
cp backend/.env.example backend/.env
```

Fill these variables in `backend/.env`:

- `SPOTIPY_CLIENT_ID`
- `SPOTIPY_CLIENT_SECRET`
- `SPOTIPY_REDIRECT_URI`

Optional backend settings:

- `BACKEND_HOST`
- `BACKEND_PORT`
- `PUBLIC_BASE_URL`
- `LOG_LEVEL`
- `LIBRESPOT_STATE_PATH`
- `LIBRESPOT_STATE_TTL_SECONDS`

Defaults for local `raspotify` mode:

- `LIBRESPOT_STATE_PATH=/run/spotify-frame/librespot-state.json`
- `LIBRESPOT_STATE_TTL_SECONDS=15`

## Preferred mode on Raspberry Pi

Use the local `librespot` event bridge so the frame follows whatever Spotify account is currently connected to `raspotify`.

1. Copy the backend to the Pi and install requirements as before.
2. Copy the event bridge script:

```sh
scp backend/scripts/librespot_event_bridge.py janek@yamaha-pi.local:/home/janek/spotify-frame-backend/scripts/librespot_event_bridge.py
ssh janek@yamaha-pi.local chmod +x /home/janek/spotify-frame-backend/scripts/librespot_event_bridge.py
```

3. Add the librespot hook in `/etc/raspotify/conf`:

```sh
sudoedit /etc/raspotify/conf
```

Append:

```sh
LIBRESPOT_ONEVENT=/home/janek/spotify-frame-backend/scripts/librespot_event_bridge.py
LIBRESPOT_EMIT_SINK_EVENTS=
```

4. Restart both services:

```sh
sudo systemctl restart raspotify
sudo systemctl restart spotify-frame-backend
```

5. Verify:

```sh
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/now
```

## Spotify Web API authorization

The backend still uses Spotipy for fallback reads and same-account touch controls. Do the one-time authorization first:

```sh
source work/.venv-backend/bin/activate
python backend/authorize.py
```

That command prints a Spotify login URL. After approving access, paste the full redirected URL back into the terminal. The token cache is stored under `backend/data/.spotify-token.json`.

Required Spotify scopes:

- `user-read-currently-playing`
- `user-read-playback-state`

## Playback control authorization

Touch controls use a separate token cache so adding control support does not break the already-working display token. These controls only work when the active `raspotify` session belongs to that same authorized Spotify account.

```sh
source work/.venv-backend/bin/activate
python backend/authorize.py --mode control
```

That stores the control token under `backend/data/.spotify-control-token.json`.

Required control scope:

- `user-modify-playback-state`

## Run the backend

```sh
source work/.venv-backend/bin/activate
python backend/run.py
```

Default bind:

- host: `0.0.0.0`
- port: `8000`

## Verify from Mac

```sh
curl http://192.168.1.50:8000/health
curl http://192.168.1.50:8000/api/now
```

## Verify from the frame

```sh
adb shell ping -c 3 192.168.1.50
```

## Android build/install/launch

```sh
./gradlew -PspotifyFrameBackendUrl=http://192.168.1.50:8000 assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.janek.spotifyframe/.MainActivity
```

If you do not pass `-PspotifyFrameBackendUrl=...`, the app falls back to `http://192.168.1.50:8000`.

## Notes

- The Android app never stores Spotify credentials.
- The backend caches the current cover on disk and only refreshes it when the track or cover URL changes.
- `/cover.jpg` serves the cached local image.
- Nothing in this setup touches `/system` on the frame.
