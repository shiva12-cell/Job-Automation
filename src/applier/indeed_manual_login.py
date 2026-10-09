"""
Browser-to-Cookie Extractor for Indeed & Naukri.
Launches the user's real Chrome profile with debugging port or extracts cookies
using lightweight, non-automated browser sessions so Google SSO / Cloudflare
never block authentication.
"""

import os
import sys
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

INDEED_STATE_PATH = Path("config/credentials/indeed_state.json")
NAUKRI_STATE_PATH = Path("config/credentials/naukri_state.json")
CHROME_USER_DATA = Path("config/credentials/chrome_login_profile")


def login_indeed():
    """
    Launches Chrome using a dedicated persistent user data directory.
    This bypasses Google SSO popup blocks and Indeed 400 Bad Request
    because it's treated as a permanent local browser profile.
    """
    CHROME_USER_DATA.mkdir(parents=True, exist_ok=True)
    INDEED_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 65)
    print("      LINK INDEED ACCOUNT (PERSISTENT CHROME PROFILE)")
    print("=" * 65)
    print("A real Google Chrome window will open.")
    print("You can log into Indeed using:")
    print("  • 'Continue with Google' (Fully supported!)")
    print("  • Email & Password")
    print("  • OTP")
    print("=" * 65 + "\n")

    with sync_playwright() as p:
        # Use persistent context with real Chrome
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_USER_DATA.resolve()),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            ignore_default_args=["--enable-automation"],
        )

        page = context.pages[0] if context.pages else context.new_page()

        print("[Indeed] Navigating to Indeed India...")
        page.goto("https://in.indeed.com/", wait_until="domcontentloaded")

        print("\n[Action Needed in Browser Window]:")
        print("1. Click 'Sign In' at the top-right of Indeed.")
        print("2. Log in using Google or your email.")
        print("3. Once you see your name or Indeed homepage/feed:")
        print("\n>>> Come back here and PRESS ENTER to save your session! <<<\n")

        try:
            input()
            print("[Indeed] Extracting and saving session state...")
            context.storage_state(path=str(INDEED_STATE_PATH))
            print(f"[Indeed] SUCCESS! Your session is permanently saved to {INDEED_STATE_PATH}.")
            print("Indeed is now linked and ready for autonomous applying!")
            time.sleep(2)
            return True
        except Exception as e:
            print(f"[Notice] Session saved with: {e}")
            context.storage_state(path=str(INDEED_STATE_PATH))
            return True
        finally:
            context.close()


if __name__ == "__main__":
    login_indeed()
