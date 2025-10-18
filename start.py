import time
import os
import pickle
import sys
import random
import requests
import json
import shutil
from itertools import cycle 

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# =========================================================
# --- CONFIGURATION (UPDATE THESE VALUES) ---
# Set the current version of THIS executable
CURRENT_VERSION = 1.0 # <<<<<<<<<<<< UPDATE THIS NUMBER FOR NEW RELEASES

# URL for license verification (calls check_license.php)
LICENSE_SERVER_URL = "https://boulakhbar.com/check_license.php" 
LICENSE_KEY_FILE = 'license.key'

# URL for update check (calls config_update.php)
CONFIG_SERVER_URL = "https://boulakhbar.com/config_update.php" 
# =========================================================

# ---------------------------------------------------------
# --- HELPER SCRIPT CONTENTS (Used for Self-Replacement) ---
# ---------------------------------------------------------

# --- HELPER SCRIPT CONTENT (FOR WINDOWS) ---
HELPER_BATCH_CONTENT = """@echo off
ECHO Running update cleanup...
TIMEOUT /T 2 /NOBREAK >nul

:: Delete the old executable (start.bin)
IF EXIST start.bin (
    DEL start.bin
    ECHO Old executable deleted.
) ELSE (
    ECHO Old executable not found, proceeding.
)

:: Rename the new executable (start_NEW.bin)
IF EXIST start_NEW.bin (
    RENAME start_NEW.bin start.bin
    ECHO New executable renamed to start.bin.
) ELSE (
    ECHO Error: Downloaded file not found. Update failed.
    GOTO END
)

:: Launch the new executable
ECHO Launching new start.bin...
start start.bin

:END
:: Clean up the helper script itself
DEL %0
EXIT
"""

# --- HELPER SCRIPT CONTENT (FOR MACOS/LINUX) ---
HELPER_SHELL_CONTENT = """#!/bin/bash
# Helper script to replace the old executable
# Use 'sleep' to ensure the main script has fully exited and released the file lock
sleep 2

OLD_EXE="start.bin"
NEW_EXE="start_NEW.bin"
HELPER_SCRIPT="$0"

echo "Running update cleanup..."

# Delete the old executable
if [ -f "$OLD_EXE" ]; then
    rm "$OLD_EXE"
    echo "Old executable deleted."
else
    echo "Old executable not found, proceeding."
fi

# Rename the new executable
if [ -f "$NEW_EXE" ]; then
    mv "$NEW_EXE" "$OLD_EXE"
    echo "New executable renamed to start.bin."
else
    echo "Error: Downloaded file not found. Update failed."
    exit 1
fi

# Launch the new executable
echo "Launching new start.bin..."
chmod +x "$OLD_EXE"
./"$OLD_EXE" &

# Clean up the helper script itself
rm "$HELPER_SCRIPT"

exit 0
"""

# ---------------------------------------------------------
# --- SECURITY AND UPDATE FUNCTIONS ---
# ---------------------------------------------------------

def check_subscription():
    """
    Performs the critical license check against the remote server.
    If verification fails, the script terminates immediately.
    """
    try:
        # 1. Read the license key from the distributed file
        with open(LICENSE_KEY_FILE, 'r') as f:
            license_key = f.read().strip()
    except FileNotFoundError:
        print("\nFATAL ERROR: license.key file not found. Place it in the script folder.")
        sys.exit(1)

    payload = {'key': license_key}
    
    try:
        print("\n[SECURITY CHECK] Verifying subscription with license server...")
        response = requests.post(LICENSE_SERVER_URL, json=payload, timeout=15)
        response.raise_for_status() 
        
        try:
            data = response.json()
        except json.JSONDecodeError:
            print("\n[DENIAL] Invalid server response format. Exiting.")
            sys.exit(1)
            
        if data.get('status') == 'active':
            print(f"[STATUS] Verification successful. Subscription is ACTIVE.")
            time.sleep(1 + random.uniform(0.1, 0.5)) 
            return True
        
        elif data.get('status') == 'denied':
            print(f"\n[LICENSE DENIED] {data.get('message', 'Subscription check failed.')}")
            sys.exit(1)

        else:
            print(f"\n[DENIAL] Unexpected response from server. Exiting. Response: {data}")
            sys.exit(1)

    except requests.exceptions.HTTPError as e:
        print(f"\n[LICENSE FAILURE] Access denied (Code: {e.response.status_code}). Please check your payment status.")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"\n[CONNECTION ERROR] Could not connect to the license server. Check internet connection.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[CRITICAL ERROR] An unknown error occurred during license check: {e}")
        sys.exit(1)


