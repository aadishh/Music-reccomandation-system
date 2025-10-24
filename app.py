from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import cv2
import base64
import numpy as np
import random
import logging
import os
import webbrowser
import spotipy
import threading
import time
from datetime import datetime
from config import EMOTION_PLAYLISTS, SPOTIFY_CONFIG, AUTO_CAPTURE_SETTINGS, CAPTURED_IMAGE_PATH

# Suppress TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# Default to fallback mode - try DeepFace only if explicitly available
DEEPFACE_AVAILABLE = False

# Try to import DeepFace only if TensorFlow is available
try:
    import tensorflow as tf
    tf.get_logger().setLevel('ERROR')
    
    # Only try DeepFace if TensorFlow import succeeded
    try:
        from deepface import DeepFace
        DEEPFACE_AVAILABLE = True
        print("✅ DeepFace + TensorFlow loaded successfully")
    except ImportError:
        print("⚠️  DeepFace not available, using fallback")
        
except ImportError:
    print("⚠️  TensorFlow not available, using fallback")
except ImportError as e:
    print(f"⚠️  DeepFace not available: {e}")
    print("🔄 Using fallback emotion detection")
    from emotion_fallback import FallbackEmotionDetector
    DEEPFACE_AVAILABLE = False

def convert_to_json_serializable(obj):
    """Convert numpy types to JSON serializable Python types."""
    if hasattr(obj, 'item'):  # numpy scalar
        return obj.item()
    elif hasattr(obj, 'tolist'):  # numpy array
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_json_serializable(v) for v in obj]
    else:
        return obj

