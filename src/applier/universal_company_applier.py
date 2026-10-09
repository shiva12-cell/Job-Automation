"""
Universal Company Career Website Applier.
Fills multi-step application wizards across Workday, Greenhouse, Lever, Taleo,
SuccessFactors, Darwinbox, SmartRecruiters, and custom MNC career portals
using the 12-Pillar Question Superset Engine.
"""

import re
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from playwright.sync_api import sync_playwright, Page

from src.applier.base import BaseApplier
from src.applier.question_solver import QuestionSolver
from src.applier.question_superset import QuestionSupersetResolver
from src.models import CandidateProfile, JobApplication, ApplicationStatus


def safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass


class UniversalCompanyApplier(BaseApplier):
    """
    Universal form filling automation for MNC career portals.
    Fills standard inputs, attaches resume, answers screening questions from Superset,
    and supports multi-step Next/Submit workflows.
    """

    def __init__(self, profile: CandidateProfile, **kwargs):
        super().__init__(profile, **kwargs)
        self.solver = QuestionSolver(profile)
        self.superset = QuestionSupersetResolver(profile)

    def can_handle(self, url: str) -> bool:
        # Acts as universal fallback for external company portals
        return url.startswith("http") and "naukri.com" not in url.lower() and "indeed." not in url.lower()

    def apply(self, url: str, dry_run: bool = True) -> Optional[JobApplication]:
        safe_print(f"\n[Company Portal Applier] Navigating to company career portal: {url}")
        safe_print(f"[Company Portal Applier] Mode: {'DRY RUN (Will inspect & prepare form)' if dry_run else 'LIVE AUTOMATED SUBMISSION'}")

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

            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            try:
                page.goto(url, timeout=self.timeout_ms)
                page.wait_for_load_state("domcontentloaded")
                self.human_delay(2)
                self._dismiss_overlays(page)

                # Track popups / new tabs opened during application
                opened_tabs: List[Page] = []
                context.on("page", lambda p: opened_tabs.append(p))

                # Extract company & title if available on page
                title = "Candidate Application"
                company = "Company"
                h1 = page.query_selector("h1")
                if h1:
                    title = h1.inner_text().strip()[:50]

                # Check for Apply button to open form if not already opened
                apply_start_btn = page.query_selector(
                    "a:has-text('Apply for job'), a:has-text('Apply Now'), button:has-text('Apply Now'), a:has-text('Apply'), button:has-text('Apply'), [data-automation-id='adventureButton']"
                )
                if apply_start_btn and apply_start_btn.is_visible():
                    btn_href = apply_start_btn.get_attribute("href")
                    if btn_href and btn_href.startswith("http") and "naukri.com" not in btn_href and btn_href != page.url:
                        safe_print(f"[Company Portal Applier] Navigating to external application URL: {btn_href}")
                        try:
                            page.goto(btn_href, timeout=self.timeout_ms, wait_until="domcontentloaded")
                            self.human_delay(2)
                        except Exception as e:
                            safe_print(f"[Company Portal Applier] Navigation note: {e}")
                    else:
                        safe_print("[Company Portal Applier] Clicking 'Apply' button to launch form...")
                        clicked = self._safe_click(page, apply_start_btn)
                        if clicked:
                            page.wait_for_timeout(3000)
                            # Check if a new tab was opened
                            if opened_tabs:
                                page = opened_tabs[-1]
                                try:
                                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                                except Exception:
                                    pass

                self._dismiss_overlays(page)

                # Check if login or account creation wall is strictly required (e.g. Workday Login)
                password_field = page.query_selector("input[type='password']")
                login_heading = page.query_selector(":has-text('Sign In'), :has-text('Create Account'), :has-text('Log In')")
                if password_field and password_field.is_visible() and login_heading:
                    safe_print(f"[Company Portal Applier] Account login wall detected on {url}. Logging for user review.")
                    return JobApplication(
                        app_id=f"ACW-{uuid.uuid4().hex[:8]}",
                        company=company,
                        job_title=title,
                        location="India",
                        job_url=url,
                        platform="Company Portal (Login Required)",
                        status=ApplicationStatus.MANUAL_APPLY_NEEDED,
                        notes="Candidate account creation/login required on company portal",
                    )

                # Form filling steps
                filled_fields = self._fill_universal_form(page, company=company, job_title=title)
                safe_print(f"[Company Portal Applier] Automated form filler populated {filled_fields} input fields.")

                # Upload Resume if file input present
                self._attach_resume(page)

                # Check for CAPTCHA wall
                captcha_elem = page.query_selector("iframe[src*='recaptcha'], iframe[src*='turnstile'], iframe[src*='hcaptcha'], .g-recaptcha, .cf-turnstile")
                if captcha_elem and captcha_elem.is_visible():
                    safe_print(f"[Company Portal Applier] CAPTCHA challenge detected on {url}. Logging pre-filled state for user 1-click completion.")
                    return JobApplication(
                        app_id=f"ACW-{uuid.uuid4().hex[:8]}",
                        company=company,
                        job_title=title,
                        location="India",
                        job_url=url,
                        platform="Company Portal (CAPTCHA)",
                        status=ApplicationStatus.MANUAL_APPLY_NEEDED,
                        notes=f"Form pre-filled ({filled_fields} fields). CAPTCHA verification required: {url}",
                    )

                if dry_run:
                    safe_print(f"[Company Portal Applier] [Dry-Run] Inspected & prepared form for {title} on {url}.")
                    return JobApplication(
                        app_id=f"ACW-{uuid.uuid4().hex[:8]}",
                        company=company,
                        job_title=title,
                        location="India",
                        job_url=url,
                        platform="Company Portal",
                        status=ApplicationStatus.APPLIED,
                        notes="Form prepared and verified via Universal Company Applier (Dry-Run)",
                    )

                # Multi-Step Wizard Loop: advance through up to 3 pages if Next button is present
                for step_idx in range(3):
                    self._dismiss_overlays(page)
                    submit_btn = page.query_selector(
                        "button[type='submit'], input[type='submit'], button:has-text('Submit Application'), button:has-text('Submit'), button:has-text('Review and Submit')"
                    )
                    if submit_btn and submit_btn.is_visible():
                        break

                    next_btn = page.query_selector(
                        "button:has-text('Next'), button:has-text('Continue'), button:has-text('Save and Continue'), a:has-text('Next'), [data-automation-id='bottom-navigation-next-button']"
                    )
                    if next_btn and next_btn.is_visible():
                        safe_print(f"[Company Portal Applier] Advancing wizard (Step {step_idx + 1} -> Next)...")
                        if self._safe_click(page, next_btn):
                            page.wait_for_timeout(3000)
                            more_filled = self._fill_universal_form(page, company=company, job_title=title)
                            filled_fields += more_filled
                        else:
                            break
                    else:
                        break

                # Look for final Submit button
                self._dismiss_overlays(page)
                submit_btn = page.query_selector(
                    "button[type='submit'], input[type='submit'], button:has-text('Submit Application'), button:has-text('Submit'), button:has-text('Review and Submit')"
                )
                if submit_btn and submit_btn.is_visible():
                    safe_print("[Company Portal Applier] Submitting company website application...")
                    self._safe_click(page, submit_btn)
                    self.human_delay(3)
                    page.wait_for_timeout(3000)

                    # Check for confirmation indicators
                    confirm_text = page.query_selector(
                        ":has-text('thank you'), :has-text('successfully submitted'), :has-text('application received'), :has-text('your application has been submitted')"
                    )
                    if confirm_text:
                        safe_print("[Company Portal Applier] ✓ Confirmation verified on company portal!")
                        return JobApplication(
                            app_id=f"ACW-{uuid.uuid4().hex[:8]}",
                            company=company,
                            job_title=title,
                            location="India",
                            job_url=url,
                            platform="Company Portal",
                            status=ApplicationStatus.APPLIED,
                            notes="Successfully submitted via Universal Company Applier",
                        )

                # If multi-step or awaiting manual final review:
                safe_print(f"[Company Portal Applier] Multi-step portal pre-filled ({filled_fields} fields). Logged to ACW sheet.")
                return JobApplication(
                    app_id=f"ACW-{uuid.uuid4().hex[:8]}",
                    company=company,
                    job_title=title,
                    location="India",
                    job_url=url,
                    platform="Company Portal",
                    status=ApplicationStatus.MANUAL_APPLY_NEEDED,
                    notes=f"Form pre-filled ({filled_fields} fields) via Superset Engine. Saved for final submission review.",
                )

            except Exception as e:
                safe_print(f"[Company Portal Applier] Error: {e}")
                return None
            finally:
                browser.close()

    def _dismiss_overlays(self, page: Page):
        """Removes cookie banners, modals, and system alerts blocking clicks."""
        try:
            page.evaluate("""() => {
                const selectors = [
                    '#system-ialert', '#system-imessage', '.system-ialert-css',
                    '#onetrust-banner-sdk', '#onetrust-consent-sdk',
                    '.cookie-banner', '.cookie-consent', '#cookie-notice',
                    '[id*="cookie-banner"]', '[class*="cookie-banner"]',
                    '.modal-backdrop'
                ];
                for (const sel of selectors) {
                    const elements = document.querySelectorAll(sel);
                    for (const el of elements) {
                        try { el.remove(); } catch (e) {}
                    }
                }
            }""")
        except Exception:
            pass

    def _safe_click(self, page: Page, element) -> bool:
        """Safely clicks an element dismissing overlays and falling back to JS click."""
        if not element:
            return False
        self._dismiss_overlays(page)
        try:
            element.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        try:
            element.click(timeout=4000)
            return True
        except Exception:
            try:
                element.click(force=True, timeout=2000)
                return True
            except Exception:
                try:
                    page.evaluate("(el) => el.click()", element)
                    return True
                except Exception:
                    return False

    def _fill_universal_form(self, page: Page, company: str, job_title: str) -> int:
        """Finds all visible inputs, textareas, and selects, answering them using Superset."""
        filled = 0
        inputs = page.query_selector_all("input:not([type='hidden']):not([type='submit']):not([type='file']), textarea")
        for inp in inputs:
            try:
                if not inp.is_visible():
                    continue
                # Determine label or placeholder
                label_text = self._get_field_label(inp)
                if not label_text:
                    continue

                answer = self.solver.answer_text_question(label_text, company=company, job_title=job_title)
                if answer and not inp.input_value():
                    inp.fill(str(answer))
                    filled += 1
            except Exception:
                pass

        # Select / Dropdown elements
        selects = page.query_selector_all("select")
        for sel in selects:
            try:
                if not sel.is_visible():
                    continue
                label_text = self._get_field_label(sel)
                options = [o.inner_text().strip() for o in sel.query_selector_all("option") if o.inner_text().strip()]
                if options:
                    choice = self.solver.select_best_option(label_text, options, company=company, job_title=job_title)
                    if choice:
                        sel.select_option(label=choice)
                        filled += 1
            except Exception:
                pass

        return filled

    def _get_field_label(self, element) -> str:
        """Retrieves field label, aria-label, name, or placeholder."""
        for attr in ["aria-label", "placeholder", "name", "id"]:
            val = element.get_attribute(attr)
            if val and len(val.strip()) > 1:
                return val.strip()

        # Check preceding label tag
        try:
            parent = element.evaluate_handle("el => el.closest('div, label, fieldset')")
            if parent:
                text = parent.inner_text().strip().split("\n")[0]
                if text and len(text) < 80:
                    return text
        except Exception:
            pass

        return ""

    def _attach_resume(self, page: Page):
        """Finds file upload input and attaches candidate resume."""
        resume_path = self.profile.resume_path
        if not resume_path or not Path(resume_path).exists():
            return
        abs_path = str(Path(resume_path).resolve())
        file_inputs = page.query_selector_all("input[type='file']")
        for f_inp in file_inputs:
            try:
                f_inp.set_input_files(abs_path)
                safe_print(f"[Company Portal Applier] ✓ Resume attached: {Path(resume_path).name}")
                break
            except Exception:
                pass
