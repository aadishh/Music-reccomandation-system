# Emotion-Based Music Recommendation System

An intelligent system that captures your facial emotion through webcam and recommends Spotify playlists based on your current mood.

## Features

- **Real-time Face Detection**: Uses OpenCV Haar cascades for face detection
- **Emotion Analysis**: Leverages DeepFace for accurate emotion recognition
- **Music Recommendation**: Opens curated Spotify playlists based on detected emotions
- **Improved Error Handling**: Robust error handling and logging
- **Modular Design**: Clean, organized code structure

## Supported Emotions

- **Happy**: Upbeat and energetic playlists
- **Sad**: Melancholic and soothing music
- **Angry**: Intense and powerful tracks
- **Neutral**: Balanced and versatile playlists
- **Fear**: Calming and reassuring music

## Installation

1. **Clone or download the project files**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Download Haar cascade file** (if not present):
   ```bash
   wget https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml
   ```

4. **Set up Spotify credentials** in `config.py` or use environment variables

## Usage

### Option 1: Run the Python script
```bash
python emotion_music_system.py
```

### Option 2: Use the Jupyter notebook
Open `main_improved.ipynb` in Jupyter and run the cells

### Option 3: Use original notebook
Your original `main.ipynb` still works as before

## How to Use

1. Run the application
2. Position your face in the camera frame
3. Press 's' to capture and analyze your emotion
4. The system will automatically open a Spotify playlist matching your mood
5. Press 'q' to quit

## Project Structure

```
├── emotion_music_system.py    # Main improved system class
├── config.py                  # Configuration and playlist mappings
├── main_improved.ipynb        # Improved Jupyter notebook
├── main.ipynb                 # Your original notebook (unchanged)
├── requirements.txt           # Python dependencies
├── .env.example              # Environment variables template
└── README.md                 # This file
```

## Improvements Made

- **Better Error Handling**: Graceful handling of camera, file, and network errors
- **Logging**: Comprehensive logging for debugging and monitoring
- **Code Organization**: Separated concerns into classes and modules
- **Configuration Management**: Centralized configuration in `config.py`
- **Resource Management**: Proper cleanup of camera and file resources
- **User Experience**: Better feedback and fallback mechanisms
- **Maintainability**: Modular design for easy updates and extensions

## Dependencies

- `opencv-python`: Computer vision and camera handling
- `deepface`: Facial emotion recognition
- `spotipy`: Spotify Web API integration
- `tensorflow`: Deep learning backend for DeepFace

## Troubleshooting

### Camera Issues
- Ensure no other application is using the camera
- Check camera permissions
- Try different camera indices if default doesn't work

### Face Detection Issues
- Ensure good lighting conditions
- Position face clearly in the frame
- Make sure the Haar cascade file is present

### Spotify Issues
- Verify internet connection
- Check Spotify API credentials
- Ensure redirect URI matches your Spotify app settings

## License

This project is for educational and personal use.