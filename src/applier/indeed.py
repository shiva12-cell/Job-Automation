"""
Indeed (India & Global) Auto Applier.
Handles job postings on indeed.com, in.indeed.com, and Indeed Smart Apply.
"""

import re
import uuid
from typing import Optional
from pathlib import Path
from playwright.sync_api import sync_playwright
from src.applier.base import BaseApplier
from src.applier.question_solver import QuestionSolver
from src.models import CandidateProfile, JobApplication, ApplicationStatus


INDEED_SESSION_FILE = "config/credentials/indeed_state.json"


class IndeedApplier(BaseApplier):
    """Automates form submission for Indeed 'Easily apply' job postings."""

    def __init__(self, profile: CandidateProfile, session_file: str = INDEED_SESSION_FILE, **kwargs):
        super().__init__(profile, **kwargs)
        self.session_file = Path(session_file)
        self.solver = QuestionSolver(profile)

    def can_handle(self, url: str) -> bool:
        lower = url.lower()
        return "indeed.com" in lower or "indeedapply" in lower

    def interactive_login(self) -> bool:
        """
        Opens a visible browser for the user to log into Indeed once.
        Saves the authenticated cookies and storage state to indeed_state.json.
        """
        print("\n" + "=" * 65)
        print("INDEED (INDIA) 1-TIME SESSION LOGIN")
        print("A browser window will open to Indeed (in.indeed.com).")
        print("Please log in with your email/password or Google.")
        print("Once you are logged into your dashboard, the session will be saved.")
        print("=" * 65 + "\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ],
                ignore_default_args=["--enable-automation"],
                slow_mo=self.slow_mo_ms,
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            # Navigate to base indeed India to set clean session cookies, then click Sign In
            page.goto("https://in.indeed.com/", timeout=self.timeout_ms)
            self.human_delay(2)

            # Try clicking Sign In on the homepage or redirect to auth
            sign_in_link = page.query_selector("a:has-text('Sign in'), a[href*='account/login'], a[href*='auth']")
            if sign_in_link:
                sign_in_link.click()
            else:
                page.goto("https://in.indeed.com/account/login?hl=en_IN&co=IN", timeout=self.timeout_ms)

            print("[Indeed] Browser opened to Indeed India.")
            print("[Indeed] Please sign in with your email or Google.")
            print("\n>>> Once you are logged in and see your Indeed profile/jobs feed, press ENTER here... <<<")

            try:
                input()
                print("[Indeed] Saving session state...")
                self.session_file.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(self.session_file))
                print(f"[Indeed] [OK] Session saved successfully to {self.session_file}!")
                return True
            except Exception as e:
                print(f"[Indeed] Saving state before exit: {e}")
                self.session_file.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(self.session_file))
                return False
            finally:
                browser.close()

    def apply(self, url: str, dry_run: bool = True) -> Optional[JobApplication]:
        print(f"\n[Indeed] Launching applier for: {url}")
        print(f"[Indeed] Mode: {'DRY RUN (Will not submit)' if dry_run else 'LIVE SUBMISSION'}")

        if not self.session_file.exists():
            print(f"[Indeed Notice] No saved session found at {self.session_file}.")
            print("Tip: Run 'python src/runner.py indeed-login' to link your Indeed account permanently.")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ],
                ignore_default_args=["--enable-automation"],
                slow_mo=self.slow_mo_ms,
            )
            context_kwargs = {
                "viewport": {"width": 1280, "height": 900},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            if self.session_file.exists():
                context_kwargs["storage_state"] = str(self.session_file)

            context = browser.new_context(**context_kwargs)
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            try:
                page.goto(url, timeout=self.timeout_ms)
                page.wait_for_load_state("domcontentloaded")
                self.human_delay(2)

                # Extract Job Title & Company
                job_title = "Data Analyst / Role"
                company = "Unknown Company"

                title_elem = page.query_selector("h1[data-testid='jobsearch-JobInfoHeader-title'], h1.jobsearch-JobInfoHeader-title, h1")
                if title_elem:
                    job_title = title_elem.inner_text().strip()

                comp_elem = page.query_selector("[data-testid='inlineHeader-companyName'], .jobsearch-InlineCompanyRating-companyHeader, [data-company-name='true']")
                if comp_elem:
                    company = comp_elem.inner_text().strip().split("\n")[0].strip()

                safe_company = re.sub(r'[^\w\-_\.]', '_', company)[:30]
                print(f"[Indeed] Detected: {company} - {job_title}")

                # Check if already applied on Indeed UI
                already_applied = page.query_selector(
                    ":has-text('You have applied to this job'), :has-text('Applied 30+ days ago'), [data-testid*='applied'], button:has-text('Applied')"
                )
                if already_applied and already_applied.is_visible():
                    print(f"[Indeed] You have already applied previously to {company} for this job.")
                    return JobApplication(
                        app_id=f"IND-{uuid.uuid4().hex[:8]}",
                        company=company,
                        job_title=job_title,
                        location="India",
                        job_url=url,
                        platform="Indeed (India)",
                        status=ApplicationStatus.APPLIED,
                        notes=f"Already applied previously on Indeed to {company}",
                    )

                # Look for 'Apply now' or 'Easily apply' button
                apply_button = page.query_selector(
                    "#indeedApplyButton, button[id*='indeedApply'], button:has-text('Apply now'), button:has-text('Easily apply')"
                )

                if not apply_button:
                    # Check for external apply link / button
                    ext_btn = page.query_selector("a:has-text('Apply on company site'), button:has-text('Apply on company site'), a[href*='rc/clk']")
                    ext_url = ext_btn.get_attribute("href") if ext_btn else url
                    print(f"[Indeed] 'Easily apply' button not found. Identified company site redirect for {company}. Marked for Manual Apply.")
                    return JobApplication(
                        app_id=f"MAN-{uuid.uuid4().hex[:8]}",
                        company=company,
                        job_title=job_title,
                        location="India",
                        job_url=ext_url or url,
                        platform="Indeed (Company Site)",
                        status=ApplicationStatus.MANUAL_APPLY_NEEDED,
                        notes=f"Apply on company site (External: {ext_url or url})",
                    )

                apply_button.click()
                self.human_delay(3)

                # Indeed often opens the application in a modal or an iframe
                target_frame = page
                frames = page.frames
                for f in frames:
                    if "indeed" in f.url or "apply" in f.name.lower():
                        target_frame = f
                        break

                # Step 1: Contact info
                self._fill_input(target_frame, ["input[id*='applicant.name']", "input[name*='name']"], self.profile.personal_info.full_name)
                self._fill_input(target_frame, ["input[id*='applicant.email']", "input[name*='email']"], self.profile.personal_info.email)
                self._fill_input(target_frame, ["input[id*='applicant.phoneNumber']", "input[name*='phone']"], self.profile.personal_info.phone)
                self._fill_input(target_frame, ["input[id*='applicant.location']", "input[name*='city']"], self.profile.personal_info.location)

                # Step through Indeed modal pages (multi-step wizard)
                max_steps = 6
                step = 0
                submitted = False

                while step < max_steps:
                    step += 1
                    self.human_delay(1.5)

                    # Check for Resume upload input if present
                    if self.profile.resume_path and Path(self.profile.resume_path).exists():
                        file_input = target_frame.query_selector("input[type='file']")
                        if file_input and file_input.is_visible():
                            print(f"[Indeed] Attaching resume: {self.profile.resume_path}")
                            file_input.set_input_files(str(Path(self.profile.resume_path).resolve()))
                            self.human_delay(2)

                    # Handle screening questions if any on this step
                    self._handle_screening_questions(target_frame)

                    # Check if we reached the final "Submit your application" or "Review" step
                    submit_button = target_frame.query_selector(
                        "button:has-text('Submit your application'), button:has-text('Submit application')"
                    )

                    if submit_button:
                        if dry_run:
                            print("[Indeed] Dry-run: Reached final review step! Saving screenshot...")
                            screenshot_file = f"indeed_dry_run_{safe_company}.png"
                            page.screenshot(path=screenshot_file)
                            print(f"[Indeed] Screenshot captured: {screenshot_file}")
                            submitted = True
                        else:
                            print("[Indeed] Submitting application...")
                            submit_button.click()
                            self.human_delay(4)
                            print("[Indeed] Application submitted successfully!")
                            submitted = True
                        break

                    # Look for Continue / Next button to go to next step
                    continue_btn = target_frame.query_selector(
                        "button:has-text('Continue'), button:has-text('Next'), button:has-text('Review your application')"
                    )
                    if continue_btn and continue_btn.is_visible():
                        continue_btn.click()
                    else:
                        break

                if not submitted and not dry_run:
                    print(f"[Indeed] ⚠️ Notice: Application process could not reach final submit for {company}.")
                    return None

                app = JobApplication(
                    app_id=f"IND-{uuid.uuid4().hex[:8]}",
                    company=company,
                    job_title=job_title,
                    location="India",
                    job_url=url,
                    platform="Indeed (India)",
                    status=ApplicationStatus.APPLIED,
                    notes="Applied via Indeed Auto-Applier" + (" (DRY RUN)" if dry_run else ""),
                )
                return app

            except Exception as e:
                print(f"[Indeed Error] Application failed: {e}")
                return None
            finally:
                browser.close()

    def _fill_input(self, frame, selectors, value: str) -> bool:
        for sel in selectors:
            elem = frame.query_selector(sel)
            if elem and elem.is_visible():
                elem.fill(value)
                return True
        return False

    def _handle_screening_questions(self, frame) -> None:
        """Answers standard screening inputs (experience, city, yes/no)."""
        questions = frame.query_selector_all("fieldset, .ia-Questions-item, [data-testid*='question']")
        for q in questions:
            try:
                label_elem = q.query_selector("legend, label, .heading")
                if not label_elem:
                    continue
                label_text = label_elem.inner_text().strip()

                # Text input
                text_input = q.query_selector("input[type='text'], input[type='number'], textarea")
                if text_input and text_input.is_visible() and not text_input.input_value():
                    ans = self.solver.answer_text_question(label_text)
                    if ans:
                        text_input.fill(ans)

                # Radio inputs (Yes / No)
                radios = q.query_selector_all("input[type='radio']")
                if radios:
                    labels = [r.get_attribute("value") or "" for r in radios]
                    best_opt = self.solver.select_best_option(label_text, labels)
                    if best_opt:
                        for r in radios:
                            if r.get_attribute("value") == best_opt:
                                r.check()
                                break
            except Exception:
                pass