def handle_update():
    """Checks server for required version and handles the cross-platform self-replacement update."""
    global CURRENT_VERSION
    current_exe_path = os.path.abspath(sys.argv[0])
    new_exe_temp_name = "start_NEW.bin" 

    # Determine helper script type based on OS
    if os.name == 'nt':
        # Windows
        helper_script_name = "update_helper.bat"
        helper_content = HELPER_BATCH_CONTENT
    else:
        # macOS, Linux, etc. (POSIX systems)
        helper_script_name = "update_helper.sh"
        helper_content = HELPER_SHELL_CONTENT
    
    try:
        print("\n[UPDATE CHECK] Checking for required maintenance and updates...")
        response = requests.get(CONFIG_SERVER_URL, timeout=10)
        response.raise_for_status()
        config = response.json()
        
        required_version = config.get('minimum_required_version', CURRENT_VERSION)
        download_url = config.get('update_download_url')
        
        # Check 1: Global Kill Switch
        if not config.get('global_active', True):
            print(f"\n[MAINTENANCE] Tool is temporarily offline. {config.get('maintenance_message', 'Check back later.')}")
            sys.exit(1)

        # Check 2: Version Check
        if CURRENT_VERSION < required_version:
            print("\n=======================================================")
            print(f"       [CRITICAL UPDATE REQUIRED] (v{required_version})")
            print("=======================================================")
            
            # 1. Download the new binary
            print(f"Downloading new version from: {download_url}")
            new_binary_response = requests.get(download_url, stream=True)
            new_binary_response.raise_for_status()
            
            # 2. Save it with a temporary name
            with open(new_exe_temp_name, 'wb') as f:
                for chunk in new_binary_response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # 3. Create the OS-specific helper script
            with open(helper_script_name, 'w') as f:
                f.write(helper_content)
            
            # 4. Make the helper script executable (essential for macOS/Linux)
            if os.name != 'nt':
                os.chmod(helper_script_name, 0o755) 

            # 5. Launch the helper script and IMMEDIATELY EXIT the old program
            print("\n✅ Download complete. Starting automatic replacement...")
            
            if os.name == 'nt':
                # Windows: Use 'start' to run the batch script in a new process
                os.system(f"start {helper_script_name}")
            else:
                # macOS/Linux: Execute the shell script in the background
                os.system(f"chmod +x {helper_script_name} && ./{helper_script_name} &") 

            print("\nTerminating old version for update. The new version will start automatically.")
            sys.exit(0) # IMPORTANT: Exit to release the file lock

        print("[STATUS] Software version is current.")
        return True

    except requests.exceptions.RequestException as e:
        print(f"\n[WARNING] Could not connect to update server. Proceeding without version check.")
        return True
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Update check failed. Error: {e}")
        return True

# ---------------------------------------------------------
# --- YOUTUBE FUNCTIONS (YOUR ORIGINAL CODE) ---
# ---------------------------------------------------------

def get_authenticated_service(client_secret_file, credentials_file):
    SCOPES = ['https://www.googleapis.com/auth/youtube']
    API_SERVICE_NAME = 'youtube'
    API_VERSION = 'v3'
    credentials = None

    if os.path.exists(credentials_file):
        with open(credentials_file, 'rb') as token:
            credentials = pickle.load(token)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secret_file, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open(credentials_file, 'wb') as token:
            pickle.dump(credentials, token)
            print(f"Credentials renewed and saved to {credentials_file}")

    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

def initialize_upload(youtube, file, title, description, category, privacy, tags_list):
    
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags_list, 
            'categoryId': category
        },
        'status': {
            'privacyStatus': privacy,
            'selfDeclaredMadeForKids': False
        }
    }

    print(f"Uploading video '{os.path.basename(file)}' with title '{title}'...")
    media = MediaFileUpload(file, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")
    
    print(f"Upload complete! Video ID: {response.get('id')}")
    return response.get('id')

def set_thumbnail(youtube, video_id, thumbnail_file):
    print(f"Setting thumbnail '{os.path.basename(thumbnail_file)}' for video ID {video_id}...")
    try:
        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_file)
        )
        request.execute()
        print("Thumbnail set successfully.")
    except Exception as e:
        print(f"An error occurred while setting the thumbnail: {e}")

# ---------------------------------------------------------
# --- MAIN EXECUTION ---
# ---------------------------------------------------------

