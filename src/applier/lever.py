"""
Lever ATS Auto Applier.
Fills out job applications hosted on jobs.lever.co.
"""

import uuid
from typing import Optional
from pathlib import Path
from playwright.sync_api import sync_playwright
from src.applier.base import BaseApplier
from src.applier.question_solver import QuestionSolver
from src.models import CandidateProfile, JobApplication, ApplicationStatus


class LeverApplier(BaseApplier):
    """Automates form submission for Lever job postings."""

    def __init__(self, profile: CandidateProfile, **kwargs):
        super().__init__(profile, **kwargs)
        self.solver = QuestionSolver(profile)

    def can_handle(self, url: str) -> bool:
        return "lever.co" in url.lower()

    def apply(self, url: str, dry_run: bool = True) -> Optional[JobApplication]:
        # Ensure url ends with /apply if not already
        apply_url = url if url.endswith("/apply") else f"{url.rstrip('/')}/apply"
        print(f"\n[Lever] Launching applier for: {apply_url}")
        print(f"[Lever] Mode: {'DRY RUN (Will not submit)' if dry_run else 'LIVE SUBMISSION'}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, slow_mo=self.slow_mo_ms)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            try:
                page.goto(apply_url, timeout=self.timeout_ms)
                page.wait_for_load_state("networkidle")

                # Extract company and job title
                job_title = "Unknown Position"
                company = "Unknown Company"

                title_elem = page.query_selector(".posting-headline h2, h2")
                if title_elem:
                    job_title = title_elem.inner_text().strip()

                if "jobs.lever.co/" in apply_url:
                    parts = apply_url.split("jobs.lever.co/")[1].split("/")
                    if parts:
                        company = parts[0].capitalize()

                print(f"[Lever] Applying to {company} - {job_title}")

                # Standard fields
                self._fill_input(page, ["input[name='name']"], self.profile.personal_info.full_name)
                self._fill_input(page, ["input[name='email']"], self.profile.personal_info.email)
                self._fill_input(page, ["input[name='phone']"], self.profile.personal_info.phone)
                self._fill_input(page, ["input[name='org']"], self.profile.personal_info.current_company or "")

                # Social / Portfolio URLs
                if self.profile.personal_info.linkedin_url:
                    self._fill_input(page, ["input[name*='urls[LinkedIn]']", "input[name*='urls[linkedin]']"], self.profile.personal_info.linkedin_url)
                if self.profile.personal_info.github_url:
                    self._fill_input(page, ["input[name*='urls[GitHub]']", "input[name*='urls[github]']"], self.profile.personal_info.github_url)
                if self.profile.personal_info.portfolio_url:
                    self._fill_input(page, ["input[name*='urls[Portfolio]']", "input[name*='urls[Other]']"], self.profile.personal_info.portfolio_url)

                # Additional information / cover letter
                if self.profile.cover_letter:
                    self._fill_input(page, ["textarea[name='comments']"], self.profile.cover_letter)

                # Upload resume
                if self.profile.resume_path and Path(self.profile.resume_path).exists():
                    resume_input = page.query_selector("input[type='file'][id='resume-upload-input'], input[type='file']")
                    if resume_input:
                        print(f"[Lever] Uploading resume from: {self.profile.resume_path}")
                        resume_input.set_input_files(str(Path(self.profile.resume_path).resolve()))
                        self.human_delay(1.5)

                # Custom questions and dropdowns
                self._handle_custom_fields(page)

                if dry_run:
                    print("[Lever] Dry-run completed. Form was filled successfully without submission.")
                    screenshot_path = f"lever_dry_run_{company.lower()}.png"
                    page.screenshot(path=screenshot_path)
                    print(f"[Lever] Screenshot saved to: {screenshot_path}")
                else:
                    submit_btn = page.query_selector("button#btn-submit, button[type='submit']")
                    if submit_btn:
                        print("[Lever] Submitting application...")
                        submit_btn.click()
                        page.wait_for_timeout(4000)
                        print("[Lever] Application submitted successfully!")

                # Return structured application record
                app = JobApplication(
                    app_id=f"LEV-{uuid.uuid4().hex[:8]}",
                    company=company,
                    job_title=job_title,
                    job_url=url,
                    platform="Lever",
                    status=ApplicationStatus.APPLIED,
                    notes="Applied via Lever Auto-Applier" + (" (DRY RUN)" if dry_run else ""),
                )
                return app

            except Exception as e:
                print(f"[Lever Error] Failed to complete application: {e}")
                return None
            finally:
                browser.close()

    def _fill_input(self, page, selectors, value: str) -> bool:
        for sel in selectors:
            elem = page.query_selector(sel)
            if elem and elem.is_visible():
                elem.fill(value)
                return True
        return False

    def _handle_custom_fields(self, page) -> None:
        questions = page.query_selector_all(".application-question")
        for q in questions:
            try:
                label_elem = q.query_selector(".text, label")
                if not label_elem:
                    continue
                label_text = label_elem.inner_text().strip()

                # Check text inputs
                text_input = q.query_selector("input[type='text'], textarea")
                if text_input and text_input.is_visible() and not text_input.input_value():
                    ans = self.solver.answer_text_question(label_text)
                    if ans:
                        text_input.fill(ans)

                # Check dropdowns
                select = q.query_selector("select")
                if select and select.is_visible():
                    options = [opt.inner_text().strip() for opt in select.query_selector_all("option") if opt.inner_text().strip()]
                    best_opt = self.solver.select_best_option(label_text, options)
                    if best_opt:
                        select.select_option(label=best_opt)

                # Check radio buttons
                radio_inputs = q.query_selector_all("input[type='radio']")
                if radio_inputs:
                    labels = [r.get_attribute("value") or "" for r in radio_inputs]
                    best_radio = self.solver.select_best_option(label_text, labels)
                    if best_radio:
                        for r in radio_inputs:
                            if r.get_attribute("value") == best_radio:
                                r.check()
                                break
            except Exception:
                pass
