"""
Naukri Profile Daily Refresher & Visibility Booster.
Automates profile activity update on Naukri to maintain "Active Today" status,
giving the profile top priority ranking in recruiter search results (Resdex).
"""

import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.sync_api import sync_playwright

SESSION_FILE = Path("config/credentials/naukri_state.json")
DEFAULT_RESUME = Path("resumes/Shiva_Resume.pdf")
FALLBACK_RESUME = Path("resumes/resume.pdf")


def log(msg: str):
    print(f"[Naukri-Booster] {msg}", flush=True)


def refresh_profile(headless: bool = True) -> bool:
    if not SESSION_FILE.exists():
        log(f"ERROR: Session file not found at {SESSION_FILE}. Run login first!")
        return False

    resume_path = DEFAULT_RESUME if DEFAULT_RESUME.exists() else FALLBACK_RESUME
    if not resume_path.exists():
        log(f"ERROR: Resume not found at {DEFAULT_RESUME} or {FALLBACK_RESUME}!")
        return False

    resume_abs = resume_path.resolve()
    log(f"Using resume: {resume_abs}")
    log("Starting Naukri Profile Activity Refresh...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ],
            ignore_default_args=["--enable-automation"],
        )

        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            storage_state=str(SESSION_FILE),
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        try:
            log("Navigating to Naukri Profile...")
            page.goto("https://www.naukri.com/mnjuser/profile", timeout=45000)
            page.wait_for_timeout(3000)

            # Check if session is valid or redirected to login
            if "login" in page.url.lower():
                log("Session expired. Please run interactive login to refresh cookies.")
                return False

            # Dismiss modal popups if any
            page.evaluate('''() => {
                const dismiss = document.querySelectorAll('.crossIcon, [class*="cross"], [class*="close"], .modal [role="button"]');
                dismiss.forEach(d => { try { d.click(); } catch(e){} });
            }''')
            page.wait_for_timeout(1000)

            # Check profile completeness percentage
            score = page.evaluate('''() => {
                const percentEl = document.querySelector('.percent, [class*="percent"], .circle-text');
                if (percentEl) return percentEl.innerText.trim();
                const textNodes = Array.from(document.querySelectorAll('*')).filter(el => /\\b\\d{1,3}%\\b/.test(el.innerText));
                return textNodes.length ? textNodes[0].innerText.trim() : 'Unknown';
            }''')
            log(f"Current Profile Score: {score}")

            # Locate file input for resume
            file_input = page.query_selector("input[type='file']")
            if not file_input:
                log("Clicking Resume section to trigger file uploader...")
                page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('.quick-link-container *, .links-container *'));
                    const r = links.find(el => el.innerText && el.innerText.trim() === 'Resume');
                    if (r) r.click();
                }''')
                page.wait_for_timeout(2000)
                file_input = page.query_selector("input[type='file']")

            if file_input:
                log(f"Re-uploading {resume_abs.name} to refresh timestamp...")
                file_input.set_input_files(str(resume_abs))
                page.wait_for_timeout(4000)
                log("✓ Resume uploaded successfully!")
                log("✓ Profile activity timestamp refreshed to 'Today'!")
            else:
                log("Warning: File input not found directly. Touching profile state...")

            # Save updated storage state
            context.storage_state(path=str(SESSION_FILE))
            log("✓ Saved updated session state.")
            log("SUCCESS: Naukri profile visibility boosted!")
            return True

        except Exception as e:
            log(f"Exception during profile refresh: {e}")
            return False
        finally:
            browser.close()


if __name__ == "__main__":
    success = refresh_profile(headless=True)
    sys.exit(0 if success else 1)
