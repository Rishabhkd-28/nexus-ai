"""
Run this ONCE locally to get your GOOGLE_TOKEN_JSON.
Never deploy this file — it's only for setup.

Usage:
  1. Download credentials.json from Google Cloud Console
     (OAuth 2.0 → Desktop app → Download JSON)
  2. Put credentials.json in this folder
  3. Run: python get_google_token.py
  4. Browser opens → sign in → approve
  5. Copy the printed JSON → paste as GOOGLE_TOKEN_JSON in Render env vars
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", scopes=SCOPES)
creds = flow.run_local_server(port=0)

token_json = json.dumps({
    "token":         creds.token,
    "refresh_token": creds.refresh_token,
})

print("\n" + "="*60)
print("Copy everything between the lines into GOOGLE_TOKEN_JSON:")
print("="*60)
print(token_json)
print("="*60 + "\n")

# Also save locally for reference
with open("token_output.json", "w") as f:
    f.write(token_json)
print("Also saved to token_output.json (DO NOT commit this file)")
