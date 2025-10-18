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


CURRENT_VERSION = 1.0 


LICENSE_SERVER_URL = "https://boulakhbar.com/check_license.php" 
LICENSE_KEY_FILE = 'license.key'


CONFIG_SERVER_URL = "https://boulakhbar.com/config_update.php" 


PROXIES_FILE = os.path.join('proxies-list', 'proxies.txt')
# --------------------


AVAILABLE_PROXIES = [] 

USE_PROXIES_FLAG = False 



def parse_proxy_line(line):
    """Parses a proxy string into the requests library format."""
    line = line.strip()
    if line.startswith('#') or not line:
        return None
        

    if '@' in line:

        return {'http': f"http://{line}", 'https': f"http://{line}"}
    

    if ':' in line:
        return {'http': f"http://{line}", 'https': f"http://{line}"}
        
    return None

def load_proxies():
    """Loads proxies from file, filtering out completed ones (marked with ✅)."""
    global AVAILABLE_PROXIES
    global USE_PROXIES_FLAG

    if not os.path.exists(PROXIES_FILE):
        print(f"\n[PROXY INFO] Proxy file not found at '{PROXIES_FILE}'. Skipping proxy use.")
        USE_PROXIES_FLAG = False
        return []

    try:
        with open(PROXIES_FILE, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"\n[PROXY ERROR] Could not read '{PROXIES_FILE}'. Error: {e}")
        USE_PROXIES_FLAG = False
        return []

    available_lines = []
    
    for line in lines:
        if line.strip().endswith('✅'):

            continue
        
        parsed = parse_proxy_line(line)
        if parsed:
            AVAILABLE_PROXIES.append({
                'raw': line.strip(), 
                'parsed': parsed
            })
            available_lines.append(line)
    
    if not AVAILABLE_PROXIES:
        print(f"\n[PROXY INFO] Proxy file found, but no unused proxies available. Continuing without proxies.")
        USE_PROXIES_FLAG = False
        return []
        
    print(f"\n[PROXY STATUS] {len(AVAILABLE_PROXIES)} unused proxies loaded.")
    USE_PROXIES_FLAG = True
    return AVAILABLE_PROXIES

def mark_proxy_as_used(raw_proxy_line):
    """Writes the '✅' mark next to the successfully used proxy."""
    try:
        with open(PROXIES_FILE, 'r') as f:
            lines = f.readlines()
        
        with open(PROXIES_FILE, 'w') as f:
            for line in lines:

                if line.strip() == raw_proxy_line:
                    f.write(f"{line.strip()} ✅\n")
                    print(f"[PROXY SUCCESS] Marked proxy: {raw_proxy_line} as used.")
                elif line.strip() == f"{raw_proxy_line} ✅":
                   
                    f.write(line)
                else:
                    f.write(line)
    except Exception as e:
        print(f"[PROXY WARNING] Failed to mark proxy as used in file: {e}")


HELPER_BATCH_CONTENT = """@echo off
ECHO Running update cleanup...
TIMEOUT /T 2 /NOBREAK >nul

:: Define filenames
SET OLD_EXE=start.bin
SET NEW_EXE=start_NEW.bin
SET HELPER_SCRIPT=%%0

:: Delete the old executable (start.bin)
IF EXIST %OLD_EXE% (
    DEL %OLD_EXE%
    ECHO Old executable deleted.
) ELSE (
    ECHO Old executable not found, proceeding.
)

:: Rename the new executable (start_NEW.bin)
IF EXIST %NEW_EXE% (
    RENAME %NEW_EXE% %OLD_EXE%
    ECHO New executable renamed to start.bin.
) ELSE (
    ECHO Error: Downloaded file not found. Update failed.
    GOTO END
)

:: Launch the new executable
ECHO Launching new start.bin...
start %OLD_EXE%

:END
:: Clean up the helper script itself
DEL %HELPER_SCRIPT%
EXIT
"""

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




