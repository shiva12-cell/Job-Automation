"""
Greenhouse ATS Auto Applier.
Fills out job applications hosted on boards.greenhouse.io or greenhouse embeds.
"""

import uuid
from typing import Optional
from pathlib import Path
from playwright.sync_api import sync_playwright
from src.applier.base import BaseApplier
from src.applier.question_solver import QuestionSolver
from src.models import CandidateProfile, JobApplication, ApplicationStatus


class GreenhouseApplier(BaseApplier):
    """Automates form submission for Greenhouse job boards."""

    def __init__(self, profile: CandidateProfile, **kwargs):
        super().__init__(profile, **kwargs)
        self.solver = QuestionSolver(profile)

    def can_handle(self, url: str) -> bool:
        return "greenhouse.io" in url.lower() or "gh_jid" in url.lower()

    def apply(self, url: str, dry_run: bool = True) -> Optional[JobApplication]:
        print(f"\n[Greenhouse] Launching applier for: {url}")
        print(f"[Greenhouse] Mode: {'DRY RUN (Will not submit)' if dry_run else 'LIVE SUBMISSION'}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, slow_mo=self.slow_mo_ms)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            try:
                page.goto(url, timeout=self.timeout_ms)
                page.wait_for_load_state("networkidle")

                # Extract company and job title
                job_title = "Unknown Position"
                company = "Unknown Company"

                title_elem = page.query_selector("h1.app-title, h1")
                if title_elem:
                    job_title = title_elem.inner_text().strip()

                comp_elem = page.query_selector("span.company-name, .company-name")
                if comp_elem:
                    company = comp_elem.inner_text().strip()
                elif "greenhouse.io/" in url:
                    # extract slug e.g. greenhouse.io/stripe/jobs/123 -> stripe
                    parts = url.split("greenhouse.io/")[1].split("/")
                    if parts:
                        company = parts[0].capitalize()

                print(f"[Greenhouse] Applying to {company} - {job_title}")

                # Standard fields
                self._fill_input(page, ["#first_name", "input[name*='first_name']"], self.profile.personal_info.first_name)
                self._fill_input(page, ["#last_name", "input[name*='last_name']"], self.profile.personal_info.last_name)
                self._fill_input(page, ["#email", "input[name*='email']"], self.profile.personal_info.email)
                self._fill_input(page, ["#phone", "input[name*='phone']"], self.profile.personal_info.phone)

                # Location if available
                self._fill_input(page, ["#location", "input[name*='location']", "input[name*='city']"], self.profile.personal_info.location)

                # LinkedIn
                if self.profile.personal_info.linkedin_url:
                    self._fill_input(page, ["input[name*='urls[LinkedIn]']", "input[name*='linkedin']"], self.profile.personal_info.linkedin_url)

                # Website / Portfolio
                if self.profile.personal_info.portfolio_url:
                    self._fill_input(page, ["input[name*='urls[Portfolio]']", "input[name*='website']"], self.profile.personal_info.portfolio_url)

                # Upload Resume if exists
                if self.profile.resume_path and Path(self.profile.resume_path).exists():
                    resume_input = page.query_selector("input[type='file'][id*='resume'], input[type='file'][name*='resume'], input[type='file']")
                    if resume_input:
                        print(f"[Greenhouse] Attaching resume from: {self.profile.resume_path}")
                        resume_input.set_input_files(str(Path(self.profile.resume_path).resolve()))
                        self.human_delay(1.5)

                # Custom questions and dropdowns
                self._handle_custom_fields(page)

                if dry_run:
                    print("[Greenhouse] Dry-run completed. Form was filled successfully without submission.")
                    screenshot_path = f"greenhouse_dry_run_{company.lower()}.png"
                    page.screenshot(path=screenshot_path)
                    print(f"[Greenhouse] Screenshot saved to: {screenshot_path}")
                else:
                    submit_btn = page.query_selector("#submit_app, button[type='submit'], input[type='submit']")
                    if submit_btn:
                        print("[Greenhouse] Submitting application...")
                        submit_btn.click()
                        page.wait_for_timeout(4000)
                        print("[Greenhouse] Form submitted successfully!")

                # Return structured application record
                app = JobApplication(
                    app_id=f"GH-{uuid.uuid4().hex[:8]}",
                    company=company,
                    job_title=job_title,
                    job_url=url,
                    platform="Greenhouse",
                    status=ApplicationStatus.APPLIED,
                    notes="Applied via Greenhouse Auto-Applier" + (" (DRY RUN)" if dry_run else ""),
                )
                return app

            except Exception as e:
                print(f"[Greenhouse Error] Failed to complete application: {e}")
                return None
            finally:
                browser.close()

    def _fill_input(self, page, selectors, value: str) -> bool:
        """Attempts to find and fill an input matching one of the selectors."""
        for sel in selectors:
            elem = page.query_selector(sel)
            if elem and elem.is_visible():
                elem.fill(value)
                return True
        return False

    def _handle_custom_fields(self, page) -> None:
        """Discovers and answers custom form inputs and dropdowns."""
        # Process select dropdowns
        selects = page.query_selector_all("select")
        for sel in selects:
            try:
                if not sel.is_visible():
                    continue
                # Get label text
                label_elem = page.query_selector(f"label[for='{sel.get_attribute('id')}']")
                label_text = label_elem.inner_text() if label_elem else sel.get_attribute("name") or ""
                options = [opt.inner_text().strip() for opt in sel.query_selector_all("option") if opt.inner_text().strip()]
                best_option = self.solver.select_best_option(label_text, options)
                if best_option:
                    sel.select_option(label=best_option)
            except Exception:
                pass

        # Process custom text inputs
        custom_inputs = page.query_selector_all("input[type='text'], textarea")
        for inp in custom_inputs:
            try:
                if not inp.is_visible() or inp.input_value():
                    continue
                label_elem = page.query_selector(f"label[for='{inp.get_attribute('id')}']")
                label_text = label_elem.inner_text() if label_elem else inp.get_attribute("name") or ""
                answer = self.solver.answer_text_question(label_text)
                if answer:
                    inp.fill(answer)
            except Exception:
                pass
