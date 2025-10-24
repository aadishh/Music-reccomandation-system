# Deployment Guide for Emotion Music Recommender

## 🚀 Free Deployment Options

### 1. **Render.com (Recommended)**
**Pros**: Easy setup, good free tier, supports Python apps
**Free Tier**: 750 hours/month, sleeps after 15min inactivity

**Steps**:
1. Push code to GitHub repository
2. Go to [render.com](https://render.com) and sign up
3. Connect your GitHub account
4. Create new "Web Service"
5. Select your repository
6. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn web_app:app`
   - **Environment**: Python 3
7. Add environment variables if needed
8. Deploy!

### 2. **Railway.app**
**Pros**: Simple deployment, good performance
**Free Tier**: $5 credit monthly, sleeps after inactivity

**Steps**:
1. Push to GitHub
2. Go to [railway.app](https://railway.app)
3. "Deploy from GitHub"
4. Select repository
5. Railway auto-detects Python and uses Procfile
6. Deploy automatically

### 3. **Heroku** 
**Pros**: Most popular, extensive documentation
**Free Tier**: Discontinued, but has affordable paid plans ($7/month)

**Steps**:
1. Install Heroku CLI
2. `heroku create your-app-name`
3. `git push heroku main`
4. `heroku ps:scale web=1`

### 4. **PythonAnywhere**
**Pros**: Python-focused, simple setup
**Free Tier**: Limited but functional

**Steps**:
1. Upload files to PythonAnywhere
2. Create web app with Flask
3. Configure WSGI file to point to `web_app:app`

## 📋 Pre-Deployment Checklist

### Required Files (✅ Already Created):
- `web_app.py` - Main Flask application
- `requirements.txt` - Dependencies
- `Procfile` - Deployment configuration
- `runtime.txt` - Python version
- `config.py` - Configuration
- `templates/` - HTML templates
- `static/` - CSS/JS files

### Environment Setup:
1. **Download Haar Cascade**:
   ```bash
   wget https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml
   ```

2. **Test Locally**:
   ```bash
   pip install -r requirements.txt
   python web_app.py
   ```
   Visit `http://localhost:5000`

## 🔧 Configuration for Deployment

### Environment Variables (Optional):
```bash
# For production
FLASK_ENV=production
PORT=5000

# Spotify API (if using environment variables)
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
```

### Memory Optimization:
The app uses TensorFlow/DeepFace which can be memory-intensive. For free tiers:

1. **Reduce TensorFlow Memory**:
   Add to `web_app.py`:
   ```python
   import tensorflow as tf
   tf.config.experimental.set_memory_growth(
       tf.config.list_physical_devices('GPU')[0], True
   )
   ```

2. **Use Lighter Models** (if needed):
   Modify DeepFace analysis to use smaller models

## 🌐 Deployment Steps (Render Example)

### 1. Prepare Repository:
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/emotion-music-app.git
git push -u origin main
```

### 2. Deploy on Render:
1. Go to [render.com](https://render.com)
2. "New" → "Web Service"
3. Connect GitHub repository
4. Configure:
   - **Name**: emotion-music-app
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn web_app:app`
   - **Instance Type**: Free

### 3. Add Files to Repository:
Make sure these files are in your repo:
- `haarcascade_frontalface_default.xml`
- All Python files
- `templates/` and `static/` folders

## 📱 Features of Deployed App

### Web Interface:
- **Camera Access**: Uses browser webcam
- **Real-time Emotion Detection**: Analyze emotions via web interface
- **Playlist Recommendations**: Direct Spotify links
- **Settings**: Configure recheck intervals
- **Song Counter**: Track songs played

### Continuous Mode Features:
- Set number of songs before emotion recheck
- Manual emotion analysis
- Song counter with reset functionality
- Responsive design for mobile/desktop

## 🔍 Troubleshooting Deployment

### Common Issues:

1. **Memory Errors**:
   - Use smaller TensorFlow models
   - Increase instance memory (paid plans)

2. **Camera Access**:
   - Ensure HTTPS (required for camera in browsers)
   - Most platforms provide HTTPS automatically

3. **Slow Cold Starts**:
   - Free tiers sleep after inactivity
   - First request may be slow (30-60 seconds)

4. **File Size Limits**:
   - Some platforms limit file sizes
   - Consider using CDN for large model files

### Performance Tips:
- Use caching for model loading
- Implement request queuing for multiple users
- Consider using Redis for session management

## 💡 Recommended Deployment: Render.com

**Why Render**:
- Easy GitHub integration
- Automatic HTTPS
- Good free tier (750 hours/month)
- Supports Python/Flask out of the box
- Auto-deploys on git push

**Expected Performance**:
- Cold start: 30-60 seconds
- Warm requests: 2-5 seconds
- Emotion analysis: 3-8 seconds

Your app will be accessible at: `https://your-app-name.onrender.com`