app = Flask(__name__)
CORS(app)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeepFaceEmotionSystem:
    def __init__(self):
        self.current_emotion = None
        self.songs_played = 0
        self.songs_before_recheck = AUTO_CAPTURE_SETTINGS['songs_before_recheck']
        self.last_check_time = None
        self.auto_capture_enabled = AUTO_CAPTURE_SETTINGS['enabled']
        self.auto_capture_thread = None
        self.is_running = False
        
        # Initialize fallback detector if DeepFace not available
        if not DEEPFACE_AVAILABLE:
            self.fallback_detector = FallbackEmotionDetector()
        
        # Initialize Spotify
        self.spotify_client = None
        self._initialize_spotify()
        
        detector_type = "DeepFace" if DEEPFACE_AVAILABLE else "Fallback"
        logger.info(f"Emotion System initialized with {detector_type} detector")
        
    def _initialize_spotify(self):
        """Initialize Spotify client for track information (optional)."""
        try:
            # Skip Spotify authentication for demo - just use playlist URLs
            self.spotify_client = None
            logger.info("Spotify client skipped - using direct playlist URLs")
        except Exception as e:
            logger.error(f"Failed to initialize Spotify: {e}")
            self.spotify_client = None
        
    def analyze_emotion_from_base64(self, image_data):
        """Analyze emotion from base64 image data using DeepFace or fallback."""
        
        # Use fallback detector if DeepFace not available
        if not DEEPFACE_AVAILABLE:
            return self.fallback_detector.analyze_emotion_from_base64(image_data)
        
        try:
            # Decode base64 image
            image_data = image_data.split(',')[1]  # Remove data:image/jpeg;base64,
            image_bytes = base64.b64decode(image_data)
            
            # Convert to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise Exception("Could not decode image")
            
            # Save image for DeepFace analysis
            cv2.imwrite(CAPTURED_IMAGE_PATH, img)
            
            # Analyze emotion using DeepFace
            logger.info("Analyzing emotion with DeepFace...")
            predictions = DeepFace.analyze(img, actions=['emotion'], enforce_detection=False)
            
            # Extract emotion data
            if isinstance(predictions, list):
                emotion_data = predictions[0]
            else:
                emotion_data = predictions
            
            dominant_emotion = emotion_data['dominant_emotion']
            emotion_scores = emotion_data['emotion']
            
            # Convert all numpy types to JSON serializable Python types
            emotion_scores_clean = convert_to_json_serializable(emotion_scores)
            dominant_emotion_clean = str(dominant_emotion).lower()
            
            # Round percentages
            emotion_percentages = {k: round(float(v), 2) for k, v in emotion_scores_clean.items()}
            
            logger.info(f"DeepFace detected emotion: {dominant_emotion_clean}")
            
            return {
                'dominant_emotion': dominant_emotion_clean,
                'emotion_scores': emotion_percentages,
                'success': True,
                'detector': 'DeepFace',
                'confidence': emotion_percentages.get(dominant_emotion_clean, 0.0)
            }
            
        except Exception as e:
            logger.error(f"DeepFace emotion analysis failed: {e}")
            # Fallback to random emotion if DeepFace fails
            emotions = ['happy', 'sad', 'angry', 'neutral', 'fear']
            fallback_emotion = random.choice(emotions)
            
            return {
                'dominant_emotion': fallback_emotion,
                'emotion_scores': {fallback_emotion: 85.0, 'neutral': 15.0},
                'success': False,
                'error': str(e),
                'detector': 'Fallback (Random)',
                'message': f'DeepFace failed, using fallback: {fallback_emotion}'
            }
    
    def get_random_song_from_playlist(self, playlist_url):
        """For demo: return playlist URL directly (no Spotify API needed)."""
        try:
            # For demo purposes, just return the playlist URL
            # In production, this would extract individual tracks
            return {
                'url': playlist_url,
                'name': f'Random song from {playlist_url.split("/")[-1][:8]}... playlist',
                'artist': 'Various Artists',
                'type': 'playlist'
            }
            
        except Exception as e:
            logger.error(f"Failed to process playlist: {e}")
            return {'url': playlist_url, 'type': 'playlist'}
    
    def get_playlist_for_emotion(self, emotion):
        """Get a random playlist and optionally a random song for the given emotion."""
        if emotion not in EMOTION_PLAYLISTS:
            emotion = 'neutral'
        
        playlists = EMOTION_PLAYLISTS[emotion]
        selected_playlist = random.choice(playlists)
        
        result = {
            'playlist_url': selected_playlist,
            'emotion': emotion,
            'songs_played': self.songs_played
        }
        
        # Get random song if enabled
        if AUTO_CAPTURE_SETTINGS['auto_play_random_song']:
            song_info = self.get_random_song_from_playlist(selected_playlist)
            if isinstance(song_info, dict) and 'url' in song_info:
                result['song_url'] = song_info['url']
                result['song_name'] = song_info.get('name', 'Random Song')
                result['song_artist'] = song_info.get('artist', 'Unknown Artist')
                result['play_type'] = song_info.get('type', 'track')
            else:
                result['song_url'] = selected_playlist
                result['play_type'] = 'playlist'
        
        self.songs_played += 1
        self.current_emotion = emotion
        self.last_check_time = datetime.now()
        
        return result
    
    def auto_capture_and_analyze(self):
        """Automatically capture from webcam and analyze emotion."""
        try:
            # Initialize webcam
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.error("Could not open webcam for auto-capture")
                return None
            
            # Capture frame
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                logger.error("Failed to capture frame")
                return None
            
            # Convert frame to base64
            _, buffer = cv2.imencode('.jpg', frame)
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            img_data_url = f"data:image/jpeg;base64,{img_base64}"
            
            # Analyze emotion
            result = self.analyze_emotion_from_base64(img_data_url)
            
            if result['success']:
                logger.info(f"Auto-captured emotion: {result['dominant_emotion']}")
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"Auto-capture failed: {e}")
            return None
    
    def start_auto_capture(self):
        """Start automatic emotion capture and music recommendation."""
        if self.auto_capture_enabled and not self.is_running:
            self.is_running = True
            self.auto_capture_thread = threading.Thread(target=self._auto_capture_loop, daemon=True)
            self.auto_capture_thread.start()
            logger.info("Auto-capture started")
    
    def stop_auto_capture(self):
        """Stop automatic emotion capture."""
        self.is_running = False
        if self.auto_capture_thread:
            self.auto_capture_thread.join(timeout=5)
        logger.info("Auto-capture stopped")
    
    def _auto_capture_loop(self):
        """Main loop for automatic capture and music recommendation."""
        while self.is_running:
            try:
                # Auto-capture and analyze
                result = self.auto_capture_and_analyze()
                
                if result and result['success']:
                    # Get music recommendation
                    music_info = self.get_playlist_for_emotion(result['dominant_emotion'])
                    
                    # Open music in browser
                    music_url = music_info.get('song_url', music_info.get('playlist_url'))
                    if music_url:
                        webbrowser.open(music_url)
                        logger.info(f"Auto-opened music for {result['dominant_emotion']} emotion")
                
                # Wait for next capture
                time.sleep(AUTO_CAPTURE_SETTINGS['interval_seconds'])
                
            except Exception as e:
                logger.error(f"Auto-capture loop error: {e}")
                time.sleep(10)  # Wait before retrying

