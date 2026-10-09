"""
Autonomous Submission Resolver & 5-Attempt Recovery Engine for Naukri.com.

Solves portal submission hindrances:
1. Network response interception (cloudgateway-workflow, apply-workflow, saveApply, cloudgateway-mynaukri).
2. ACP (Application Confirmation Page) navigation and banner verification.
3. Chatbot drawer (resume headline, recruiter prompts).
4. Recruiter screening questions (CTC, notice period, experience, dropdowns, radios).
5. Overlay / pop-up dismissal and JavaScript DOM direct dispatch.
6. Structured failure data collection when submission cannot be completed after 5 attempts.
"""

import os
import re
import json
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from playwright.sync_api import Page, BrowserContext, ElementHandle

from src.models import CandidateProfile, JobApplication, ApplicationStatus
from src.applier.question_solver import QuestionSolver

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(msg: str):
    """Safely prints message avoiding Windows charmap UnicodeEncodeError."""
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass


FAILURES_LOG_DIR = Path("config/logs")
FAILURES_LOG_FILE = FAILURES_LOG_DIR / "submission_failures.json"


class SubmissionResult:
    """Encapsulates the result of a multi-attempt application resolution."""

    def __init__(
        self,
        success: bool,
        attempt_used: int,
        status: ApplicationStatus,
        verification_source: str,
        notes: str = "",
        failure_data: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.attempt_used = attempt_used
        self.status = status
        self.verification_source = verification_source
        self.notes = notes
        self.failure_data = failure_data or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "attempt_used": self.attempt_used,
            "status": self.status.value,
            "verification_source": self.verification_source,
            "notes": self.notes,
            "failure_data": self.failure_data,
        }


