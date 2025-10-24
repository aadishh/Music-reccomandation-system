# 🎵 DeepFace Emotion Music Recommender

An intelligent web application that uses **DeepFace AI** to analyze your facial emotions through webcam and automatically recommends personalized Spotify playlists based on your current mood.

## ✨ Features

- **🧠 Real AI Emotion Detection**: Uses DeepFace for accurate facial emotion analysis
- **📷 Auto-Capture Mode**: Continuous emotion monitoring every 30 seconds
- **🎵 Smart Music Recommendations**: Curated Spotify playlists for each emotion
- **🎶 Random Song Selection**: Automatically picks random songs from playlists
- **📱 Mobile Responsive**: Works on desktop, tablet, and mobile devices
- **⚡ Real-time Analysis**: Instant emotion detection and music recommendations

## 🎯 Supported Emotions & Music

| Emotion | Music Style | Playlist Count |
|---------|-------------|----------------|
| **😊 Happy** | Upbeat, energetic, pop | 4 playlists |
| **😢 Sad** | Melancholic, soothing, acoustic | 4 playlists |
| **😠 Angry** | Intense, powerful, rock/metal | 4 playlists |
| **😐 Neutral** | Balanced, versatile, mixed | 4 playlists |
| **😨 Fear** | Calming, reassuring, ambient | 2 playlists |

## 🚀 Quick Start

### **Local Development**
```bash
# 1. Create virtual environment
python3 -m venv emotion_env
source emotion_env/bin/activate  # On macOS/Linux

# 2. Install dependencies
pip install flask flask-cors spotipy opencv-python deepface tf-keras

# 3. Run the app
python3 app.py

# 4. Open browser
# Visit: http://localhost:8080
```

### **Production Deployment**
```bash
# Deploy to Render.com, Railway, or Heroku
git push origin main
# Uses: requirements.txt, Procfile, runtime.txt
```

## 🎮 How to Use

### **Manual Mode**
1. **Start Camera** - Enable webcam access
2. **Capture Emotion** - Click to analyze your current emotion
3. **Get Music** - Spotify playlist opens automatically

### **Auto-Capture Mode** 
1. **Start Camera** - Enable webcam access
2. **Start Auto-Capture** - Begins continuous monitoring
3. **Automatic Music** - Emotion analyzed every 30 seconds, music changes automatically
4. **Stop Auto-Capture** - Return to manual mode

## 🛠️ Technology Stack

- **AI/ML**: DeepFace, TensorFlow, OpenCV
- **Backend**: Flask (Python)
- **Frontend**: HTML5, CSS3, JavaScript
- **Music API**: Spotify Web API
- **Deployment**: Render.com compatible

## 📁 Project Structure

```
emotion-music-app/
├── app.py                         # 🧠 Main DeepFace application
├── config.py                      # ⚙️ Configuration & playlists
├── requirements.txt               # 📦 Production dependencies
├── Procfile                       # 🚀 Deployment config
├── runtime.txt                    # 🐍 Python version
├── render.yaml                    # 🔧 Render configuration
├── haarcascade_frontalface_default.xml  # 👤 Face detection
├── templates/index.html           # 🌐 Web interface
├── static/css/style.css          # 🎨 Styling
├── static/js/app.js              # ⚡ Frontend logic
├── LOCAL_DEVELOPMENT.md          # 🖥️ Development guide
└── README.md                     # 📖 This file
```

## 🔧 Configuration

### **Spotify Playlists**
Edit `config.py` to customize playlist URLs:
```python
EMOTION_PLAYLISTS = {
    'happy': [
        'https://open.spotify.com/playlist/your-playlist-id',
        # Add more playlists...
    ],
    # Configure other emotions...
}
```

### **Auto-Capture Settings**
```python
AUTO_CAPTURE_SETTINGS = {
    'enabled': True,
    'interval_seconds': 30,  # Capture every 30 seconds
    'songs_before_recheck': 3,
    'auto_play_random_song': True
}
```

## 🌐 API Endpoints

- **`/`** - Main web interface
- **`/analyze`** - Emotion analysis (POST)
- **`/auto-capture`** - Toggle auto-capture (POST)
- **`/settings`** - Get/update settings
- **`/reset`** - Reset song counter
- **`/health`** - Health check
- **`/test`** - System test

## 🚀 Deployment Options

### **Render.com (Recommended)**
1. Push to GitHub
2. Connect repository to Render
3. Deploy automatically with `requirements.txt`

### **Railway.app**
1. Connect GitHub repository
2. Auto-deploys with Procfile

### **Heroku**
```bash
heroku create emotion-music-app
git push heroku main
```

## 🎯 Performance

- **Emotion Analysis**: 2-5 seconds with DeepFace
- **Auto-Capture**: Every 30 seconds (configurable)
- **Memory Usage**: ~500MB (includes TensorFlow)
- **Accuracy**: High with DeepFace AI models

## 🔍 Browser Compatibility

- ✅ Chrome 60+ (Recommended)
- ✅ Firefox 55+
- ✅ Safari 11+
- ✅ Edge 79+
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)

**Note**: HTTPS required for webcam access (automatically provided by deployment platforms)

## 🐛 Troubleshooting

### **Camera Issues**
- Grant browser camera permissions
- Ensure no other apps are using camera
- Try different browsers (Chrome works best)

### **Emotion Detection Issues**
- Ensure good lighting conditions
- Position face clearly in camera frame
- Wait for DeepFace models to download (first run)

### **Performance Issues**
- DeepFace models download on first use (~100MB)
- Subsequent runs are faster
- Consider upgrading to paid hosting for better performance

## 🔒 Privacy & Security

- **No Data Storage**: Images processed in real-time, not saved
- **Local Processing**: Emotion analysis on your server
- **Spotify Integration**: Only opens public playlist links
- **No Account Required**: Works without Spotify login

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Make changes and test locally
4. Submit pull request

## 📄 License

This project is open source and available under the MIT License.

## 🙏 Acknowledgments

- **DeepFace**: For advanced emotion recognition
- **OpenCV**: For computer vision capabilities
- **Spotify**: For music streaming integration
- **TensorFlow**: For deep learning backend

---

**Built with 🧠 AI and ❤️ for music lovers who want personalized recommendations based on their real emotions!**

### 🎵 Ready to let AI read your emotions and play the perfect music? Start the app and let DeepFace work its magic! ✨