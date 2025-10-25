# 🎵 How to Run the Emotion Music App

## Quick Start

### 1. Local Development (Python)
```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```
Visit: http://localhost:8080

### 2. Docker (Recommended for deployment issues)
```bash
# Build Docker image
docker build -t emotion-music-app .

# Run container
docker run -p 8080:8080 emotion-music-app
```
Visit: http://localhost:8080

### 3. Deploy on Render
1. Push code to GitHub
2. Connect repository to Render
3. Render uses `render.yaml` automatically
4. Choose Docker or Python environment

## What the App Does

- 📷 **Captures your photo** from webcam
- 🧠 **Detects your emotion** (happy, sad, angry, etc.)
- 🎵 **Recommends Spotify playlists** based on your mood
- 🔄 **Auto-capture mode** for continuous monitoring

## Files You Need

**Essential:**
- `app.py` - Main application
- `config.py` - Spotify playlists
- `requirements.txt` - Dependencies
- `Dockerfile` - For Docker deployment
- `render.yaml` - For Render deployment

**Web Interface:**
- `templates/` - HTML files
- `static/` - CSS, JS, images

## Troubleshooting

**Dependencies fail?** → Use Docker
**TensorFlow issues?** → App has smart fallback
**No webcam?** → Upload image manually
**Deployment fails?** → Check render.yaml settings