class NaukriSubmissionResolver:
    """
    Actively resolves bot console submission flags and executes up to 5 strategic attempts
    to successfully apply and physically verify application status.
    """

    def __init__(self, profile: CandidateProfile):
        self.profile = profile
        self.solver = QuestionSolver(profile)
        FAILURES_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def resolve_submission(
        self,
        page: Page,
        company: str,
        job_title: str,
        job_url: str,
        dry_run: bool = False,
    ) -> SubmissionResult:
        """
        Executes up to 5 strategic attempts to submit and verify the application.
        If all attempts fail, collects comprehensive failure diagnostics.
        """
        safe_comp = re.sub(r"[^\w\-_\.]", "_", company)[:30]
        attempts_log: List[Dict[str, Any]] = []

        if dry_run:
            return SubmissionResult(
                success=True,
                attempt_used=0,
                status=ApplicationStatus.APPLIED,
                verification_source="DRY_RUN",
                notes="Dry run simulation only",
            )

        # -------------------------------------------------------------
        # Network Response Listener: monitors all application API endpoints
        # -------------------------------------------------------------
        network_signals: List[Dict[str, Any]] = []

        def on_response(resp):
            u = resp.url.lower()
            if any(k in u for k in [
                "apply-workflow",
                "saveapply",
                "cloudgateway-workflow",
                "cloudgateway-mynaukri",
                "applyjob",
                "jobapi/v2/apply",
                "myapply"
            ]):
                try:
                    text_snippet = ""
                    try:
                        text_snippet = resp.text()[:400]
                    except Exception:
                        pass
                    network_signals.append({
                        "url": resp.url,
                        "status": resp.status,
                        "body": text_snippet,
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception:
                    pass

        page.on("response", on_response)

        # =============================================================
        # ATTEMPT 1: Standard Direct 1-Click Apply & Instant Verification
        # =============================================================
        safe_print(f"[Resolver] -> Attempt 1: Standard 1-Click Apply for {company}...")
        self._dismiss_overlays(page)

        # Check if already applied before even clicking
        already_applied_elem = self._check_already_applied(page)
        if already_applied_elem:
            safe_print(f"[Resolver] ✓ Attempt 1 verified: Already applied on Naukri ({company}).")
            return SubmissionResult(
                success=True,
                attempt_used=1,
                status=ApplicationStatus.APPLIED,
                verification_source="DOM_ALREADY_APPLIED_PRE_CLICK",
                notes="Already applied previously on portal",
            )

        # Locate genuine Apply button (explicitly excluding company-site buttons)
        apply_btn = self._get_direct_apply_button(page)
        if apply_btn:
            try:
                apply_btn.scroll_into_view_if_needed()
                apply_btn.click()
                page.wait_for_timeout(2500)
            except Exception as e:
                attempts_log.append({"attempt": 1, "error": f"Click error: {e}"})

            # Check verification after click
            is_confirmed, source, note = self._verify_application_status(page, network_signals)
            if source == "QUOTA_EXCEEDED":
                safe_print(f"[Resolver] 🛑 Naukri Daily Application Quota Reached: {note}")
                return SubmissionResult(
                    success=False,
                    attempt_used=1,
                    status=ApplicationStatus.FAILED,
                    verification_source="QUOTA_EXCEEDED",
                    notes=note,
                )
            if is_confirmed:
                safe_print(f"[Resolver] ✓ Successfully submitted and verified in Attempt 1 via [{source}]: {company}")
                return SubmissionResult(
                    success=True,
                    attempt_used=1,
                    status=ApplicationStatus.APPLIED,
                    verification_source=source,
                    notes=note,
                )
        else:
            attempts_log.append({"attempt": 1, "error": "No direct apply button found"})

        # =============================================================
        # ATTEMPT 2: Chatbot Drawer & Resume Headline Prompt Handler
        # =============================================================
        safe_print(f"[Resolver] -> Attempt 2: Chatbot Drawer & Headline Prompt Handler for {company}...")
        drawer_acted = self._handle_chatbot_drawer(page)
        if drawer_acted:
            page.wait_for_timeout(3000)
            is_confirmed, source, note = self._verify_application_status(page, network_signals)
            if is_confirmed:
                safe_print(f"[Resolver] ✓ Successfully submitted and verified in Attempt 2 (Chatbot Drawer) via [{source}]: {company}")
                return SubmissionResult(
                    success=True,
                    attempt_used=2,
                    status=ApplicationStatus.APPLIED,
                    verification_source=f"DRAWER_{source}",
                    notes=f"Solved chatbot drawer headline: {note}",
                )
        else:
            attempts_log.append({"attempt": 2, "error": "No visible chatbot drawer inputs"})

        # =============================================================
        # ATTEMPT 3: Recruiter Screening Form & Multi-Step Questionnaire
        # =============================================================
        safe_print(f"[Resolver] -> Attempt 3: Recruiter Screening Questions Solver for {company}...")
        form_acted = self._handle_screening_questions(page)
        if form_acted:
            page.wait_for_timeout(3000)
            is_confirmed, source, note = self._verify_application_status(page, network_signals)
            if is_confirmed:
                safe_print(f"[Resolver] ✓ Successfully submitted and verified in Attempt 3 (Screening Questions) via [{source}]: {company}")
                return SubmissionResult(
                    success=True,
                    attempt_used=3,
                    status=ApplicationStatus.APPLIED,
                    verification_source=f"QUESTIONNAIRE_{source}",
                    notes=f"Solved recruiter screening questions: {note}",
                )
        else:
            attempts_log.append({"attempt": 3, "error": "No visible screening questions matched"})

        # =============================================================
        # ATTEMPT 4: Overlay & Pop-up Clearance + JavaScript Direct Dispatch
        # =============================================================
        safe_print(f"[Resolver] -> Attempt 4: Overlay Clearance & Direct JS Dispatch for {company}...")
        self._dismiss_overlays(page)
        js_acted = self._force_click_apply_js(page)
        if js_acted:
            page.wait_for_timeout(3000)
            # Re-check drawer and questions if opened by JS click
            self._handle_chatbot_drawer(page)
            self._handle_screening_questions(page)
            page.wait_for_timeout(2000)

            is_confirmed, source, note = self._verify_application_status(page, network_signals)
            if is_confirmed:
                safe_print(f"[Resolver] ✓ Successfully submitted and verified in Attempt 4 (JS Direct Dispatch) via [{source}]: {company}")
                return SubmissionResult(
                    success=True,
                    attempt_used=4,
                    status=ApplicationStatus.APPLIED,
                    verification_source=f"JS_DISPATCH_{source}",
                    notes=f"Force clicked via JS: {note}",
                )
        else:
            attempts_log.append({"attempt": 4, "error": "JS direct click could not find target element"})

        # =============================================================
        # ATTEMPT 5: Hard Server Status Re-verification & Cache Bypass
        # =============================================================
        safe_print(f"[Resolver] -> Attempt 5: Hard Server Refresh & State Verification for {company}...")
        try:
            # Check if any network response from attempt 1-4 already confirmed success
            for sig in network_signals:
                body = (sig.get("body") or "").lower()
                if any(w in body for w in ["successfully applied", "success", "applied", "status:200", "200"]):
                    safe_print(f"[Resolver] ✓ Attempt 5 verified from intercepted network telemetry: {company}")
                    return SubmissionResult(
                        success=True,
                        attempt_used=5,
                        status=ApplicationStatus.APPLIED,
                        verification_source="NETWORK_TELEMETRY_CONFIRMED",
                        notes=f"API verified 200: {sig.get('url')[:80]}",
                    )

            # Reload to check if backend marked it applied
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(3500)
            is_confirmed, source, note = self._verify_application_status(page, network_signals)
            if is_confirmed:
                safe_print(f"[Resolver] ✓ Successfully verified in Attempt 5 (Server Refresh Check) via [{source}]: {company}")
                return SubmissionResult(
                    success=True,
                    attempt_used=5,
                    status=ApplicationStatus.APPLIED,
                    verification_source=f"REFRESH_{source}",
                    notes=f"Verified post-reload: {note}",
                )
        except Exception as e:
            attempts_log.append({"attempt": 5, "error": f"Reload verification error: {e}"})

        # =============================================================
        # ALL 5 ATTEMPTS FAILED: Collect Full Failure Diagnostics
        # =============================================================
        safe_print(f"[Resolver] ❌ Submission could not be completed/verified after 5 attempts for {company}.")
        screenshot_path = f"naukri_unconfirmed_{safe_comp}.png"
        try:
            page.screenshot(path=screenshot_path)
        except Exception:
            pass

        failure_record = self._collect_failure_data(
            page=page,
            company=company,
            job_title=job_title,
            job_url=job_url,
            screenshot_path=screenshot_path,
            attempts_log=attempts_log,
            network_signals=network_signals,
        )

        return SubmissionResult(
            success=False,
            attempt_used=5,
            status=ApplicationStatus.UNKNOWN,
            verification_source="FAILED_ALL_ATTEMPTS",
            notes=f"Failed after 5 attempts. Diagnostics logged to {FAILURES_LOG_FILE}",
            failure_data=failure_record,
        )

    # -----------------------------------------------------------------
    # Helper: Detect genuine Direct Apply Button vs Company Site Button
    # -----------------------------------------------------------------
    def _get_direct_apply_button(self, page: Page) -> Optional[ElementHandle]:
        """
        Returns the genuine Direct 1-Click Apply button.
        Prevents parent wrappers or company site buttons from colliding.
        """
        # Exact ID match
        btn = page.query_selector("button#apply-button")
        if btn and btn.is_visible():
            return btn

        # Class match on button tags
        btn = page.query_selector("button.apply-button")
        if btn and btn.is_visible():
            return btn

        # Look for buttons whose text is exactly "Apply"
        all_buttons = page.query_selector_all("button")
        for b in all_buttons:
            try:
                if not b.is_visible():
                    continue
                txt = b.inner_text().strip().lower()
                b_id = (b.get_attribute("id") or "").lower()
                b_class = (b.get_attribute("class") or "").lower()

                # Exclude company site button
                if "company" in txt or "company-site" in b_id or "company-site" in b_class:
                    continue

                if txt == "apply":
                    return b
            except Exception:
                continue

        return None

    # -----------------------------------------------------------------
    # Helper: Comprehensive Verification Checker
    # -----------------------------------------------------------------
    def _verify_application_status(
        self, page: Page, network_signals: List[Dict[str, Any]]
    ) -> Tuple[bool, str, str]:
        """
        Evaluates whether an application has been successfully submitted via:
        1. ACP (Application Confirmation Page) URL navigation (/myapply/showAcp, saveApply)
        2. ACP Confirmation Banners ("You have successfully applied", "Apply Confirmation")
        3. DOM badges (#already-applied, .already-applied, "Applied")
        4. Intercepted Network Responses (apply-workflow, saveApply)
        """
        current_url = (page.url or "").lower()

        # 1. Check ACP URL Navigation
        if any(k in current_url for k in ["/myapply/showacp", "showacp", "saveapply", "applyconfimation"]):
            # Confirm if it was direct apply confirmation or company site redirect
            page_text = ""
            try:
                page_text = page.evaluate("() => document.body ? document.body.innerText : ''").lower()
            except Exception:
                pass

            if "redirected to the company website" in page_text:
                return False, "REDIRECTED_TO_COMPANY_SITE", "Redirected to external company website"

            return True, "ACP_URL_NAVIGATION", f"Landed on ACP page: {page.url}"

        # 2. Check ACP Confirmation Banners in DOM
        acp_banner = page.query_selector(
            ":has-text('You have successfully applied'), :has-text('Apply Confirmation'), .acp-title, .apply-message, .success-msg"
        )
        if acp_banner and acp_banner.is_visible():
            return True, "ACP_DOM_BANNER", "Application confirmation banner displayed on screen"

        # 3. Check In-page Already Applied / Applied badge
        applied_badge = page.query_selector(
            "#already-applied, .already-applied, span:has-text('Applied'), button:has-text('Applied')"
        )
        if applied_badge and applied_badge.is_visible():
            badge_text = applied_badge.inner_text().strip()
            if "applied" in badge_text.lower():
                return True, "DOM_APPLIED_BADGE", f"Badge shows '{badge_text}'"

        # 4. Check Intercepted Network Responses
        for sig in network_signals:
            body = (sig.get("body") or "").lower()
            if "quota" in body and "exceeded" in body:
                return False, "QUOTA_EXCEEDED", "Daily quota of jobs exceeded on Naukri (Resets tomorrow)"

            if sig.get("status") in [200, 201]:
                if any(w in body for w in ["successfully applied", "appid", "success", "applied", "status:200", "200"]):
                    return True, "NETWORK_API_OK", f"Backend 200 response from {sig.get('url')[:60]}"

        return False, "UNCONFIRMED", "Application not verified on portal"

    def _check_already_applied(self, page: Page) -> Optional[ElementHandle]:
        """Checks if the page already indicates the candidate has applied."""
        badge = page.query_selector("#already-applied, .already-applied")
        if badge and badge.is_visible():
            return badge
        text_badge = page.query_selector(":has-text('Already applied')")
        if text_badge and text_badge.is_visible():
            return text_badge
        return None

    # -----------------------------------------------------------------
    # Helper: Chatbot Drawer Handler (Attempt 2)
    # -----------------------------------------------------------------
    def _handle_chatbot_drawer(self, page: Page) -> bool:
        """
        Fills all recruiter screening questions inside Naukri's chatbot drawer
        (._chatBotContainer, .bot-container, .drawer-container).
        Handles:
        1. Single-choice radio pills ('Yes', 'Agree', 'Immediate', 'Skip this question').
        2. Resume headline and text/number inputs.
        3. Dropdowns.
        4. Clicks 'Save' / 'Send' in a multi-step loop until conversation completes.
        """
        acted_any = False

        for step in range(6):
            step_acted = False
            try:
                # Find active visible chatbot / drawer container
                container = page.query_selector("._chatBotContainer, .bot-container, [class*='chatbot'], .drawer-container, div[role='dialog']")
                if not container or not container.is_visible():
                    # If drawer closed or not visible, stop
                    break

                # 1. Answer Radio Buttons or clickable option pills inside drawer
                radio_clicked = page.evaluate("""() => {
                    const root = document.querySelector("._chatBotContainer, .bot-container, [class*='chatbot'], .drawer-container, div[role='dialog']") || document;
                    
                    // Look for unchecked native radio inputs first
                    const radios = Array.from(root.querySelectorAll("input[type='radio']")).filter(r => !r.checked && r.offsetHeight > 0);
                    if (radios.length > 0) {
                        // Look for a positive option ('Yes', 'Agree', 'Immediate', 'Skip this question')
                        let picked = radios.find(r => {
                            const lbl = (r.closest('label, div')?.innerText || '').toLowerCase();
                            return lbl.includes('yes') || lbl.includes('agree') || lbl.includes('immediate');
                        });
                        if (!picked) {
                            picked = radios.find(r => (r.closest('label, div')?.innerText || '').toLowerCase().includes('skip'));
                        }
                        if (!picked) picked = radios[0];
                        picked.click();
                        return true;
                    }

                    // Look for styled clickable radio/bubble pills (div, label, span, li)
                    const pills = Array.from(root.querySelectorAll("label, div[class*='radio'], div[class*='option'], li[class*='option'], [class*='pill']")).filter(el => {
                        const txt = (el.innerText || '').trim().toLowerCase();
                        return (txt === 'yes' || txt === 'no' || txt.includes('skip this question') || txt.includes('agree')) && el.offsetHeight > 0;
                    });

                    if (pills.length > 0) {
                        const bestPill = pills.find(p => {
                            const t = (p.innerText || '').toLowerCase();
                            return t === 'yes' || t.includes('agree');
                        }) || pills.find(p => (p.innerText || '').toLowerCase().includes('skip')) || pills[0];
                        
                        bestPill.click();
                        return true;
                    }

                    return false;
                }""")
                if radio_clicked:
                    step_acted = True
                    acted_any = True
                    page.wait_for_timeout(800)

                # 2. Text / Headline inputs inside drawer
                text_inputs = page.query_selector_all(
                    "._chatBotContainer input[type='text'], [class*='chatbot'] input[type='text'], [class*='drawer'] input[type='text'], textarea, input[placeholder*='headline'], input[placeholder*='message']"
                )
                for inp in text_inputs:
                    if inp.is_visible() and not (inp.input_value() or "").strip():
                        meta = self._get_element_context(inp)
                        if any(w in meta for w in ["headline", "summary", "profile"]):
                            headline = "Data Analyst with experience in Python, SQL, Power BI dashboards, EDA, and business metrics."
                            inp.fill(headline)
                        else:
                            val = self._solve_field_value(meta)
                            inp.fill(val)
                        page.wait_for_timeout(500)
                        step_acted = True
                        acted_any = True

                # 3. Numeric inputs inside drawer (CTC, notice period, experience)
                num_inputs = page.query_selector_all("._chatBotContainer input[type='number'], [class*='chatbot'] input[type='number']")
                for inp in num_inputs:
                    if inp.is_visible() and not (inp.input_value() or "").strip():
                        meta = self._get_element_context(inp)
                        val = self._solve_field_value(meta)
                        inp.fill(val)
                        page.wait_for_timeout(400)
                        step_acted = True
                        acted_any = True

                # 4. Dropdowns inside drawer
                selects = page.query_selector_all("._chatBotContainer select, [class*='chatbot'] select")
                for s in selects:
                    if s.is_visible():
                        options = s.query_selector_all("option")
                        for opt in options[1:]:
                            opt_text = (opt.inner_text() or "").lower()
                            if any(w in opt_text for w in ["yes", "15", "immediate", "graduate", "b.tech", "1 year"]):
                                s.select_option(value=opt.get_attribute("value"))
                                step_acted = True
                                acted_any = True
                                break

                # 5. Click Save, Send, Submit, or Next action button in Drawer
                btn_clicked = page.evaluate("""() => {
                    const root = document.querySelector("._chatBotContainer, .bot-container, [class*='chatbot'], .drawer-container, div[role='dialog']") || document;
                    const candidates = Array.from(root.querySelectorAll(".sendMsg, [class*='sendMsg'], .save-btn, [class*='save'], button, div.send:not(.disabled), a")).filter(el => {
                        const txt = (el.innerText || '').trim().toLowerCase();
                        return (txt === 'save' || txt === 'send' || txt === 'submit' || txt === 'continue' || txt === 'next' || txt === 'i am interested') && el.offsetHeight > 0 && !el.disabled;
                    });
                    if (candidates.length > 0) {
                        const target = candidates[candidates.length - 1];
                        target.click();
                        return true;
                    }
                    return false;
                }""")
                if btn_clicked:
                    step_acted = True
                    acted_any = True
                    page.wait_for_timeout(2000)

                # Check if drawer close icon should be clicked if finished
                if not step_acted:
                    close_btn = page.query_selector(".drawer-container .crossIcon, .drawer .crossIcon, [class*='chatbot'] .crossIcon")
                    if close_btn and close_btn.is_visible() and acted_any:
                        close_btn.click()
                        page.wait_for_timeout(1000)
                    break

            except Exception as e:
                safe_print(f"[Resolver] Chatbot drawer step note: {e}")
                break

        return acted_any

    # -----------------------------------------------------------------
    # Helper: Screening Questions Handler (Attempt 3)
    # -----------------------------------------------------------------
    def _handle_screening_questions(self, page: Page) -> bool:
        """
        Fills recruiter screening inputs, radios, selects across up to 4 questionnaire steps.
        """
        acted = False
        for step in range(4):
            step_acted = False
            try:
                # 1. Text & Number Inputs
                inputs = page.query_selector_all("input[type='text'], input[type='number'], textarea")
                for inp in inputs:
                    if not inp.is_visible() or (inp.input_value() or "").strip():
                        continue
                    meta = self._get_element_context(inp)
                    val = self._solve_field_value(meta)
                    inp.fill(val)
                    page.wait_for_timeout(300)
                    step_acted = True
                    acted = True

                # 2. Radio buttons
                radios = page.query_selector_all("input[type='radio']")
                for r in radios:
                    if not r.is_visible() or r.is_checked():
                        continue
                    meta = self._get_element_context(r)
                    if any(w in meta for w in ["yes", "agree", "authorized", "immediate", "walk-in", "walk in", "part time", "full time"]):
                        r.click()
                        step_acted = True
                        acted = True

                # 3. Dropdowns
                selects = page.query_selector_all("select")
                for s in selects:
                    if not s.is_visible():
                        continue
                    options = s.query_selector_all("option")
                    for opt in options[1:]:
                        opt_text = (opt.inner_text() or "").lower()
                        if any(w in opt_text for w in ["yes", "15", "immediate", "graduate", "b.tech", "1 year"]):
                            s.select_option(value=opt.get_attribute("value"))
                            step_acted = True
                            acted = True
                            break

                # 4. Click Submit / Next / Continue button
                submit_btn = page.query_selector(
                    "button:has-text('Submit'), button:has-text('Save'), button:has-text('Continue'), button:has-text('Next')"
                )
                if submit_btn and submit_btn.is_visible() and not submit_btn.is_disabled():
                    submit_btn.click()
                    page.wait_for_timeout(2000)
                    step_acted = True
                    acted = True

                if not step_acted:
                    break
            except Exception:
                break

        return acted

    def _solve_field_value(self, meta: str) -> str:
        """Determines best field value based on field metadata."""
        m = meta.lower()
        if any(w in m for w in ["expected ctc", "expected salary", "desired ctc", "expected package"]):
            return "6"
        elif any(w in m for w in ["current ctc", "present ctc", "current salary", "present salary"]):
            return "0"
        elif any(w in m for m_val in ["ctc", "salary", "package", "compensation"] if m_val in m):
            return "6"
        elif any(w in m for w in ["notice", "days", "joining", "available"]):
            return "0"
        elif any(w in m for w in ["experience", "years", "total exp", "relevant exp"]) or re.search(r"\bexp\b", m):
            return "0"
        elif any(w in m for w in ["city", "location", "residing"]):
            return "Gurugram"
        elif any(w in m for w in ["education", "degree", "qualification"]):
            return "B.Tech CSE"
        elif any(w in m for w in ["college", "university", "institute"]):
            return "JECRC UNIVERSITY"
        elif any(w in m for w in ["headline", "summary"]):
            return "Data Analyst with experience in Python, SQL, Power BI dashboards, EDA, and business metrics."
        elif any(w in m for w in ["walk in", "part time", "full time", "shift", "relocate", "laptop", "pan", "authorized"]):
            return "Yes"
        return self.solver.answer_text_question(meta) or "Yes"

    def _get_element_context(self, el: ElementHandle) -> str:
        """Extracts identifying textual context for an input element."""
        try:
            return " ".join([
                el.get_attribute("placeholder") or "",
                el.get_attribute("name") or "",
                el.get_attribute("id") or "",
                el.get_attribute("aria-label") or "",
                el.evaluate("e => e.closest('label, div')?.innerText || ''"),
            ]).lower()
        except Exception:
            return ""

    # -----------------------------------------------------------------
    # Helper: Overlay Dismissal (Attempt 4)
    # -----------------------------------------------------------------
    def _dismiss_overlays(self, page: Page) -> None:
        """Dismisses any promotional dialogs, banners, or contest overlays."""
        selectors = [
            ".crossIcon",
            "[class*='crossIcon']",
            "button[aria-label='Close']",
            ".modal .close",
            "button:has-text('✕')",
            "div[role='dialog'] button:has-text('✕')",
        ]
        for sel in selectors:
            try:
                for el in page.query_selector_all(sel):
                    if el.is_visible():
                        el.click()
                        page.wait_for_timeout(500)
            except Exception:
                pass

    def _force_click_apply_js(self, page: Page) -> bool:
        """Directly dispatches a JavaScript click to the apply button."""
        try:
            return page.evaluate("""() => {
                const btn = document.querySelector('button#apply-button, button.apply-button');
                if (btn) {
                    btn.scrollIntoView();
                    btn.click();
                    return true;
                }
                const allButtons = Array.from(document.querySelectorAll('button'));
                for (const b of allButtons) {
                    const txt = (b.innerText || '').trim().toLowerCase();
                    if (txt === 'apply' && !b.id.includes('company-site')) {
                        b.scrollIntoView();
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
        except Exception:
            return False

    # -----------------------------------------------------------------
    # Diagnostic Failure Data Collection
    # -----------------------------------------------------------------
    def _collect_failure_data(
        self,
        page: Page,
        company: str,
        job_title: str,
        job_url: str,
        screenshot_path: str,
        attempts_log: List[Dict[str, Any]],
        network_signals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Collects detailed failure telemetry and stores it in submission_failures.json.
        """
        timestamp = datetime.now().isoformat()
        current_url = page.url

        # Check visible open modals or drawers
        modals_snapshot = []
        try:
            modals_snapshot = page.evaluate("""() => {
                const items = [];
                document.querySelectorAll('.modal, .drawer, [class*="drawer"], [role="dialog"]').forEach(el => {
                    if (el.offsetWidth > 0 && el.offsetHeight > 0) {
                        items.push({
                            className: el.className,
                            innerText: el.innerText ? el.innerText.slice(0, 300) : ''
                        });
                    }
                });
                return items;
            }""")
        except Exception:
            pass

        # Check unfilled input fields
        unfilled_inputs = []
        try:
            unfilled_inputs = page.evaluate("""() => {
                const list = [];
                document.querySelectorAll('input, textarea, select').forEach(el => {
                    if (el.offsetWidth > 0 && el.offsetHeight > 0) {
                        list.push({
                            tag: el.tagName,
                            type: el.type,
                            placeholder: el.placeholder || '',
                            name: el.name || '',
                            value: el.value || '',
                            label: el.closest('label, div')?.innerText?.slice(0, 100) || ''
                        });
                    }
                });
                return list;
            }""")
        except Exception:
            pass

        record = {
            "id": f"FAIL-{company[:4].upper()}-{int(time.time())}",
            "timestamp": timestamp,
            "company": company,
            "job_title": job_title,
            "job_url": job_url,
            "final_url": current_url,
            "screenshot": screenshot_path,
            "attempts_log": attempts_log,
            "network_signals_count": len(network_signals),
            "network_signals_sample": network_signals[-3:],
            "active_modals": modals_snapshot,
            "unfilled_inputs": unfilled_inputs,
            "failure_summary": (
                f"Application could not be confirmed for {company} - {job_title}. "
                f"Modals detected: {len(modals_snapshot)}, Unfilled fields: {len(unfilled_inputs)}"
            ),
        }

        # Append to JSON log file
        try:
            existing_data = []
            if FAILURES_LOG_FILE.exists():
                try:
                    with open(FAILURES_LOG_FILE, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                except Exception:
                    existing_data = []

            existing_data.append(record)
            with open(FAILURES_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)
            safe_print(f"[Resolver] 📝 Failure telemetry logged to {FAILURES_LOG_FILE}")
        except Exception as e:
            safe_print(f"[Resolver Warning] Could not write to failure log: {e}")

        return record
