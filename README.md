# 🎵 DeepFace Emotion-Based Multi-Provider Music Recommender

An AI-powered music recommendation platform that detects facial emotions and recommends music using a multi-provider architecture.

Built with **Python, Flask, DeepFace, OpenCV, Supabase PostgreSQL**, and integrated music providers including **Jamendo, Audius, and Mubert**.

The platform provides emotion-aware music discovery, unified music metadata, licensing verification, secure user authentication, privacy-focused emotion processing, and in-browser audio playback.

Designed independently of Spotify, the system uses authorized provider APIs and respects upstream streaming and licensing restrictions.

---

## 🌟 Key Features

### 1. Facial Emotion Recognition

- Real-time facial emotion analysis using webcam input.
- DeepFace-powered emotion detection.
- Supports seven primary emotions:
  - Happy
  - Sad
  - Angry
  - Neutral
  - Fear
  - Surprise
  - Disgust
- Lightweight fallback emotion detection when TensorFlow or DeepFace is unavailable.
- In-memory image processing designed to avoid persistent storage of webcam frames.
- Explicit camera consent before emotion analysis.

### 2. Multi-Provider Music Integration

Integrates multiple music providers through a unified abstraction layer.

**Jamendo API**
- Music catalog search.
- Creative Commons music discovery.
- Audio stream integration.
- Licensing and attribution metadata.

**Audius API**
- Decentralized music catalog search.
- Trending tracks.
- Stream endpoint resolution.
- Streamability and access-condition checks.
- License metadata tracking.

**Mubert API (Optional)**
- AI-generated music channels.
- Time-limited streaming links.
- Commercial licensing verification for supported plans.

### 3. Unified Music Metadata Architecture

Normalizes provider-specific music information into a common track schema.

Supported metadata includes:

- Track ID
- Title and artist
- Album
- Genre
- Duration
- BPM
- Energy
- Mood tags
- Artwork
- Playback URL
- Provider information
- Licensing and attribution metadata

### 4. Copyright and Licensing Validation

A dedicated licensing engine evaluates track eligibility before playback.

Features include:

- Commercial and non-commercial deployment policies.
- Creative Commons license verification.
- Blocking of Non-Commercial (CC-NC) tracks in commercial mode.
- Audius streamability and access-condition enforcement.
- Jamendo licensing verification.
- Attribution generation for applicable Creative Commons tracks.
- No bypassing of provider restrictions or unauthorized audio proxying.

### 5. Supabase Authentication and PostgreSQL

Uses Supabase for cloud authentication and persistent PostgreSQL storage.

**Authentication**
- Email and password registration.
- Email verification.
- Google OAuth.
- Password recovery and reset.
- Session management.
- Account deletion.

**Database**
- User profiles.
- Music preferences.
- Consent records.
- Emotion history (optional).
- Listening history.
- Favorite tracks.
- Policy versions.
- Privacy requests.
- Security audit logs.

**Security**
- PostgreSQL Row Level Security (RLS).
- User-specific data access policies.
- Service-role operations restricted to trusted backend code.
- Foreign-key relationships and cascading deletion where configured.

### 6. Privacy and Consent Management

Privacy-focused architecture with explicit consent management.

**India DPDP Act**
- Itemized consent collection.
- Explicit camera-processing consent.
- Optional emotion-history storage.
- Consent withdrawal.
- Grievance redressal information.
- Child protection safeguards.

**International Privacy Considerations**
- GDPR.
- CCPA/CPRA.
- Illinois BIPA.
- Texas CUBI.
- Washington biometric privacy requirements.

**Privacy Features**
- Data export in JSON format.
- Selective deletion of user data.
- Account deletion.
- Consent history.
- Camera-processing controls.
- No persistent storage of raw webcam images or facial templates by design.

The implementation is designed to support privacy-conscious development. It does not independently establish legal compliance.

### 7. User Dashboard

Provides a centralized dashboard for:

- Profile management.
- Music preferences.
- Listening history.
- Favorite tracks.
- Emotion timeline (opt-in).
- Privacy settings.
- Consent management.
- Personal data export and deletion.

---

## 🏗️ System Architecture

```text
             Client Browser
          (Webcam + Music Player)
                    |
                    v
             Flask Application
                  app.py
                    |
       +------------+-------------+
       |            |             |
       v            v             v
    Authentication Privacy     Dashboard
       Module      Module       Module
       |            |             |
       +------------+-------------+
                    |
                    v
              Core Services
                    |
       +------------+-------------+
       |            |             |
       v            v             v
   Emotion      Music Provider  Licensing
   Detection      Registry      Validator
       |            |             |
       v            v             v
    DeepFace    Jamendo        License Rules
    OpenCV      Audius
                Mubert
                    |
                    v
             Data Repository
                    |
          +---------+---------+
          |                   |
          v                   v
       Supabase             SQLite
      PostgreSQL        Local Fallback
```

### Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, Flask |
| Frontend | HTML, CSS, JavaScript |
| Emotion Recognition | DeepFace |
| Computer Vision | OpenCV |
| Numerical Processing | NumPy |
| Data Processing | Pandas |
| Database | PostgreSQL |
| Authentication | Supabase Auth |
| Database Security | PostgreSQL RLS |
| Local Fallback | SQLite |
| Music Providers | Jamendo, Audius, Mubert |
| API Communication | Requests |
| Deployment | Docker, Gunicorn |
| Testing | Pytest |

---

