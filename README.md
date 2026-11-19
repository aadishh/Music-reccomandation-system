# 🎵 DeepFace Emotion Multi-Provider Music Recommender

An AI-driven music recommendation and authorized streaming platform built with **Python**, **Flask**, **DeepFace**, **OpenCV**, and a **Multi-Provider Music API Architecture** supporting **Jamendo**, **Audius**, and **Mubert**.

Completely independent of Spotify, this system detects facial emotions from a webcam, normalizes music metadata across multiple providers into a unified schema, enforces strict copyright and commercial licensing verification, and plays authorized audio streams directly inside a unified in-browser player.

---

## 🌟 Key Features

- **Facial Emotion Recognition**: Uses DeepFace (with automatic graceful fallback) to detect 7 primary emotions: `happy`, `sad`, `angry`, `neutral`, `fear`, `surprise`, and `disgust`.
- **Multi-Provider Music Abstraction Layer**:
  - **Jamendo API v3.0**: Catalog search, Creative Commons tag discovery, audio streaming (`mp32`), and Jamendo Pro licensing checks.
  - **Audius REST API v1**: Decentralized catalog search, trending tracks, stream endpoint resolution with gating enforcement (`is_streamable`, `stream_conditions`), and Open Music License / Creative Commons tracking.
  - **Mubert API v3**: Optional generative AI channels and time-limited stream links with B2B commercial license verification.
- **Unified Track Schema**: Standardized domain model normalizing track IDs, titles, artists, albums, genres, duration, BPM, energy, mood tags, artwork, authorized playback URLs, and licensing compliance metadata.
- **Strict Licensing Validation Engine**:
  - Supports `non_commercial` and `commercial` deployment policies.
  - Enforces per-track permissions: blocks tracks carrying Non-Commercial licenses (`CC-NC`), unverified free-tier Jamendo streams, Audius `All Rights Reserved` or gated tracks in commercial mode.
  - Generates required attribution strings for Creative Commons tracks.
  - Never bypasses provider restrictions or caches/proxies audio payloads.
- **Intelligent Emotion Recommendation Engine**:
  - **Mode A (Mood Matching)**: Directly aligns musical energy, tempo, and mood tags with your detected emotional state.
  - **Mode B (Mood Shifting)**: Applies iso-principle psychological transitions to gently guide negative or fatigued states toward calming or uplifting states.
  - **Configurable Weighted Scoring**: Dynamically scores and ranks candidates using emotion confidence, user moods, genres, artists, language, BPM, energy, listening history, and likes/dislikes.
- **Unified HTML5 Audio Player**:
  - Play/pause, next/previous, scrubber seek, volume/mute, shuffle, repeat (`off` / `all` / `one`).
  - Queue, favorites, search catalog, and listening history with quick play actions.
  - Automatic expired-stream recovery: refreshes expiring tokens seamlessly without playback interruptions.
- **Secure API & Session Management**:
  - Signed Flask session identity and CSRF tokens for web clients.
  - Optional `Authorization: Bearer <APP_API_KEY>` for external API consumers.
  - Upstream provider credentials (`JAMENDO_CLIENT_ID`, `AUDIUS_API_KEY`, etc.) are kept strictly backend-side and never leaked to frontend code or API responses.

---

## 📐 System Architecture

```text
[ Webcam / Client Browser ]
           │
           ▼
[ Flask Application (app.py) ]
  ├── Emotion Pipeline: DeepFace / FallbackEmotionDetector
  ├── Blueprint: /api/music/* (Session & API Key Auth + CSRF)
  └── Services:
        ├── ProviderRegistry (Cross-Provider Fallback & Health)
        ├── LicensingValidator (Non-Commercial vs. Commercial Policy)
        ├── EmotionRecommendationEngine (Mood Matching & Mood Shifting)
        ├── MetadataTTLCache (Safe Metadata Caching; No Audio Caching)
        ├── MusicStorage (SQLite: History, Feedback, Favorites, Preferences)
        └── BaseMusicProvider Abstraction Layer
              ├── JamendoProvider   ──> Jamendo API v3.0
              ├── AudiusProvider    ──> Audius REST API v1
              └── MubertProvider    ──> Mubert API v3 (Optional B2B)
```

---

## 📋 Unified Track Schema

All tracks across all providers are normalized into the `UnifiedTrack` model:

| Field | Type | Description |
| :--- | :--- | :--- |
| `internal_id` | `str` | Normalized ID format `<provider>:<provider_track_id>` (e.g. `jamendo:1001`, `audius:D72kP`) |
| `provider` | `str` | Provider identifier (`jamendo`, `audius`, `mubert`) |
| `provider_track_id`| `str` | Upstream provider track or channel identifier |
| `title` | `str` | Track title |
| `artist` | `str` | Artist or creator name |
| `album` | `str` (optional) | Album or collection name |
| `genre` | `str` (optional) | Normalized musical genre |
| `duration` | `int` (optional) | Duration in seconds |
| `bpm` | `float` (optional) | Beats per minute (when available or estimated) |
| `energy` | `float` (optional) | Normalized acoustic energy (`0.0` to `1.0`) |
| `mood_tags` | `list[str]` | Normalized mood tags (e.g. `['happy', 'upbeat']`) |
| `language` | `str` (optional) | ISO 2-letter language code |
| `artwork` | `str` (optional) | Album/track cover art URL |
| `preview_url` | `str` (optional) | Short audio preview stream URL |
| `playback_url` | `str` (optional) | Approved, direct audio stream URL |
| `playback_reference` | `str` (optional) | Canonical provider permalink or stream reference |
| `playback_expires_at`| `str` (optional) | ISO-8601 UTC timestamp if the URL expires |
| `is_available` | `bool` | Whether the track is currently playable |
| `licensing` | `LicensingMetadata` | Detailed licensing, permitted playback, and verification record |
| `provider_metadata` | `dict` | Provider-specific raw metadata kept strictly separate |

---

## ⚖️ Licensing & Commercial Verification

The licensing engine enforces copyright compliance before stream URLs are returned to clients:

- **Non-Commercial Mode (`APP_DEPLOYMENT_MODE=non_commercial`)**:
  - Permits personal and non-commercial streaming under standard Jamendo API free tier (Creative Commons licenses).
  - Permits open, streamable Audius tracks with `is_streamable=True` and no access conditions.
  - Blocks gated tracks (e.g., Audius tracks with `stream_conditions` requiring tokens/NFTs) and unstreamable tracks.
- **Commercial Mode (`APP_DEPLOYMENT_MODE=commercial`)**:
  - **Strictly blocks** tracks with Non-Commercial restrictions (`CC-NC`).
  - **Strictly blocks** standard Jamendo free-tier tracks unless covered by verified Jamendo Licensing / Pro commercial agreements.
  - **Strictly blocks** Audius tracks marked `All Rights Reserved` or unverified for commercial broadcasting.
  - **Strictly blocks** Mubert generative streams unless an active B2B commercial license is verified.
- **Attribution**: Automatically generates formatted attribution text for Creative Commons (CC BY, CC BY-SA, etc.) tracks displayed prominently in the web player.
- **Redistribution Prohibited**: Standard streaming permissions never allow downloading, re-hosting, or proxying raw audio bytes.

---

## 📡 REST API Reference

All `/api/music/*` routes are authenticated via signed Flask session cookie (with `X-CSRF-Token` header for `POST` write requests) or programmatic `Authorization: Bearer <APP_API_KEY>`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/music/providers` | List provider capabilities, health, and current deployment policy (no secrets). |
| `GET` | `/api/music/search` | Search normalized tracks across providers (`q`, `provider`, `genre`, `mood`, `limit`). |
| `GET` | `/api/music/track/<track_id>` | Retrieve full metadata and licensing compliance for a specific track ID. |
| `GET` | `/api/music/playback/<track_id>` | Resolve fresh authorized stream URL and record listening history. |
| `GET` | `/api/music/recommendations` | Emotion/mood-aware ranked recommendations (`emotion`, `mode`, `genres`, `limit`). |
| `POST`| `/api/music/feedback` | Record user feedback: `like`, `dislike`, `skip`, or `neutral`. |
| `GET` | `/api/music/history` | Retrieve recent listening history for the current session. |
| `GET` | `/api/music/favorites` | List favorite tracks for the current session. |
| `POST`| `/api/music/favorites` | Add or remove a track from favorites (`is_favorite: true/false`). |
| `GET` / `POST` | `/api/music/preferences` | Get or update user preferred genres, artists, language, and default mode. |

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11, 3.12, 3.13)
- Modern web browser with webcam access

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/your-username/Music-reccomandation-system.git
cd Music-reccomandation-system

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### 3. Provider Configuration (`.env`)
Configure credentials only for the providers you wish to activate:
```ini
# Jamendo API (https://developer.jamendo.com)
JAMENDO_ENABLED=true
JAMENDO_CLIENT_ID=your_jamendo_client_id

# Audius API (https://docs.audius.co/api)
# Note: Audius public read works out of the box; set API key for higher rate limits
AUDIUS_ENABLED=true
AUDIUS_API_KEY=your_optional_audius_api_key

# Mubert API (Optional generative audio B2B plan)
MUBERT_ENABLED=false
MUBERT_COMPANY_ID=
MUBERT_LICENSE_TOKEN=
```

### 4. Run the Application
```bash
python app.py
```
Open your browser at: **`http://localhost:8080`**

### 5. Run with Docker
```bash
docker build -t emotion-music-app .
docker run -p 8080:8080 --env-file .env emotion-music-app
```

---

## 🧪 Running Automated Tests

A comprehensive test suite of 41 unit and integration tests covers each provider, normalization, licensing, recommendations, streams, and API authentication:

```bash
# Run with pytest
pytest tests/ -v

# Or run with Python's built-in unittest
python3 -m unittest discover -s tests -v
```

---

## 📄 License
This application is distributed for non-commercial educational and demonstration purposes. All audio playback complies with upstream provider terms and individual artist Creative Commons / Open Music licenses.
