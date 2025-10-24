from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import cv2
import base64
import numpy as np
from deepface import DeepFace
import random
import logging
import os
from config import EMOTION_PLAYLISTS
import threading
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebEmotionSystem:
    def __init__(self):
        self.current_emotion = None
        self.songs_played = 0
        self.songs_before_recheck = 3
        self.last_check_time = None
        self.is_monitoring = False
        
    def analyze_emotion_from_base64(self, image_data):
        """Analyze emotion from base64 image data."""
        try:
            # Decode base64 image
            image_data = image_data.split(',')[1]  # Remove data:image/jpeg;base64,
            image_bytes = base64.b64decode(image_data)
            
            # Convert to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise Exception("Could not decode image")
            
            # Analyze emotion
            predictions = DeepFace.analyze(img, actions=['emotion'], enforce_detection=False)
            
            if isinstance(predictions, list):
                emotion_data = predictions[0]
            else:
                emotion_data = predictions
            
            dominant_emotion = emotion_data['dominant_emotion']
            emotion_scores = emotion_data['emotion']
            
            logger.info(f"Detected emotion: {dominant_emotion}")
            
            return {
                'dominant_emotion': dominant_emotion,
                'emotion_scores': emotion_scores,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Emotion analysis failed: {e}")
            return {
                'dominant_emotion': 'neutral',
                'emotion_scores': {},
                'success': False,
                'error': str(e)
            }
    
    def get_playlist_for_emotion(self, emotion):
        """Get a random playlist for the given emotion."""
        if emotion not in EMOTION_PLAYLISTS:
            emotion = 'neutral'
        
        playlists = EMOTION_PLAYLISTS[emotion]
        selected_playlist = random.choice(playlists)
        
        self.songs_played += 1
        self.current_emotion = emotion
        self.last_check_time = datetime.now()
        
        return {
            'playlist_url': selected_playlist,
            'emotion': emotion,
            'songs_played': self.songs_played
        }

# Global system instance
emotion_system = WebEmotionSystem()

@app.route('/')
def index():
    """Serve the main web interface."""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_emotion():
    """Analyze emotion from uploaded image."""
    try:
        data = request.get_json()
        image_data = data.get('image')
        
        if not image_data:
            return jsonify({'error': 'No image data provided'}), 400
        
        # Analyze emotion
        result = emotion_system.analyze_emotion_from_base64(image_data)
        
        if result['success']:
            # Get playlist recommendation
            playlist_info = emotion_system.get_playlist_for_emotion(result['dominant_emotion'])
            result.update(playlist_info)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Analysis endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Get or update system settings."""
    if request.method == 'GET':
        return jsonify({
            'songs_before_recheck': emotion_system.songs_before_recheck,
            'current_emotion': emotion_system.current_emotion,
            'songs_played': emotion_system.songs_played
        })
    
    elif request.method == 'POST':
        data = request.get_json()
        if 'songs_before_recheck' in data:
            emotion_system.songs_before_recheck = int(data['songs_before_recheck'])
        
        return jsonify({'success': True})

@app.route('/reset', methods=['POST'])
def reset_counter():
    """Reset the song counter."""
    emotion_system.songs_played = 0
    return jsonify({'success': True, 'songs_played': 0})

@app.route('/health')
def health_check():
    """Health check endpoint for deployment."""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)