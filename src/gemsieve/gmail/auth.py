"""OAuth2 authentication for Gmail API."""

from __future__ import annotations

import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from gemsieve.config import Config

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def authenticate(config: Config) -> Credentials:
    """Authenticate with Gmail API via OAuth2, caching the token for reuse."""
    credentials_file = config.gmail.credentials_file
    token_file = config.gmail.token_file
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                print(f"ERROR: {credentials_file} not found.", file=sys.stderr)
                print(
                    "Download your OAuth 2.0 credentials from Google Cloud Console.",
                    file=sys.stderr,
                )
                raise FileNotFoundError(f"Gmail credentials file not found: {credentials_file}")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return creds


def get_gmail_service(config: Config):
    """Return an authenticated Gmail API service object."""
    creds = authenticate(config)
    return build("gmail", "v1", credentials=creds)


def get_user_email(service) -> str:
    """Get the authenticated user's email address."""
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]
