# Configuration file for emotion-based music recommendation
import os

# Spotify Configuration
SPOTIFY_CONFIG = {
    'username': 'aadish',
    'client_id': '63b8d384874843a7a8fbdd09ca6aea5f',
    'client_secret': '672a3ea80d364ac69cf3114252503ed1',
    'redirect_uri': 'http://google.com/callback/'
}

# Emotion to Playlist Mapping with individual track URLs
EMOTION_PLAYLISTS = {
    'happy': [
        'https://open.spotify.com/playlist/4nd7oGDNgfM0rv28CQw9WQ?si=deeb2095439a415b',
        'https://open.spotify.com/playlist/37i9dQZF1DWTwbZHrJRIgD?si=8fa87fafa3ec4b2f',
        'https://open.spotify.com/playlist/1tTXdi6Bp04Pgmam9bSN7W?si=3e2e3747b4d84b5a',
        'https://open.spotify.com/playlist/0jrlHA5UmxRxJjoykf7qRY?si=ba8fe9417a114d0f'
    ],
    'sad': [
        'https://open.spotify.com/playlist/0VPrITrZqpMpIRGAs33Tmz?si=a914368c42b74810',
        'https://open.spotify.com/playlist/4YOfhHpjPB0tq29NPpDY3F?si=9086ef13bf3c4690',
        'https://open.spotify.com/playlist/1eRXF5lCwXzXArmtULo4Ji?si=41757810089d4e65',
        'https://open.spotify.com/playlist/5qYMFV8EdILwgFbCwyG85Y?si=89691439b2664680'
    ],
    'angry': [
        'https://open.spotify.com/playlist/7pS8tMgJgzQ8XSGpOajOqb?si=1898b4d8d6cb4da3',
        'https://open.spotify.com/playlist/5rPNCmrHpkrfQvbyfFfEib?si=f0258de20d594874',
        'https://open.spotify.com/playlist/0a4Hr64HWlxekayZ8wnWqx?si=74fac1a8928d4c12',
        'https://open.spotify.com/playlist/0YMghmr5hSy2rrkL4BVuHP?si=b2fabd5160b14283'
    ],
    'neutral': [
        'https://open.spotify.com/playlist/7EClwmhqu7mg4JvUI9z5DT?si=3816b85fcb3e4a0a',
        'https://open.spotify.com/playlist/4PFwZ4h1LMAOwdwXqvSYHd?si=de1ebd18b436457b',
        'https://open.spotify.com/playlist/3M1mbdfDqoDRbA46C3PRJi?si=1442a775925f4f24',
        'https://open.spotify.com/playlist/4ftcK3C6QUeMUOMAQpOkDf?si=e6d6dfdcfaf841b3'
    ],
    'fear': [
        'https://open.spotify.com/playlist/4pUX3ojKN2OxXP7I4Lu9ij?si=9e3cadcaa0e94a24',
        'https://open.spotify.com/playlist/5AM4lgcUAw5sokybXj3ny7?si=c399fc779e964346'
    ]
}

# Auto-capture settings
AUTO_CAPTURE_SETTINGS = {
    'enabled': True,
    'interval_seconds': 30,  # Capture every 30 seconds
    'songs_before_recheck': 3,  # Recheck emotion after 3 songs
    'auto_play_random_song': True  # Automatically play random song from playlist
}

# File paths
HAAR_CASCADE_PATH = './haarcascade_frontalface_default.xml'
CAPTURED_IMAGE_PATH = 'saved_img.jpg'
PROCESSED_IMAGE_PATH = 'saved_img-final.jpg'