if __name__ == '__main__':
    
    # === CRITICAL SECURITY CHECKS (Must be run first!) ===
    check_subscription() 
    handle_update() 
    # =====================================================
    
    GREEN = '\033[92m'
    RESET = '\033[0m'
    
    signature = """
============================================
    Welcome to YouTube Videos Uploader
              ----------------
    This tool made by @RealAbdeljalil
============================================
"""
    
    os.system('cls' if os.name == 'nt' else 'clear') 
    print(GREEN + signature + RESET)
    time.sleep(1) 
    
    
    CHANNEL_DIR = 'youtube-channels'
    CLIENT_SECRET_FILE = 'client_secret.json'
    VIDEO_DIR = 'youtube-video'
    
    DESCRIPTION_DIR = 'description'
    THUMBNAIL_DIR = 'thumbnail-image'
    TITLE_FILE_PATH = os.path.join('video-title', 'title.txt')
    TAGS_FILE_PATH = os.path.join('video-tags', 'tags.txt')

    
    try:
        token_filenames = [f for f in os.listdir(CHANNEL_DIR) if f.endswith('.pkl')]
        if not token_filenames:
            print(f"Error: No channel token files (.pkl) found in the '{CHANNEL_DIR}' folder.")
            sys.exit()
        channel_tokens = [os.path.join(CHANNEL_DIR, f) for f in token_filenames]
    except FileNotFoundError:
        print(f"Error: The '{CHANNEL_DIR}' folder was not found.")
        sys.exit()

    
    try:
        video_files = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
        if not video_files:
            print(f"Error: No video files found in the '{VIDEO_DIR}' folder.")
            sys.exit()
        video_paths = [os.path.join(VIDEO_DIR, f) for f in video_files]
    except FileNotFoundError:
        print(f"Error: The '{VIDEO_DIR}' folder was not found.")
        sys.exit()
        
    
    description_list = []
    try:
        
        description_filenames = [f for f in os.listdir(DESCRIPTION_DIR) if f.lower().endswith('.txt')]
        
        if description_filenames:
            for filename in description_filenames:
                file_path = os.path.join(DESCRIPTION_DIR, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    description = f.read().strip()
                    if description:
                        description_list.append(description)
            
            if description_list:
                print(f"Successfully loaded {len(description_list)} unique description(s) from '{DESCRIPTION_DIR}'.")
            else:
                print(f"Warning: Description files found but all were empty. Using an empty description for all videos.")

        else:
            print(f"Info: No description files (.txt) found in '{DESCRIPTION_DIR}'. Using an empty description for all videos.")
            
    except FileNotFoundError:
        print(f"Info: The '{DESCRIPTION_DIR}' folder was not found. Using an empty description for all videos.")
        
    
    if description_list:
        description_cycler = cycle(description_list)
    else:
        
        description_cycler = cycle([""]) 
    


    
    thumbnail_paths = []
    try:
        image_files = [f for f in os.listdir(THUMBNAIL_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if image_files:
            thumbnail_paths = [os.path.join(THUMBNAIL_DIR, f) for f in image_files]
            print(f"Found {len(thumbnail_paths)} thumbnail(s) in '{THUMBNAIL_DIR}'.")
    except FileNotFoundError:
        print(f"Info: Thumbnail folder '{THUMBNAIL_DIR}' not found. Skipping thumbnails.")


    
    video_titles = []
    try:
        with open(TITLE_FILE_PATH, 'r', encoding='utf-8') as f:
            video_titles = [line.strip() for line in f if line.strip()]
        if video_titles:
            print(f"Successfully loaded {len(video_titles)} custom title(s) from '{TITLE_FILE_PATH}'.")
            title_cycler = cycle(video_titles)
        else:
            print(f"Warning: Title file is empty. Using video filenames as titles.")
    except FileNotFoundError:
        print(f"Info: Title file not found. Using video filenames as titles.")
        
    
    tags_list = None
    try:
        with open(TAGS_FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                tags_list = [tag.strip() for tag in content.split(',') if tag.strip()]
                print(f"Successfully loaded {len(tags_list)} tag(s) from '{TAGS_FILE_PATH}'.")
            else:
                print(f"Info: Tags file found but is empty. Skipping tags.")
    except FileNotFoundError:
        print(f"Info: Tags file not found. Skipping tags.")

    print(f"\nFound {len(video_files)} video(s) to upload to {len(channel_tokens)} channel(s).")
    
    
    video_cycler = cycle(video_paths)
    if 'title_cycler' not in locals(): 
        title_cycler = None
    
    
    for i, token_file in enumerate(channel_tokens):
        
        
        if len(video_files) == 1:
            video_file_path = video_paths[0]
            video_filename = os.path.basename(video_file_path)
        else:
            video_file_path = next(video_cycler)
            video_filename = os.path.basename(video_file_path)

        
        if title_cycler:
            video_title = next(title_cycler)
        else:
            video_title = os.path.splitext(video_filename)[0]
            
        
        current_description = next(description_cycler)

        print(f"\n===== Processing Channel {i+1}/{len(channel_tokens)}: {os.path.basename(token_file)} =====")
        print(f"    -> Assigned Video: {video_filename} (Title: {video_title})")
        
        print(f"    -> Description Length: {len(current_description)} characters")


        try:
            youtube_service = get_authenticated_service(CLIENT_SECRET_FILE, token_file)
            
            
            video_id = initialize_upload(
                youtube=youtube_service,
                file=video_file_path,
                title=video_title,
                description=current_description, 
                category='22',
                privacy='public',
                tags_list=tags_list 
            )


            
            if video_id and thumbnail_paths:
                if len(thumbnail_paths) == 1:
                    chosen_thumbnail = thumbnail_paths[0]
                else:
                    chosen_thumbnail = random.choice(thumbnail_paths)
                
                set_thumbnail(youtube_service, video_id, chosen_thumbnail)


        except Exception as e:
            print(f"An error occurred while processing for {token_file}: {e}")
    
    print("\n✅ All tasks complete!")
