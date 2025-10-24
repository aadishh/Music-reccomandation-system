from deepface import DeepFace
import cv2
import webbrowser
import spotipy
import random
from time import sleep
import logging
from config import SPOTIFY_CONFIG, EMOTION_PLAYLISTS, HAAR_CASCADE_PATH, CAPTURED_IMAGE_PATH, PROCESSED_IMAGE_PATH

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmotionMusicSystem:
    def __init__(self):
        """Initialize the emotion-based music recommendation system."""
        self.face_cascade = None
        self.spotify_client = None
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
                SPOTIFY_CONFIG['redirect_uri']
            )
            token_dict = oauth_object.get_access_token()
            token = token_dict['access_token']
            self.spotify_client = spotipy.Spotify(auth=token)
            
            # Verify connection
            user_info = self.spotify_client.current_user()
            logger.info(f"Spotify connected for user: {user_info.get('display_name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Spotify: {e}")
            # Continue without Spotify - we'll still open browser links
            self.spotify_client = None
    
    def capture_image(self):
        """Capture image from webcam with face detection."""
        logger.info("Starting image capture...")
        
        webcam = None
        try:
            webcam = cv2.VideoCapture(0)
            if not webcam.isOpened():
                raise Exception("Could not open webcam")
            
            sleep(2)  # Allow camera to warm up
            
            while True:
                try:
                    check, frame = webcam.read()
                    if not check:
                        logger.warning("Failed to read frame from webcam")
                        continue
                    
                    # Detect faces
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3)
                    
                    # Draw rectangles around detected faces
                    for (x, y, w, h) in faces:
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    
                    # Display frame
                    cv2.imshow("Capturing", frame)
                    key = cv2.waitKey(1) & 0xFF
                    
                    if key == ord('s'):
                        if len(faces) == 0:
                            logger.warning("No face detected. Please position your face in the frame and try again.")
                            continue
                        
                        # Save the captured image
                        cv2.imwrite(CAPTURED_IMAGE_PATH, frame)
                        logger.info("Image captured successfully")
                        
                        # Process the image
                        self._process_captured_image()
                        break
                    
                    elif key == ord('q'):
                        logger.info("Capture cancelled by user")
                        return False
                
                except KeyboardInterrupt:
                    logger.info("Capture interrupted by user")
                    return False
                except Exception as e:
                    logger.error(f"Error during capture: {e}")
                    continue
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to capture image: {e}")
            return False
        
        finally:
            if webcam:
                webcam.release()
            cv2.destroyAllWindows()
    
    def _process_captured_image(self):
        """Process the captured image (resize and convert)."""
        try:
            logger.info("Processing image...")
            
            # Read the saved image
            img = cv2.imread(CAPTURED_IMAGE_PATH, cv2.IMREAD_ANYCOLOR)
            if img is None:
                raise Exception("Could not read captured image")
            
            logger.info("Converting RGB image to grayscale...")
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            logger.info("Resizing image to 28x28 scale...")
            resized = cv2.resize(gray, (28, 28))
            
            # Save processed image
            cv2.imwrite(PROCESSED_IMAGE_PATH, resized)
            logger.info("Image processed and saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to process image: {e}")
            raise
    
    def detect_emotion(self):
        """Detect emotion from the captured image."""
        try:
            logger.info("Analyzing emotion...")
            
            # Load the captured image
            img = cv2.imread(CAPTURED_IMAGE_PATH)
            if img is None:
                raise Exception("Could not load captured image for emotion analysis")
            
            # Analyze emotion using DeepFace
            predictions = DeepFace.analyze(img, actions=['emotion'], enforce_detection=False)
            
            # Extract dominant emotion
            if isinstance(predictions, list):
                emotion = predictions[0]['dominant_emotion']
            else:
                emotion = predictions['dominant_emotion']
            
            logger.info(f"Detected emotion: {emotion}")
            return emotion
            
        except Exception as e:
            logger.error(f"Failed to detect emotion: {e}")
            # Return neutral as fallback
            return 'neutral'
    
    def play_music_for_emotion(self, emotion):
        """Open a random playlist based on the detected emotion."""
        try:
            if emotion not in EMOTION_PLAYLISTS:
                logger.warning(f"No playlists found for emotion: {emotion}. Using neutral playlists.")
                emotion = 'neutral'
            
            playlists = EMOTION_PLAYLISTS[emotion]
            selected_playlist = random.choice(playlists)
            
            logger.info(f"Opening playlist for {emotion} emotion: {selected_playlist}")
            webbrowser.open(selected_playlist)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to open playlist: {e}")
            return False
    
    def run(self):
        """Run the complete emotion-based music recommendation system."""
        try:
            logger.info("Starting Emotion-Based Music Recommendation System")
            logger.info("Press 's' to capture image, 'q' to quit")
            
            # Capture image
            if not self.capture_image():
                logger.info("Image capture failed or cancelled")
                return
            
            # Detect emotion
            emotion = self.detect_emotion()
            
            # Play music based on emotion
            if self.play_music_for_emotion(emotion):
                logger.info("Music recommendation completed successfully")
            else:
                logger.error("Failed to open music playlist")
            
        except Exception as e:
            logger.error(f"System error: {e}")
        
        finally:
            logger.info("System shutdown complete")

def main():
    """Main function to run the emotion music system."""
    try:
        system = EmotionMusicSystem()
        system.run()
    except Exception as e:
        logger.error(f"Failed to start system: {e}")

if __name__ == "__main__":
    main()