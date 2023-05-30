# import cv2
# from cv2 import *
# from time import sleep
# key = cv2. waitKey(1)
# webcam = cv2.VideoCapture(0)
# sleep(2)
# while True:

#     try:
#         check, frame = webcam.read()
#         print(check) #prints true as long as the webcam is running
#         print(frame) #prints matrix values of each framecd 
#         cv2.imshow("Capturing", frame)
#         key = cv2.waitKey(1)
#         if key == ord('s'): 
#             cv2.imwrite(filename='saved_img.jpg', img=frame)
#             webcam.release()
#             print("Processing image...")
#             img_ = cv2.imread('saved_img.jpg', cv2.IMREAD_ANYCOLOR)
#             print("Converting RGB image to grayscale...")
#             gray = cv2.cvtColor(img_, cv2.COLOR_BGR2GRAY)
#             print("Converted RGB image to grayscale...")
#             print("Resizing image to 28x28 scale...")
#             img_ = cv2.resize(gray,(28,28))
#             print("Resized...")
#             img_resized = cv2.imwrite(filename='saved_img-final.jpg', img=img_)
#             print("Image saved!")
            
#             break
        
#         elif key == ord('q'):
#             webcam.release()
#             cv2.destroyAllWindows()
#             break
    
#     except(KeyboardInterrupt):
#         print("Turning off camera.")
#         webcam.release()
#         print("Camera off.")
#         print("Program ended.")
#         cv2.destroyAllWindows()
#         break


# play song in spotify
import json
import spotipy
import webbrowser

username = 'aadish'
clientID = '63b8d384874843a7a8fbdd09ca6aea5f'
clientSecret = '672a3ea80d364ac69cf3114252503ed1'
redirect_uri = 'http://google.com/callback/'
oauth_object = spotipy.SpotifyOAuth(clientID, clientSecret, redirect_uri)
token_dict = oauth_object.get_access_token()
token = token_dict['access_token']
spotifyObject = spotipy.Spotify(auth=token)
user_name = spotifyObject.current_user()

# To print the JSON response from
# browser in a readable format.
# optional can be removed
print(json.dumps(user_name, sort_keys=True, indent=4))

while True:
	print("Welcome to the project, " + user_name['display_name'])
	print("0 - Exit the console")
	print("1 - Search for a Song")
	user_input = int(input("Enter Your Choice: "))
	if user_input == 1:
		search_song = input("Enter the song name: ")
		results = spotifyObject.search(search_song, 1, 0, "track")
		songs_dict = results['tracks']
		song_items = songs_dict['items']
		song = song_items[0]['external_urls']['spotify']
		webbrowser.open(song)
		print('Song has opened in your browser.')
	elif user_input == 0:
		print("Good Bye, Have a great day!")
		break
	else:
		print("Please enter valid user-input.")
