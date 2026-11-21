# 🎵 DeepFace Emotion Multi-Provider Music Recommender

An AI-driven music recommendation and authorized streaming platform built with **Python**, **Flask**, **DeepFace**, **OpenCV**, **Supabase PostgreSQL & Authentication**, and a **Multi-Provider Music API Architecture** supporting **Jamendo**, **Audius**, and **Mubert**.

Completely independent of Spotify, this system detects facial emotions from a webcam, normalizes music metadata across multiple providers into a unified schema, enforces strict copyright and commercial licensing verification, manages user authentication with Supabase, adheres to global privacy laws (India DPDP Act 2023 & Rules 2025, California CCPA/CPRA, Illinois BIPA, GDPR), and plays authorized audio streams directly inside a unified in-browser player.

---

## 🌟 Key Features

### 1. Facial Emotion Recognition & In-Memory Privacy
- **Strictly In-Memory Processing**: Webcam frames are streamed over HTTPS, decoded in server RAM, analyzed using DeepFace, and **immediately freed from memory**.
- **Zero Disk Retention Guarantee**: No photographs, video recordings, or facial biometric templates are ever written to disk or persistent storage.
- **Biometric Law Compliance**: Operates in full compliance with Illinois BIPA (740 ILCS 14/), Texas CUBI, and Washington HB 1493 (no facial vectors, landmarks, or face embeddings are constructed or stored).
- **DeepFace AI**: Detects 7 primary emotions (`happy`, `sad`, `angry`, `neutral`, `fear`, `surprise`, `disgust`) with automatic fallback to lightweight heuristics if TensorFlow is unavailable.

### 2. Multi-Provider Music Abstraction Layer
- **Jamendo API v3.0**: Catalog search, Creative Commons tag discovery, audio streaming (`mp32`), and Jamendo Pro licensing checks.
- **Audius REST API v1**: Decentralized catalog search, trending tracks, stream endpoint resolution with gating enforcement (`is_streamable`, `stream_conditions`), and Open Music License / Creative Commons tracking.
- **Mubert API v3**: Optional generative AI channels and time-limited stream links with B2B commercial license verification.
- **Unified Track Schema**: Standardized domain model normalizing track IDs, titles, artists, albums, genres, duration, BPM, energy, mood tags, artwork, authorized playback URLs, and licensing compliance metadata.

### 3. Strict Copyright & Commercial Licensing Engine
- Supports `non_commercial` and `commercial` deployment policies.
- Enforces per-track permissions: blocks tracks carrying Non-Commercial licenses (`CC-NC`), unverified free-tier Jamendo streams, and Audius `All Rights Reserved` or gated tracks in commercial mode.
- Generates required attribution strings for Creative Commons tracks.
- Never bypasses provider restrictions or caches/proxies audio payloads.

### 4. Supabase PostgreSQL Database & Authentication
- **PostgreSQL Database**: Persistent storage for profiles, user preferences, consent records, emotion history, listening history, favorite tracks, policy versions, and security audit logs.
- **Row Level Security (RLS)**: PostgreSQL RLS policies enforce that authenticated users can only view and mutate their own records.
- **Supabase Authentication**:
  - Email & password registration with email verification.
  - Google OAuth login via Supabase GoTrue.
  - Forgot password & password reset flows.
  - Session management using secure HTTP-only cookies and Bearer tokens.
  - Cascading account deletion (permanently removes user records and auth identity).
- **Dual-Mode Repository Architecture**: Automatically uses Supabase PostgreSQL when credentials are configured, with automatic SQLite fallback for local development and offline unit testing.

### 5. Privacy Compliance & Consent Management
- **India DPDP Act, 2023 & DPDP Rules, 2025**:
  - Itemized, unbundled, affirmative consent (Terms, Privacy, Camera Processing, Emotion History).
  - Explicit camera consent required before webcam processing can begin.
  - Opt-in emotion history: emotional states are only stored if the user affirmatively opts in.
  - Full grievance redressal disclosures and response timelines.
  - Section 9 child protection safeguards (no behavioral monitoring or targeted advertising of minors).
- **US State Privacy Laws (CCPA/CPRA, VCDPA, CPA)**:
  - Notice at collection and explicit confirmation that personal data is never sold or shared.
  - Right to Access / Data Portability (1-click JSON data export).
  - Right to Erasure / Deletion (clear emotion history, clear listening history, delete account).