def check_subscription(proxies=None):
    """
    Performs the critical license check against the remote server.
    Accepts an optional 'proxies' argument.
    """
    try:

        with open(LICENSE_KEY_FILE, 'r') as f:
            license_key = f.read().strip()
    except FileNotFoundError:
        print("\nFATAL ERROR: license.key file not found. Place it in the script folder.")
        sys.exit(1)

    payload = {'key': license_key}
    
    try:
        print("\n[SECURITY CHECK] Verifying subscription with license server...")
        

        response = requests.post(LICENSE_SERVER_URL, json=payload, proxies=proxies, timeout=15)
        response.raise_for_status() 
        
        try:
            data = response.json()
        except json.JSONDecodeError:
            print("\n[DENIAL] Invalid server response format. Exiting.")
            sys.exit(1)
            
        if data.get('status') == 'active':
            print(f"[STATUS] Verification successful. Subscription is ACTIVE.")
            if 'message' in data:
                print(f"[INFO] {data['message']}")
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

        error_message = f"Could not connect to the license server (Proxy: {proxies.get('http') if proxies else 'None'}). Check connection or proxy settings."
        
        if proxies:
            print(f"\n[PROXY ERROR] {error_message}")
            return False 
        else:
            print(f"\n[CONNECTION ERROR] {error_message}")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n[CRITICAL ERROR] An unknown error occurred during license check: {e}")
        sys.exit(1)


def handle_update(proxies=None):
    """Checks server for required version and handles the cross-platform self-replacement update."""
    global CURRENT_VERSION
    new_exe_temp_name = "start_NEW.bin" 
    

    if os.name == 'nt':
        os_key = 'Windows'
        helper_script_name = "update_helper.bat"
        helper_content = HELPER_BATCH_CONTENT
    else:
        os_key = 'Mac'
        helper_script_name = "update_helper.sh"
        helper_content = HELPER_SHELL_CONTENT
    
    try:
        print("\n[UPDATE CHECK] Checking for required maintenance and updates...")
   
        response = requests.get(CONFIG_SERVER_URL, proxies=proxies, timeout=10)
        response.raise_for_status()
        config = response.json()
        
        required_version = config.get('minimum_required_version', CURRENT_VERSION)
        
        download_urls = config.get('download_urls', {}) 
        download_url = download_urls.get(os_key)

   
        if not config.get('global_active', True):
            print(f"\n[MAINTENANCE] Tool is temporarily offline. {config.get('maintenance_message', 'Check back later.')}")
            sys.exit(1)

        # Check 2: Version Check
        if CURRENT_VERSION < required_version:
            print("\n=======================================================")
            print(f"       [CRITICAL UPDATE REQUIRED] (v{required_version})")
            print("=======================================================")
            
            if not download_url:
                print(f"\n[ERROR] Update server failed to provide a download link for {os_key}. Cannot update.")
                sys.exit(1) 


            print(f"Downloading new version from: {download_url}")

            new_binary_response = requests.get(download_url, stream=True, proxies=proxies)
            new_binary_response.raise_for_status()
            

            with open(new_exe_temp_name, 'wb') as f:
                for chunk in new_binary_response.iter_content(chunk_size=8192):
                    f.write(chunk)


            with open(helper_script_name, 'w') as f:
                f.write(helper_content)
            

            if os.name != 'nt':
                os.chmod(helper_script_name, 0o755) 


            print("\n✅ Download complete. Starting automatic replacement...")
            
            if os.name == 'nt':
                os.system(f"start {helper_script_name}")
            else:
                os.system(f"chmod +x {helper_script_name} && ./{helper_script_name} &") 

            print("\nTerminating old version for update. The new version will start automatically.")
            sys.exit(0)

        print("[STATUS] Software version is current.")
        return True

    except requests.exceptions.RequestException as e:
        error_message = f"Could not connect to update server (Proxy: {proxies.get('http') if proxies else 'None'}). Proceeding without version check."
        
        if proxies:
            print(f"\n[PROXY WARNING] {error_message}")
            return False 
        else:
            print(f"\n[WARNING] {error_message}")
            return True 
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Update check failed. Error: {e}")
        return True 



def get_authenticated_service(client_secret_file, credentials_file, proxies=None):
    SCOPES = ['https://www.googleapis.com/auth/youtube']
    API_SERVICE_NAME = 'youtube'
    API_VERSION = 'v3'
    credentials = None
    

    http_proxy = proxies['http'] if proxies else None
    

    
    if os.path.exists(credentials_file):
        with open(credentials_file, 'rb') as token:
            credentials = pickle.load(token)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:

            credentials.refresh(Request(proxies=proxies))
        else:
            
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secret_file, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open(credentials_file, 'wb') as token:
            pickle.dump(credentials, token)
            print(f"Credentials renewed and saved to {credentials_file}")
    
 
    http_request = Request(proxies=proxies)

    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials, request=http_request)

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



