import os
import pickle
import uuid 

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


def get_authenticated_service(client_secret_file, credentials_file):
    SCOPES = ['https://www.googleapis.com/auth/youtube']
    
    credentials = None

    flow = InstalledAppFlow.from_client_secrets_file(
        client_secret_file, SCOPES)
    credentials = flow.run_local_server(port=0)
    

    with open(credentials_file, 'wb') as token:
        pickle.dump(credentials, token)
        print(f"✅ Successfully created and saved token to: {credentials_file}")

if __name__ == '__main__':
    CLIENT_SECRET_FILE = 'client_secret.json'
    CHANNEL_DIR = 'youtube-channels'


    os.makedirs(CHANNEL_DIR, exist_ok=True)
    

    random_filename = f"{str(uuid.uuid4())[:8]}.pkl"
    output_path = os.path.join(CHANNEL_DIR, random_filename)
    
    get_authenticated_service(CLIENT_SECRET_FILE, output_path)