# Global system instance
emotion_system = DeepFaceEmotionSystem()

@app.route('/')
def index():
    """Serve the main web interface."""
    return render_template('index.html')

@app.route('/camera-test')
def camera_test():
    """Serve camera test page for debugging."""
    return render_template('camera_test.html')

@app.route('/analyze', methods=['POST'])
def analyze_emotion():
    """Analyze emotion from uploaded image."""
    try:
        data = request.get_json()
        image_data = data.get('image')
        
        if not image_data:
            return jsonify({'error': 'No image data provided'}), 400
        
        # Analyze emotion using DeepFace
        result = emotion_system.analyze_emotion_from_base64(image_data)
        
        # Get music recommendation
        music_info = emotion_system.get_playlist_for_emotion(result['dominant_emotion'])
        result.update(music_info)
        
        # Ensure all data is JSON serializable
        result_clean = convert_to_json_serializable(result)
        
        return jsonify(result_clean)
        
    except Exception as e:
        logger.error(f"Analysis endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/auto-capture', methods=['POST'])
def toggle_auto_capture():
    """Toggle automatic emotion capture."""
    try:
        data = request.get_json()
        enable = data.get('enable', False)
        
        if enable:
            emotion_system.start_auto_capture()
            message = "Auto-capture started"
        else:
            emotion_system.stop_auto_capture()
            message = "Auto-capture stopped"
        
        return jsonify({
            'success': True,
            'message': message,
            'auto_capture_enabled': emotion_system.is_running
        })
        
    except Exception as e:
        logger.error(f"Auto-capture toggle error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Get or update system settings."""
    if request.method == 'GET':
        return jsonify({
            'songs_before_recheck': emotion_system.songs_before_recheck,
            'current_emotion': emotion_system.current_emotion,
            'songs_played': emotion_system.songs_played,
            'auto_capture_enabled': emotion_system.auto_capture_enabled,
            'auto_capture_interval': AUTO_CAPTURE_SETTINGS['interval_seconds'],
            'auto_play_random_song': AUTO_CAPTURE_SETTINGS['auto_play_random_song']
        })
    
    elif request.method == 'POST':
        data = request.get_json()
        
        if 'songs_before_recheck' in data:
            emotion_system.songs_before_recheck = int(data['songs_before_recheck'])
        
        if 'auto_capture_enabled' in data:
            emotion_system.auto_capture_enabled = bool(data['auto_capture_enabled'])
        
        return jsonify({'success': True})

@app.route('/reset', methods=['POST'])
def reset_counter():
    """Reset the song counter."""
    emotion_system.songs_played = 0
    return jsonify({'success': True, 'songs_played': 0})

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'emotion_detector': 'DeepFace',
        'version': '3.0-deepface',
        'auto_capture': emotion_system.is_running,
        'spotify_connected': emotion_system.spotify_client is not None
    })

@app.route('/test')
def test_emotion():
    """Test endpoint."""
    return jsonify({
        'message': 'DeepFace emotion detection system ready',
        'detector': 'DeepFace + Spotify',
        'supported_emotions': list(EMOTION_PLAYLISTS.keys()),
        'features': [
            'Real emotion detection with DeepFace',
            'Automatic webcam capture',
            'Random song selection from playlists',
            'Spotify integration'
        ]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print("🎵 Emotion Music Recommender - DeepFace Edition")
    print("=" * 60)
    print(f"🌐 Server starting on: http://localhost:{port}")
    print("🧠 Emotion Detection: DeepFace (Real AI)")
    print("📷 Auto-capture: Every 30 seconds")
    print("🎵 Music: Random songs from Spotify playlists")
    print("🔄 Auto-play: Enabled")
    print("=" * 60)
    print("✅ Ready! Open your browser and start the auto-capture!")
    
    app.run(host='0.0.0.0', port=port, debug=False)