## 🗄️ Database Schema and Migrations

Database migrations are available in:

```text
database/
└── migrations/
    ├── 001_initial_schema.sql
    ├── 002_rls_policies.sql
    └── 003_seed_policies.sql
```

| Migration | Description |
|---|---|
| `001_initial_schema.sql` | Creates database tables, relationships, indexes, and constraints. |
| `002_rls_policies.sql` | Enables Row Level Security and configures access policies. |
| `003_seed_policies.sql` | Inserts initial privacy, terms, and camera-consent policy versions. |

### Database Tables

- `profiles`
- `user_preferences`
- `consent_records`
- `emotion_history`
- `listening_history`
- `favorite_tracks`
- `policy_versions`
- `privacy_requests`
- `security_audit_logs`

### Running Database Migrations

1. Create a project at [Supabase](https://supabase.com).
2. Open the Supabase Dashboard.
3. Navigate to SQL Editor.
4. Execute the migration files in the following order:
   - `001_initial_schema.sql`
   - `002_rls_policies.sql`
   - `003_seed_policies.sql`

Execute each migration successfully before proceeding to the next.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11.
- Git.
- Modern web browser.
- Webcam for emotion recognition.
- Docker (optional).
- Supabase project (optional for local SQLite fallback).
- API credentials for enabled music providers.

### 1. Clone the Repository

```bash
git clone <REPOSITORY_URL>
cd <PROJECT_DIRECTORY>
```

### 2. Create a Virtual Environment

```bash
python3 -m venv .venv
```

Activate it:

**macOS / Linux**

```bash
source .venv/bin/activate
```

**Windows**

```bash
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file using `.env.example` as a template.

```ini
# Application Configuration
FLASK_SECRET_KEY=your-secure-random-secret
APP_BASE_URL=http://localhost:8080

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-publishable-key
SUPABASE_SERVICE_ROLE_KEY=your-secret-key

# Jamendo Configuration
JAMENDO_ENABLED=true
JAMENDO_CLIENT_ID=your-jamendo-client-id

# Audius Configuration
AUDIUS_ENABLED=true
AUDIUS_API_KEY=

# Mubert Configuration (Optional)
MUBERT_ENABLED=false
MUBERT_COMPANY_ID=
MUBERT_LICENSE_TOKEN=
```

**Security Notes:**

- Never commit `.env` files to GitHub.
- Never expose the Supabase secret key in frontend code.
- Keep privileged database operations on the backend.
- Configure Row Level Security before exposing user data.
- Use HTTPS for production deployments.
- Configure OAuth redirect URLs in Supabase.

### 5. Run the Application

```bash
python app.py
```

Open:

```text
http://localhost:8080
```

---

## 🐳 Docker Deployment

### Build the Docker Image

```bash
docker build -t emotion-music-app .
```

### Run the Container

```bash
docker run -p 8080:8080 --env-file .env emotion-music-app
```

The application will be available at:

```text
http://localhost:8080
```

### Deployment Considerations

- Configure production environment variables through your hosting provider.
- Do not include secrets in the Docker image.
- Use a production WSGI server such as Gunicorn.
- Configure the application health-check endpoint.
- Select hosting resources appropriate for OpenCV and DeepFace workloads.

---

## 🧪 Automated Testing

The project includes a test suite covering core functionality.

Run tests:

```bash
pytest tests/ -v
```

Test coverage includes:

- Music provider integrations.
- Unified track metadata normalization.
- Licensing validation.
- Emotion-based recommendation algorithms.
- Mood matching and mood shifting.
- Supabase repository operations.
- SQLite fallback functionality.
- Database CRUD operations.
- Account deletion and cascading operations.
- Consent history and withdrawal.
- Data export and deletion.
- In-memory image-processing behavior.
- Camera consent enforcement.
- Authentication and protected routes.

---

## 🔐 Security and Privacy

The application follows a privacy-conscious design approach:

- Explicit camera consent.
- In-memory webcam frame processing.
- No intended persistent storage of raw webcam images.
- No persistent facial embedding storage.
- Optional emotion-history collection.
- User-specific database access through RLS.
- Backend-only privileged Supabase credentials.
- Consent withdrawal and data deletion mechanisms.

Actual privacy and security guarantees depend on implementation details, infrastructure configuration, third-party services, and deployment practices.

---

## ⚖️ Legal Disclaimer

This project is intended for educational, research, and demonstration purposes.

It includes technical controls designed to support privacy and licensing considerations under applicable laws and regulations, including:

- India Digital Personal Data Protection Act, 2023.
- GDPR.
- CCPA/CPRA.
- Illinois BIPA.
- Texas CUBI.
- Applicable Creative Commons licensing requirements.

This software does not guarantee legal compliance. Organizations deploying it commercially should obtain independent legal advice and verify all applicable provider agreements, licensing permissions, and privacy obligations.

Music availability and playback rights are determined by the respective providers and rights holders.

---

## 🤝 Contributing

Contributions, bug reports, feature requests, and improvements are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Implement your changes.
4. Run the automated test suite.
5. Submit a pull request with a clear description.

Please ensure that contributions respect music-provider terms, copyright restrictions, and privacy requirements.

---

## 📄 License

Add the applicable open-source license to the repository before distributing the project.

Third-party APIs, music catalogs, audio streams, and artwork remain subject to their respective provider terms and rights-holder licenses.

---

**Built with Python, AI, computer vision, and privacy-conscious music technology.**