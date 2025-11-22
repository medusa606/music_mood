'''
App Name: Smart Read Companion
Description: This app will provide the perfect cinematic score of music to your book reading experience

'''

# Login to account

import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json

import os # importing os module for environment variables
from dotenv import load_dotenv, dotenv_values # importing necessary functions from dotenv library

# loading variables from .env file
load_dotenv()

# scope = "user-library-read"
scope = "playlist-read-private"
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = "https://127.0.0.1:1234"

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=SPOTIFY_CLIENT_ID,
                                               client_secret=SPOTIFY_CLIENT_SECRET,
                                               redirect_uri=SPOTIFY_REDIRECT_URI,
                                               scope="user-library-read"))

results = sp.current_user_saved_tracks()
for idx, item in enumerate(results['items']):
    track = item['track']
    # print(idx, track['artists'][0]['name'], " – ", track['name'])

# Find my playlist
playlist_name = "Reading Soundscape"
playlist_id = "03zQ7dGtiuYH1GqtG9rXAt"
output_file = "reading_soundscape_data.json"


all_items = []
results = sp.playlist_tracks(playlist_id, limit=100)
all_items.extend(results["items"])

while results["next"]:
    results = sp.next(results)
    all_items.extend(results["items"])

print(f"Fetched {len(all_items)} tracks.")

data = {
    "playlist_id": playlist_id,
    "track_count": len(all_items),
    "tracks": all_items
}

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)

print(f"Saved playlist data to {output_file}")
# get each track name and ID

# package ready to add to db