- **Immutable Consent Audit Ledger**: Consecutive consent actions (grants, modifications, withdrawals) append new records to an immutable ledger and never overwrite historical data.
- **Privacy Dashboard (`/dashboard/privacy`)**: Real-time consent toggles, immutable audit trail, personal data JSON export, selective data clearing, and account deletion.
- **User Dashboard (`/dashboard`)**: Profile management, music preferences, listening history, favorite tracks, and opt-in emotion timeline.

---

## 📐 System Architecture

```text
[ Client Browser / Webcam ]
           │
           ▼
[ Flask Application (app.py) ]
  ├── Auth Blueprint: /auth/* (Register, Login, Google OAuth, Reset, Delete)
  ├── Privacy Blueprint: /privacy/* (Policy, Terms, Consent, Export, Erasure)
  ├── Dashboard Blueprint: /dashboard/* (User Dashboard & Privacy Controls)
  ├── Music API: /api/music/* (Search, Track, Playback, Recommendations, Favorites)
  ├── In-Memory Emotion Pipeline: DeepFace (0-second disk retention; no face templates)
  └── Services:
        ├── ProviderRegistry (Jamendo, Audius, Mubert)
        ├── LicensingValidator (Non-Commercial vs. Commercial Policy)
        ├── EmotionRecommendationEngine (Mood Matching & Mood Shifting)
        ├── SupabaseConnectionManager (Anon client with RLS + Admin client with Service Role)
        └── SupabaseRepository / LocalFallbackRepository (Dual-mode PostgreSQL/SQLite)
```

---

## 🗄️ Database Schema & Migrations

Database migrations are located in `database/migrations/`:

| Migration File | Description |
| :--- | :--- |
| `001_initial_schema.sql` | Creates tables: `profiles`, `user_preferences`, `consent_records`, `emotion_history`, `listening_history`, `favorite_tracks`, `policy_versions`, `privacy_requests`, `security_audit_logs`, with primary keys, indexes, and foreign keys with `ON DELETE CASCADE`. |
| `002_rls_policies.sql` | Enables Row Level Security (RLS) on all tables; configures policies checking `auth.uid() = user_id`; restricts `security_audit_logs` to service role. |
| `003_seed_policies.sql` | Seeds initial legal policy versions (`privacy_policy`, `terms_and_conditions`, `camera_consent`). |

### Running Migrations on Supabase:
1. Log in to your [Supabase Dashboard](https://supabase.com).
2. Navigate to **SQL Editor** in your project.
3. Paste and execute `001_initial_schema.sql`, `002_rls_policies.sql`, and `003_seed_policies.sql` in sequence.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11, 3.12, 3.13)
- Modern web browser with webcam support
- (Optional) Free Supabase project for cloud PostgreSQL & Auth

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

### 3. Configuration (`.env`)
Configure credentials in your `.env` file:
```ini
# Flask & App Security
FLASK_SECRET_KEY=generate-a-secure-random-secret
APP_BASE_URL=http://localhost:8080

# Supabase PostgreSQL & Authentication (Optional for cloud, SQLite fallback used if blank)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key

# Jamendo API (https://developer.jamendo.com)
JAMENDO_ENABLED=true
JAMENDO_CLIENT_ID=your_jamendo_client_id

# Audius API (https://docs.audius.co/api)
AUDIUS_ENABLED=true
AUDIUS_API_KEY=

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

## 🧪 Automated Test Suite

A comprehensive test suite of **55 unit and integration tests** validates:
- Music provider integrations (Jamendo, Audius, Mubert).
- Unified track normalization and licensing validation.
- Mood matching & mood shifting recommendation algorithms.
- Supabase PostgreSQL schema, CRUD, cascade deletions, and data export.
- Immutable consent audit ledger recording and withdrawal.
- Strictly in-memory camera frame processing (verifying 0 disk writes).
- Mandatory camera consent gating for `/analyze` and `/auto-capture`.
- User authentication, registration with unbundled consents, and protected routes.

```bash
# Run the entire test suite with pytest
pytest tests/ -v
```

---

## ⚖️ Legal Disclaimer
This software implements technical architecture and controls designed to assist with compliance under the India Digital Personal Data Protection Act, 2023 & DPDP Rules, 2025, US State Privacy Laws (CCPA/CPRA), Illinois BIPA, and GDPR. However, software implementation alone does not constitute formal legal compliance. Organizations deploying this application commercially must conduct an independent legal review with qualified counsel.

---

## 📄 License
This application is distributed for educational and demonstration purposes. All audio streaming complies with upstream provider developer terms and individual artist licenses.
