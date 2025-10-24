from deepface import DeepFace
import cv2
import webbrowser
import spotipy
import random
import time
import threading
import logging
from datetime import datetime, timedelta
from config import SPOTIFY_CONFIG, EMOTION_PLAYLISTS, HAAR_CASCADE_PATH, CAPTURED_IMAGE_PATH, PROCESSED_IMAGE_PATH

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ContinuousEmotionMusicSystem:
    def __init__(self, songs_before_recheck=3, auto_capture_interval=300):
        """
        Initialize continuous emotion-based music system.
        
        Args:
            songs_before_recheck (int): Number of songs to play before rechecking emotion
            auto_capture_interval (int): Seconds between automatic emotion checks
        """
        self.face_cascade = None
        self.spotify_client = None
        self.songs_played = 0
        self.songs_before_recheck = songs_before_recheck
        self.auto_capture_interval = auto_capture_interval
        self.current_emotion = None
        self.last_check_time = None
        self.is_running = False
        self.monitoring_thread = None
        
        self._initialize_face_detection()
        self._initialize_spotify()
    
    def _initialize_face_detection(self):
        """Initialize face detection cascade."""
        try:
            self.face_cascade = cv2.CascadeClassifier(HAAR_CASCADE_PATH)
            if self.face_cascade.empty():
                raise Exception("Could not load face cascade classifier")
            logger.info("Face detection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize face detection: {e}")
            raise
    
    def _initialize_spotify(self):
        """Initialize Spotify client."""
        try:
            oauth_object = spotipy.SpotifyOAuth(
                SPOTIFY_CONFIG['client_id'],
                SPOTIFY_CONFIG['client_secret'],
                SPOTIFY_CONFIG['redirect_uri'],
                scope="user-read-currently-playing user-read-playback-state"
            )
            token_dict = oauth_object.get_access_token()
            token = token_dict['access_token']
            self.spotify_client = spotipy.Spotify(auth=token)
            
            # Verify connection
            user_info = self.spotify_client.current_user()
            logger.info(f"Spotify connected for user: {user_info.get('display_name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Spotify: {e}")
            self.spotify_client = None
    
    def capture_image_auto(self):
        """Automatically capture image without user interaction."""
        logger.info("Auto-capturing image for emotion analysis...")
        
        webcam = None
        try:
            webcam = cv2.VideoCapture(0)
            if not webcam.isOpened():
                logger.error("Could not open webcam for auto-capture")
                return False
            
            time.sleep(1)  # Allow camera to warm up
            
            # Try to capture a good frame with face
            for attempt in range(10):  # Try 10 times
                check, frame = webcam.read()
                if not check:
                    continue
                
                # Detect faces
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3)
                
                if len(faces) > 0:
                    # Save the captured image
                    cv2.imwrite(CAPTURED_IMAGE_PATH, frame)
                    logger.info("Auto-capture successful - face detected")
                    self._process_captured_image()
                    return True
                
                time.sleep(0.5)  # Wait before next attempt
            
            logger.warning("Auto-capture failed - no face detected after 10 attempts")
            return False
            
        except Exception as e:
            logger.error(f"Auto-capture failed: {e}")
            return False
        
        finally:
            if webcam:
                webcam.release()
    
    def capture_image_manual(self):
        """Manual image capture with user interaction."""
        logger.info("Starting manual image capture...")
        
        webcam = None
        try:
            webcam = cv2.VideoCapture(0)
            if not webcam.isOpened():
                raise Exception("Could not open webcam")
            
            time.sleep(2)
            
            while True:
                try:
                    check, frame = webcam.read()
                    if not check:
                        continue
                    
                    # Detect faces
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3)
                    
                    # Draw rectangles around detected faces
                    for (x, y, w, h) in faces:
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    
                    # Add instructions to frame
                    cv2.putText(frame, "Press 's' to capture, 'q' to quit", 
                               (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    cv2.imshow("Emotion Capture", frame)
                    key = cv2.waitKey(1) & 0xFF
                    
                    if key == ord('s'):
                        if len(faces) == 0:
                            logger.warning("No face detected. Please position your face in the frame.")
                            continue
                        
                        cv2.imwrite(CAPTURED_IMAGE_PATH, frame)
                        logger.info("Manual capture successful")
                        self._process_captured_image()
                        break
                    
                    elif key == ord('q'):
                        logger.info("Manual capture cancelled")
                        return False
                
                except KeyboardInterrupt:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Manual capture failed: {e}")
            return False
        
        finally:
            if webcam:
                webcam.release()
            cv2.destroyAllWindows()
    
    def _process_captured_image(self):
        """Process the captured image."""
        try:
            img = cv2.imread(CAPTURED_IMAGE_PATH, cv2.IMREAD_ANYCOLOR)
            if img is None:
                raise Exception("Could not read captured image")
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (28, 28))
            cv2.imwrite(PROCESSED_IMAGE_PATH, resized)
            
        except Exception as e:
            logger.error(f"Failed to process image: {e}")
            raise
    
    def detect_emotion(self):
        """Detect emotion from captured image."""
        try:
            img = cv2.imread(CAPTURED_IMAGE_PATH)
            if img is None:
                raise Exception("Could not load image for emotion analysis")
            
            predictions = DeepFace.analyze(img, actions=['emotion'], enforce_detection=False)
            
            if isinstance(predictions, list):
                emotion = predictions[0]['dominant_emotion']
            else:
                emotion = predictions['dominant_emotion']
            
            logger.info(f"Detected emotion: {emotion}")
            return emotion
            
        except Exception as e:
            logger.error(f"Emotion detection failed: {e}")
            return 'neutral'
    
    def get_current_playback(self):
        """Get current Spotify playback information."""
        if not self.spotify_client:
            return None
        
        try:
            current = self.spotify_client.current_playback()
            return current
        except Exception as e:
            logger.error(f"Failed to get playback info: {e}")
            return None
    
    def is_music_playing(self):
        """Check if music is currently playing."""
        playback = self.get_current_playback()
        if playback and playback.get('is_playing'):
            return True
        return False
    
    def get_track_duration_remaining(self):
        """Get remaining time for current track in seconds."""
        playback = self.get_current_playback()
        if not playback or not playback.get('item'):
            return 0
        
        duration_ms = playback['item']['duration_ms']
        progress_ms = playback.get('progress_ms', 0)
        remaining_ms = duration_ms - progress_ms
        
        return max(0, remaining_ms / 1000)  # Convert to seconds
    
    def play_music_for_emotion(self, emotion):
        """Play music based on emotion and increment counter."""
        try:
            if emotion not in EMOTION_PLAYLISTS:
                emotion = 'neutral'
            
            playlists = EMOTION_PLAYLISTS[emotion]
            selected_playlist = random.choice(playlists)
            
            logger.info(f"Opening playlist for {emotion} emotion")
            webbrowser.open(selected_playlist)
            
            self.songs_played += 1
            self.current_emotion = emotion
            self.last_check_time = datetime.now()
            
            logger.info(f"Songs played since last emotion check: {self.songs_played}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to play music: {e}")
            return False
    
    def should_recheck_emotion(self):
        """Determine if emotion should be rechecked."""
        # Check by song count
        if self.songs_played >= self.songs_before_recheck:
            return True
        
        # Check by time interval
        if self.last_check_time:
            time_since_check = datetime.now() - self.last_check_time
            if time_since_check.total_seconds() >= self.auto_capture_interval:
                return True
        
        return False
    
    def monitor_playback(self):
        """Monitor Spotify playback and trigger emotion checks."""
        logger.info("Starting playback monitoring...")
        
        while self.is_running:
            try:
                if not self.is_music_playing():
                    # Music stopped, check if we should recheck emotion
                    if self.should_recheck_emotion():
                        logger.info("Music ended and recheck criteria met - analyzing emotion...")
                        
                        # Auto-capture and analyze emotion
                        if self.capture_image_auto():
                            new_emotion = self.detect_emotion()
                            
                            if new_emotion != self.current_emotion:
                                logger.info(f"Emotion changed from {self.current_emotion} to {new_emotion}")
                            
                            # Play music for the detected emotion
                            self.play_music_for_emotion(new_emotion)
                            self.songs_played = 0  # Reset counter
                        else:
                            logger.warning("Auto-capture failed, using previous emotion")
                            if self.current_emotion:
                                self.play_music_for_emotion(self.current_emotion)
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                time.sleep(30)  # Wait longer on error
    
    def start_continuous_mode(self):
        """Start continuous emotion monitoring."""
        logger.info("Starting continuous emotion monitoring mode...")
        
        # Initial emotion detection
        logger.info("Performing initial emotion detection...")
        if self.capture_image_manual():
            emotion = self.detect_emotion()
            self.play_music_for_emotion(emotion)
            self.songs_played = 0
        else:
            logger.error("Initial emotion detection failed")
            return
        
        # Start monitoring thread
        self.is_running = True
        self.monitoring_thread = threading.Thread(target=self.monitor_playback, daemon=True)
        self.monitoring_thread.start()
        
        logger.info(f"Continuous monitoring started:")
        logger.info(f"- Will recheck emotion every {self.songs_before_recheck} songs")
        logger.info(f"- Or every {self.auto_capture_interval} seconds")
        logger.info("Press Ctrl+C to stop")
        
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_continuous_mode()
    
    def stop_continuous_mode(self):
        """Stop continuous monitoring."""
        logger.info("Stopping continuous monitoring...")
        self.is_running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("Continuous monitoring stopped")
    
    def run_single_detection(self):
        """Run single emotion detection (original functionality)."""
        logger.info("Running single emotion detection...")
        
        if self.capture_image_manual():
            emotion = self.detect_emotion()
            self.play_music_for_emotion(emotion)
            logger.info("Single detection completed")
        else:
            logger.error("Single detection failed")

def main():
    """Main function with user options."""
    print("Emotion-Based Music Recommendation System")
    print("=========================================")
    print("1. Single Detection (Original Mode)")
    print("2. Continuous Monitoring Mode")
    print("3. Configure Settings")
    
    try:
        choice = input("\nSelect mode (1-3): ").strip()
        
        if choice == "1":
            system = ContinuousEmotionMusicSystem()
            system.run_single_detection()
            
        elif choice == "2":
            # Get user preferences
            try:
                songs_count = int(input("Songs before emotion recheck (default 3): ") or "3")
                time_interval = int(input("Time interval for recheck in seconds (default 300): ") or "300")
            except ValueError:
                songs_count, time_interval = 3, 300
            
            system = ContinuousEmotionMusicSystem(songs_count, time_interval)
            system.start_continuous_mode()
            
        elif choice == "3":
            print("\nCurrent Settings:")
            print("- Default songs before recheck: 3")
            print("- Default time interval: 300 seconds (5 minutes)")
            print("- Modify these in the main() function or when starting continuous mode")
            
        else:
            print("Invalid choice")
            
    except Exception as e:
        logger.error(f"Application error: {e}")

if __name__ == "__main__":
    main()