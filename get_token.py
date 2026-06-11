"""
get_token.py — Run once to generate token.json.
Requires nicolas_gdrive_api_credentials.json in the same folder.
After running, token.json can be distributed in the ZIP.
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive']

flow = InstalledAppFlow.from_client_secrets_file(
    'nicolas_gdrive_api_credentials.json', SCOPES
)
creds = flow.run_local_server(port=8080)

with open('token.json', 'w') as f:
    f.write(creds.to_json())

print("token.json saved successfully.")
