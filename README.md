# Spotify Frame

Turn an old Android 4.2.2 digital photo frame into a dedicated Spotify Now Playing display.

This project started on a forgotten 1024x600 Wi-Fi frame with a prehistoric Android build, a working ADB shell, and a very specific goal: keep the device dumb, fast, and stable. The Android app is only a thin LAN client. All Spotify auth, album art fetching, and playback state logic live on a local backend running on a Mac or Raspberry Pi.

![Spotify Frame UI](docs/images/spotify-frame-ui.png)

## What It Does

- Runs on Android 4.2.2 with `minSdkVersion 17`
- Uses a single Java `Activity` and plain Android SDK classes
- Polls a local backend for now-playing metadata
- Shows title, artist, album, playback state, progress, and cover art
- Keeps the screen awake in a fullscreen kiosk-style layout
- Works best with a Raspberry Pi running `raspotify/librespot`
- Keeps Spotify secrets off the frame

## Architecture

```text
Spotify app / Spotify Connect
            |
            v
   Raspotify / Librespot on Pi
            |
            +--> event bridge -> local state JSON
            |
            +--> Flask backend
                    |- /api/now
                    |- /api/control
                    |- /cover.jpg
                    '- /health
            |
            v
  Android 4.2.2 frame app (thin client)
```

## Why This Exists

Most smart display projects target new tablets, webviews, or full Spotify SDK integrations. This one deliberately does not.

The frame stays a render-only client:

- no Spotify credentials on Android
- no WebView
- no AndroidX
- no Kotlin
- no `/system` changes required for the normal app build

That made it possible to repurpose a strange old OEM frame into something that still boots instantly and can be read from across the room.

## Project Layout

```text
app/       Android client
backend/   Flask + Spotipy + librespot event bridge
gradle/    Gradle wrapper files
```

## Quick Start

### 1. Start the backend

```sh
python3 -m venv work/.venv-backend
source work/.venv-backend/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
python backend/authorize.py
python backend/run.py
```

For Raspberry Pi + `raspotify`, use the event bridge documented in [backend/README.md](backend/README.md).

### 2. Build the Android APK

```sh
./gradlew -PspotifyFrameBackendUrl=http://192.168.1.50:8000 assembleDebug
```

### 3. Install and launch

```sh
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.janek.spotifyframe/.MainActivity
```

## Stack

- Android SDK 17
- Java
- Flask
- Spotipy
- `raspotify` / `librespot`
- `HttpURLConnection`
- `org.json.JSONObject`

## Current State

What is already solid:

- backend-driven now-playing display
- Android 4.2.2 compatibility
- local cover caching
- progress rendering
- touch controls for same-account playback control
- Pi-local `librespot` event ingestion

What can still be improved:

- smarter album-art fallbacks
- more polished onboarding for first-time backend auth
- optional autostart / launcher replacement tooling
- extra screenshots and real device photos

## Notes

- The repository intentionally does not include local `.env` files, Spotify tokens, APK outputs, or extracted factory system files.
- The screenshot above is a safe UI capture; real frame photos can be added later.
- If playback is controlled from a different Spotify account than the one authorized for backend control, the display still works, but touch controls may be limited by Spotify Connect / `librespot`.

## Backend Details

More technical backend setup, API details, and Raspberry Pi notes are in [backend/README.md](backend/README.md).
