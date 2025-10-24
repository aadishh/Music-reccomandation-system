"""
Fallback emotion detection system that doesn't require TensorFlow/DeepFace
Uses simple image analysis and random selection for demo purposes
"""
import cv2
import numpy as np
import random
import logging

logger = logging.getLogger(__name__)

class FallbackEmotionDetector:
    """Simple emotion detector that works without heavy ML dependencies"""
    
    def __init__(self):
        self.emotions = ['happy', 'sad', 'angry', 'neutral', 'fear', 'surprise', 'disgust']
        
    def analyze_emotion_from_base64(self, image_data):
        """
        Fallback emotion analysis using simple image properties
        Returns random emotion with realistic confidence scores
        """
        try:
            # For demo: analyze basic image properties and return weighted random emotion
            
            # Decode image for basic analysis
            import base64
            image_data = image_data.split(',')[1]
            image_bytes = base64.b64decode(image_data)
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise Exception("Could not decode image")
            
            # Simple image analysis
            brightness = np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
            
            # Weight emotions based on simple heuristics
            emotion_weights = {
                'happy': 0.3 if brightness > 120 else 0.1,
                'neutral': 0.4,
                'sad': 0.2 if brightness < 100 else 0.1,
                'angry': 0.1,
                'fear': 0.05,
                'surprise': 0.1,
                'disgust': 0.05
            }
            
            # Normalize weights
            total_weight = sum(emotion_weights.values())
            emotion_weights = {k: v/total_weight for k, v in emotion_weights.items()}
            
            # Select emotion based on weights (without numpy.random.choice)
            import random
            rand_val = random.random()
            cumulative = 0
            dominant_emotion = 'neutral'  # default
            
            for emotion, weight in emotion_weights.items():
                cumulative += weight
                if rand_val <= cumulative:
                    dominant_emotion = emotion
                    break
            
            # Generate realistic confidence scores
            base_confidence = random.uniform(0.6, 0.9)
            emotion_scores = {}
            
            for emotion in self.emotions:
                if emotion == dominant_emotion:
                    emotion_scores[emotion] = base_confidence * 100
                else:
                    emotion_scores[emotion] = random.uniform(0.01, 0.15) * 100
            
            # Normalize to 100%
            total = sum(emotion_scores.values())
            emotion_scores = {k: (v/total) * 100 for k, v in emotion_scores.items()}
            
            logger.info(f"Fallback detector: {dominant_emotion} ({emotion_scores[dominant_emotion]:.1f}%)")
            
            return {
                'dominant_emotion': dominant_emotion,
                'emotion_scores': {k: round(v, 2) for k, v in emotion_scores.items()},
                'success': True,
                'detector': 'Fallback (Image Analysis)',
                'confidence': round(emotion_scores[dominant_emotion], 2),
                'brightness': round(brightness, 1)
            }
            
        except Exception as e:
            logger.error(f"Fallback emotion analysis failed: {e}")
            
            # Ultimate fallback - pure random
            fallback_emotion = random.choice(['happy', 'neutral', 'sad'])
            return {
                'dominant_emotion': fallback_emotion,
                'emotion_scores': {fallback_emotion: 75.0, 'neutral': 25.0},
                'success': False,
                'error': str(e),
                'detector': 'Random Fallback',
                'confidence': 75.0
            }