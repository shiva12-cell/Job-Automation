"""
Google API Authentication Manager for Gmail & Google Sheets.
Handles OAuth2 user flow and Service Account credentials.
"""

import os
from pathlib import Path
from typing import Optional, List
import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource

# Default scopes needed for Gmail and Sheets
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GoogleAuthManager:
    """Manages authentication and client instantiation for Gmail and Google Sheets."""

    def __init__(
        self,
        credentials_file: str = "config/credentials/credentials.json",
        token_file: str = "config/credentials/token.json",
        service_account_file: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ):
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self.service_account_file = Path(service_account_file) if service_account_file else None
        self.scopes = scopes or DEFAULT_SCOPES
        self._creds: Optional[Credentials] = None

    def get_credentials(self) -> Credentials:
        """Obtains valid user or service account credentials."""
        if self._creds and self._creds.valid:
            return self._creds

        # 1. Check if token.json exists and is valid
        if self.token_file.exists():
            try:
                self._creds = Credentials.from_authorized_user_file(str(self.token_file), self.scopes)
            except Exception as e:
                print(f"[Warning] Failed to load cached token from {self.token_file}: {e}")
                self._creds = None

        # 2. Refresh or trigger OAuth flow if needed
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                try:
                    self._creds.refresh(Request())
                    # Save refreshed token
                    self.token_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.token_file, "w") as token:
                        token.write(self._creds.to_json())
                    return self._creds
                except Exception as e:
                    print(f"[Warning] Failed to refresh token: {e}. Initiating re-authentication flow.")

            # Run OAuth flow if credentials.json exists
            if self.credentials_file.exists():
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), self.scopes
                )
                print("\n" + "=" * 60)
                print("GOOGLE AUTHENTICATION REQUIRED")
                print("A browser window will open to authorize access to:")
                print(" - Gmail (to read application emails & status updates)")
                print(" - Google Sheets (to log & update application rows)")
                print("=" * 60 + "\n")
                self._creds = flow.run_local_server(port=0)

                # Save credentials for subsequent runs
                self.token_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_file, "w") as token:
                    token.write(self._creds.to_json())
            elif self.service_account_file and self.service_account_file.exists():
                from google.oauth2 import service_account
                self._creds = service_account.Credentials.from_service_account_file(
                    str(self.service_account_file), scopes=self.scopes
                )
            else:
                raise FileNotFoundError(
                    f"Google credentials not found!\n"
                    f"Expected OAuth client file at '{self.credentials_file.resolve()}' or service account file.\n"
                    f"Please follow the instructions in README.md to download your credentials.json from Google Cloud Console."
                )

        return self._creds

    def get_gmail_service(self) -> Resource:
        """Returns initialized Gmail API client."""
        creds = self.get_credentials()
        return build("gmail", "v1", credentials=creds)

    def get_sheets_client(self) -> gspread.Client:
        """Returns initialized gspread client for Google Sheets."""
        creds = self.get_credentials()
        return gspread.authorize(creds)