if __name__ == '__main__':


    load_proxies() 
    
    initial_proxy = AVAILABLE_PROXIES[0]['parsed'] if USE_PROXIES_FLAG else None
    

    if not check_subscription(proxies=initial_proxy):
    
        print("\n[PROXY FAILED] The initial connection/proxy test failed.")
        while True:
            response = input("Do you want to continue normal uploading without proxies? (Yes/No): ").lower().strip()
            if response in ['yes', 'y']:
                USE_PROXIES_FLAG = False
                print("[CONTINUING] Disabling proxy use and continuing with system connection.")

                if not check_subscription(proxies=None):
                    print("\nFATAL ERROR: Cannot reach license server even without proxies. Exiting.")
                    sys.exit(1)
                break
            elif response in ['no', 'n']:
                print("[STOPPING] Tool stopped as requested.")
                sys.exit(1)
            else:
                print("Invalid input. Please type 'Yes' or 'No'.")


    handle_update(proxies=initial_proxy if USE_PROXIES_FLAG else None) 



    GREEN = '\033[92m'
    RESET = '\033[0m'
    
    signature = """
=================================================
       Welcome to YouTube Videos Uploader
              ----------------
  For any help, Contact us on Telegram @Lmaroky
=================================================
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
    except: pass
    if description_list:
        description_cycler = cycle(description_list)
    else:
        description_cycler = cycle([""]) 
    

    thumbnail_paths = []
    try:
        image_files = [f for f in os.listdir(THUMBNAIL_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if image_files:
            thumbnail_paths = [os.path.join(THUMBNAIL_DIR, f) for f in image_files]
    except: pass


    video_titles = []
    try:
        with open(TITLE_FILE_PATH, 'r', encoding='utf-8') as f:
            video_titles = [line.strip() for line in f if line.strip()]
        if video_titles:
            title_cycler = cycle(video_titles)
        else:
            title_cycler = None
    except: 
        title_cycler = None


    tags_list = None
    try:
        with open(TAGS_FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                tags_list = [tag.strip() for tag in content.split(',') if tag.strip()]
    except: pass

    print(f"\nFound {len(video_files)} video(s) to upload to {len(channel_tokens)} channel(s).")
    
    
    video_cycler = cycle(video_paths)
    

    proxy_cycler = cycle(AVAILABLE_PROXIES) if USE_PROXIES_FLAG and AVAILABLE_PROXIES else None
    
    for i, token_file in enumerate(channel_tokens):
        
        current_proxy_data = None
        current_proxies_parsed = None

        if proxy_cycler:
            try:

                current_proxy_data = next(proxy_cycler)
                current_proxies_parsed = current_proxy_data['parsed']
                raw_proxy_line = current_proxy_data['raw']
                print(f"\n[PROXY USE] Assigning proxy for Channel {i+1}: {raw_proxy_line}")
            except StopIteration:
                # All proxies used up, switch off proxy mode
                print("\n[PROXY INFO] All proxies have been used. Continuing without proxies.")
                proxy_cycler = None # Stop cycling
                current_proxies_parsed = None
                raw_proxy_line = None

        

        video_file_path = next(video_cycler) if len(video_paths) > 1 else video_paths[0]
        video_filename = os.path.basename(video_file_path)
        
        video_title = next(title_cycler) if title_cycler else os.path.splitext(video_filename)[0]
        current_description = next(description_cycler)

        print(f"\n===== Processing Channel {i+1}/{len(channel_tokens)}: {os.path.basename(token_file)} =====")
        print(f"    -> Assigned Video: {video_filename} (Title: {video_title})")
        
        try:

            youtube_service = get_authenticated_service(
                CLIENT_SECRET_FILE, 
                token_file, 
                proxies=current_proxies_parsed
            )
            

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
                chosen_thumbnail = random.choice(thumbnail_paths) if len(thumbnail_paths) > 1 else thumbnail_paths[0]
                set_thumbnail(youtube_service, video_id, chosen_thumbnail)

 
            if video_id and current_proxies_parsed:
                mark_proxy_as_used(raw_proxy_line)


        except Exception as e:

            print(f"\n[UPLOAD ERROR] An error occurred during upload for {os.path.basename(token_file)}. Error: {e}")
            if current_proxies_parsed:
                print(f"[PROXY FAILURE] The assigned proxy {raw_proxy_line} likely failed or was rejected. It will NOT be marked as used.")
            
    
    print("\n✅ All tasks complete!")
