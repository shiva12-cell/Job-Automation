"""
Autonomous Job Engine & 4-Hour Scheduler.
Executes the full pipeline:
1. Search & filter jobs with >= 70% skill match (using fixed resume).
2. Auto-apply to qualified jobs.
3. Update Google Sheets and local Excel.
4. Scan Gmail for application updates & recruiter responses.
5. Send automated 4-day polite follow-up emails.
"""

import time
import uuid
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import deque

from src.config import get_config, load_candidate_profile
from src.google_services.auth import GoogleAuthManager
from src.google_services.sheets_manager import SheetsManager
from src.google_services.gmail_tracker import GmailTracker
from src.excel_manager import ExcelManager
from src.matcher import SkillMatcher
from src.follow_up_sender import FollowUpSender
from src.applier.factory import get_applier_for_url
from src.models import CandidateProfile, JobApplication, ApplicationStatus
from src.state_manager import seen_manager


class AutonomousEngine:
    """Singleton orchestrator for scheduled and triggered job application runs."""

    def __init__(self, excel_mgr: Optional[ExcelManager] = None, seen_mgr: Optional[Any] = None):
        self.cfg = get_config()
        self.profile = load_candidate_profile()
        self.matcher = SkillMatcher(self.profile, threshold_pct=65.0)
        self.excel_mgr = excel_mgr or ExcelManager()
        self.seen_mgr = seen_mgr or seen_manager

        self.autopilot_active = True
        self.is_executing = False
        self.interval_minutes = 30
        self.last_run_time: Optional[datetime] = None
        self.next_run_time: Optional[datetime] = None

        self.logs: deque = deque(maxlen=200)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        existing_rows = self.excel_mgr.get_all_rows()
        initial_total = len(existing_rows)

        synced_count = self.seen_mgr.sync_from_excel(self.excel_mgr)
        cached_total = len(self.seen_mgr.data.get("seen_jobs", {}))

        self.stats = {
            "total_applied": initial_total,
            "seen_jobs_cached": cached_total,
            "matched_65_pct": 0,
            "interviews_scheduled": 0,
            "rejected": 0,
            "follow_ups_sent": 0,
            "last_cycle_status": "Idle",
            "avg_jobs_per_cycle": float(initial_total) if initial_total > 0 else 0.0,
            "avg_jobs_per_hour": 0.0,
            "cycles_completed": 1 if initial_total > 0 else 0,
            "cycle_duration_minutes": 30,
            "cycle_end_deadline": None,
            "active_time_remaining_seconds": 0,
            "category_counts": self.excel_mgr.get_category_stats(),
        }

        # Initialize Google Services if configured
        self.auth_mgr: Optional[GoogleAuthManager] = None
        self.sheets_mgr: Optional[SheetsManager] = None
        self.tracker: Optional[GmailTracker] = None
        self.follow_up_mgr: Optional[FollowUpSender] = None
        self.notifier: Optional[Any] = None

        self._init_google()
        self.log(f"Autonomous Engine initialized. 65% skill threshold active. Cycle: 30 minutes. Loaded {initial_total} applications. Seen cache: {cached_total} jobs (smart pagination active).")

    def reload_profile(self):
        """Reloads the active candidate profile and refreshes the skill matcher."""
        self.profile = load_candidate_profile()
        self.matcher = SkillMatcher(self.profile, threshold_pct=65.0)
        self.log(f"Candidate profile reloaded: {self.profile.personal_info.full_name} ({self.profile.personal_info.current_title}) with {len(self.matcher.candidate_skills)} skills.")

    def _init_google(self):
        try:
            google_cfg = self.cfg.get("google", {})
            creds_file = google_cfg.get("client_secrets_file", "config/credentials/credentials.json")
            token_file = google_cfg.get("token_file", "config/credentials/token.json")
            sheet_id = google_cfg.get("spreadsheet_id", "")

            self.auth_mgr = GoogleAuthManager(credentials_file=creds_file, token_file=token_file)
            if sheet_id:
                sheets_client = self.auth_mgr.get_sheets_client()
                self.sheets_mgr = SheetsManager(sheets_client, spreadsheet_id=sheet_id)

            gmail_service = self.auth_mgr.get_gmail_service()
            if self.sheets_mgr:
                self.tracker = GmailTracker(gmail_service, self.sheets_mgr)
            self.follow_up_mgr = FollowUpSender(gmail_service, self.profile, self.sheets_mgr, self.excel_mgr)

            from src.self_notifier import SelfNotifier
            self.notifier = SelfNotifier(gmail_service, self.profile, label_name="Job Applied")
            self.log("✓ Self-notifier armed: confirmations will be sent to yourself and filed under 'Job Applied' folder.")
        except Exception as e:
            self.log(f"[Notice] Google services not fully linked yet: {e}")

    def log(self, message: str) -> None:
        """Appends a timestamped log to the circular buffer."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        with self._lock:
            self.logs.append(entry)
        try:
            print(entry)
        except UnicodeEncodeError:
            print(entry.encode("ascii", "replace").decode("ascii"))

    def run_pipeline(
        self,
        max_limit: int = 50,
        keyword: str = "data analyst",
        duration_minutes: int = 30,
        dry_run: bool = False,
        headless: bool = True,
        enable_indeed: bool = False,
        location: str = "any",
        min_salary_lpa: float = 0.0,
        max_salary_lpa: float = 99.0,
        experience_years: int = 0,
        job_age_days: int = 0,
        work_mode: str = "all",
        sort_by: str = "relevance",
        apply_mode: str = "all"
    ) -> Dict[str, Any]:
        """
        Executes an application cycle:
        - Scrapes jobs for requested keyword(s) or rotates across target keywords:
          (Data Analyst, Business Analyst, AI Product Owner, Product Management, B.Tech CSE Analyst)
        - Filters by target location and salary range on Naukri
        - apply_mode filter:
          * 'all': Process both 1-click Direct Apply and Apply on Company Website
          * 'direct_only': Strictly 1-click Direct Apply only
          * 'company_site_only': Strictly Apply on Company Website (logged to ACW(Date) sheet)
        - Sorts candidate jobs according to user preference (date, relevance, or package asc/desc)
        - Runs strictly for up to `duration_minutes` (timer limit)
        - Stops exactly when `max_limit` applications are submitted (default 50)
        - Runs silently in background (headless=True) without popping up browser windows
        """
        if self.is_executing:
            self.log("Pipeline cycle already in progress. Skipping duplicate trigger.")
            return {"status": "already_running"}

        self.is_executing = True
        self.stats["last_cycle_status"] = "Running"
        self.last_run_time = datetime.now()
        self.next_run_time = self.last_run_time + timedelta(minutes=self.interval_minutes)

        # Setup duration timer
        cycle_start_time = time.time()
        max_duration_seconds = max(duration_minutes, 1) * 60
        deadline = cycle_start_time + max_duration_seconds
        self.stats["cycle_duration_minutes"] = duration_minutes
        self.stats["cycle_end_deadline"] = deadline

        # Target candidate keywords (Data Analyst, Business Analyst, AI Product Owner, Product Management, B.Tech CSE Analyst)
        DEFAULT_KEYWORDS = [
            "data analyst",
            "business analyst",
            "ai product owner",
            "product management",
            "analyst"
        ]
        clean_kw = (keyword or "").strip().lower()
        if clean_kw in ["all", "rotate", "any", "all matching", "all roles", "auto", ""]:
            search_keywords = DEFAULT_KEYWORDS
        elif "," in clean_kw:
            search_keywords = [k.strip() for k in clean_kw.split(",") if k.strip()]
        else:
            search_keywords = [keyword.strip()]

        self.stats["current_keyword"] = ", ".join(search_keywords)
        self.stats["current_location"] = location
        self.stats["current_salary"] = f"{min_salary_lpa} - {max_salary_lpa} LPA"

        self.log("=" * 60)
        self.log(f"🚀 STARTING CYCLE | Keywords: {search_keywords} | Location: {location} | Package: {min_salary_lpa}-{max_salary_lpa} LPA | Cap: {max_limit} | Timer: {duration_minutes} Mins | Headless: {headless}")
        self.log("=" * 60)

        results = {
            "applied": 0,
            "emails_synced": 0,
            "follow_ups": 0,
        }

        try:
            # 1. Sync Gmail communication to Google Sheets & Excel
            if self.tracker and self.sheets_mgr:
                self.log("📬 Scanning Gmail for job application responses & status changes...")
                sync_stats = self.tracker.sync_to_sheets(lookback_days=30)
                self.log(f"Gmail sync complete: {sync_stats.get('updated', 0)} updated, {sync_stats.get('added', 0)} new detected.")
                results["emails_synced"] = sync_stats.get("updated", 0) + sync_stats.get("added", 0)

                # Sync local Excel with latest Google Sheet data
                all_apps = [app for _, app in self.sheets_mgr.get_all_applications()]
                self.excel_mgr.sync_from_applications(all_apps)
                self.log("✓ Google Sheets and local Excel tracker synchronized.")

                # Recalculate stats
                self.stats["total_applied"] = len(all_apps)
                self.stats["interviews_scheduled"] = sum(1 for a in all_apps if a.status == ApplicationStatus.INTERVIEW)
                self.stats["rejected"] = sum(1 for a in all_apps if a.status == ApplicationStatus.REJECTED)

            # 2. Check and send 4-Day follow-ups
            if self.follow_up_mgr and self.sheets_mgr:
                self.log("⏳ Checking for applications pending >= 4 days for polite follow-up...")
                apps = [a for _, a in self.sheets_mgr.get_all_applications()]
                sent_followups = self.follow_up_mgr.process_and_send_follow_ups(apps, dry_run=dry_run)
                self.stats["follow_ups_sent"] += sent_followups
                results["follow_ups"] = sent_followups
                if sent_followups > 0:
                    self.log(f"✓ Sent {sent_followups} automated 4-day follow-up emails via Gmail.")

            # 3. Live Job Search across target keywords on Naukri (Primary Engine)
            from src.scraper import scrape_naukri_live_jobs, scrape_indeed_live_jobs

            all_target_jobs: List[Dict[str, Any]] = []
            seen_job_urls = set()

            for kw in search_keywords:
                if time.time() >= deadline:
                    self.log(f"⏰ Run timer expired ({duration_minutes} mins reached). Proceeding with collected jobs.")
                    break

                mode_desc = "Direct Apply Only" if apply_mode == "direct_only" else ("Company Site Only" if apply_mode == "company_site_only" else "All Apply Pathways")
                self.log(f"🔍 [Naukri Engine] Scanning live postings for '{kw}' [Location: {location} | Package: {min_salary_lpa}-{max_salary_lpa} LPA] (Mode: {mode_desc})...")
                naukri_jobs = scrape_naukri_live_jobs(
                    keywords=kw,
                    min_jobs=max(max_limit * 2, 40),
                    direct_only=(apply_mode == "direct_only"),
                    apply_mode=apply_mode,
                    location=location,
                    min_lpa=min_salary_lpa,
                    max_lpa=max_salary_lpa,
                    experience_years=experience_years,
                    job_age_days=job_age_days,
                    work_mode=work_mode,
                    sort_by=sort_by
                )
                for j in naukri_jobs:
                    u = j.get("url")
                    if u and u not in seen_job_urls:
                        seen_job_urls.add(u)
                        all_target_jobs.append(j)

                if enable_indeed:
                    if time.time() >= deadline:
                        break
                    self.log(f"🔍 [Indeed Engine] Scanning live postings for '{kw}'...")
                    indeed_jobs = scrape_indeed_live_jobs(keywords=kw, min_jobs=20)
                    for j in indeed_jobs:
                        u = j.get("url")
                        if u and u not in seen_job_urls:
                            seen_job_urls.add(u)
                            all_target_jobs.append(j)

            # SORTING RULE: Respect apply pathway mode and user sort preference
            if apply_mode == "company_site_only":
                all_target_jobs.sort(key=lambda j: (0 if not j.get("is_direct_apply") else 1, -j.get("min_lpa", 0.0) if sort_by == "salary_desc" else (j.get("min_lpa", 0.0) if sort_by == "salary_asc" else 0)))
            elif apply_mode == "direct_only":
                all_target_jobs.sort(key=lambda j: (0 if j.get("is_direct_apply", True) else 1, -j.get("min_lpa", 0.0) if sort_by == "salary_desc" else (j.get("min_lpa", 0.0) if sort_by == "salary_asc" else 0)))
            else:
                if sort_by == "salary_desc":
                    all_target_jobs.sort(key=lambda j: -j.get("min_lpa", 0.0))
                elif sort_by == "salary_asc":
                    all_target_jobs.sort(key=lambda j: j.get("min_lpa", 0.0))

            direct_count = len([j for j in all_target_jobs if j.get("is_direct_apply", True)])
            company_site_count = len(all_target_jobs) - direct_count
            mode_lbl = "Direct 1-Click Apply Only" if apply_mode == "direct_only" else ("Company Site Only" if apply_mode == "company_site_only" else "All Apply Pathways")
            self.log(f"📊 Collected {len(all_target_jobs)} total candidate postings (Direct: {direct_count}, Company Site: {company_site_count} | Mode: {mode_lbl}).")

            applied_in_cycle = 0
            naukri_applied_count = 0
            indeed_applied_count = 0

            for job in all_target_jobs:
                # Timer Check
                if time.time() >= deadline:
                    self.log(f"⏰ Session duration timer limit reached ({duration_minutes} minutes elapsed). Stopping cycle cleanly.")
                    break

                title = job.get("title", "")
                desc = job.get("description", "")
                url = job.get("url", "")
                comp = job.get("company", "")
                is_naukri = "naukri" in url.lower()
                platform_label = "Naukri.com" if is_naukri else "Indeed (India)"

                # FAST CACHE CHECK: If already processed in prior cycle, skip immediately
                if self.seen_mgr.is_seen(url):
                    self.log(f"⚡ [Seen Cache] Bypassed '{title}' at {comp} (already processed in prior cycle).")
                    continue

                # Check if this is a company site job
                is_company_site_job = (job.get("is_direct_apply") is False)

                if is_company_site_job and apply_mode == "direct_only":
                    self.seen_mgr.record_job(url, comp, title, "SKIPPED_COMPANY_SITE", 0.0)
                    self.log(f"⏩ Skipped '{title}' at {comp}: 'Apply on company website' is written. Focused exclusively on Direct Apply.")
                    continue

                # Pre-filter Walk-in interviews (which do not possess online 1-click apply buttons)
                title_lower = title.lower()
                if any(w in title_lower for w in ["walk-in", "walk in", "walkin"]):
                    self.seen_mgr.record_job(url, comp, title, "SKIPPED_WALKIN", 0.0)
                    self.log(f"⏩ Skipped Walk-in event '{title}' at {comp} (offline venue / no online direct apply).")
                    continue

                # STRICT RULE 1: Exact skill match (>=65%) & experience (0-2 yrs) & chance calculation
                is_qualified, match_pct, matched_skills, chance = self.matcher.is_match(title, desc)
                self.log(f"Evaluating: {comp} - '{title}' [{platform_label}] | Match: {match_pct}% | Chance: {chance}")

                if not is_qualified:
                    self.seen_mgr.record_job(url, comp, title, "SKIPPED_LOW_MATCH", match_pct)
                    self.log(f"⏩ Skipped '{title}' at {comp}: Match {match_pct}% is below 65% threshold or outside 0-2 yrs exp.")
                    continue

                # STRICT RULE 2: Anti-Duplicate (Never apply again to same company + same designation)
                already_in_excel = self.excel_mgr.is_already_applied(comp, title)
                already_in_sheets = self.sheets_mgr.is_already_applied(comp, title) if self.sheets_mgr else False
                if already_in_excel or already_in_sheets:
                    self.seen_mgr.record_job(url, comp, title, "APPLIED", match_pct)
                    self.log(f"🛡️ PREVENTED DUPLICATE: Already applied previously to {comp} for '{title}'. Skipping.")
                    continue

                if self.excel_mgr.is_already_in_manual(comp, title):
                    self.seen_mgr.record_job(url, comp, title, "MANUAL_SAVED", match_pct)
                    self.log(f"ℹ️ Already logged in 'Manual' sheet for {comp} ('{title}'). Skipping.")
                    continue

                self.stats["matched_65_pct"] += 1
                self.log(f"🎯 QUALIFIED ({match_pct}% >= 65% | Chance: {chance})! Evaluating apply pathway for {comp} on {platform_label}...")

                # Apply using Naukri / Indeed / ATS / Company Portal Applier
                applier = get_applier_for_url(url, self.profile, headless=headless)
                submission_result = None
                if applier and not dry_run:
                    try:
                        submission_result = applier.apply(url, dry_run=False, apply_mode=apply_mode)
                    except Exception as err:
                        self.log(f"[Notice] Applier submission note: {err}")

                # Handle skipped postings (e.g. filtered out by pathway on detail page)
                if submission_result and submission_result.status == ApplicationStatus.SKIPPED:
                    self.seen_mgr.record_job(url, comp, title, "SKIPPED_PATHWAY", match_pct)
                    self.log(f"⏩ {submission_result.notes} for {comp} ('{title}').")
                    continue

                # Dedicated handling for 'Apply on Company Website' jobs:
                # Creates and updates dedicated ACW(Date) worksheet every time!
                is_company_site_result = (
                    is_company_site_job or
                    (submission_result and submission_result.platform and "company site" in submission_result.platform.lower()) or
                    (submission_result and "company site" in (submission_result.notes or "").lower()) or
                    (submission_result and submission_result.job_url and "naukri.com" not in submission_result.job_url.lower())
                )

                if is_company_site_result:
                    target_portal_url = (submission_result.job_url if submission_result and submission_result.job_url else url)
                    is_verified_submission = (submission_result and submission_result.status == ApplicationStatus.APPLIED)

                    if not is_verified_submission:
                        # DO NOT copy unfilled applications to sheets!
                        # Keep tracker clean until automated submission actually succeeds.
                        self.seen_mgr.record_job(url, comp, title, "ACW_UNFILLED", match_pct)
                        self.log(f"⏸️ External Company Site ({match_pct}% | Chance: {chance}): Form requires manual verification or credentials on external portal ({target_portal_url}). Skipped copying to tracker until filled.")
                        continue

                    acw_app = submission_result or JobApplication(
                        app_id=f"ACW-{comp[:3].upper()}-{int(time.time()) % 10000}-{uuid.uuid4().hex[:4].upper()}",
                        date_applied=datetime.now().strftime("%Y-%m-%d"),
                        company=comp,
                        job_title=title,
                        location=job.get("location", "India"),
                        job_url=target_portal_url,
                        platform="Naukri (Company Site)",
                        status=ApplicationStatus.APPLIED,
                        notes=f"Automated Company Site application ({match_pct}% match)",
                    )
                    acw_app.job_url = target_portal_url

                    if not dry_run:
                        acw_sheet_name = self.excel_mgr.append_acw_application(
                            acw_app,
                            match_pct=match_pct,
                            chance=chance,
                            apply_mode="Company Site (Automated)"
                        )
                        self.seen_mgr.record_job(url, comp, title, "ACW_APPLIED", match_pct)
                        applied_in_cycle += 1
                        self.stats["total_applied"] += 1
                        self.log(f"🎉 External Company Site ({match_pct}% | Chance: {chance}): Successfully submitted application for {comp} - '{title}' on external portal ({target_portal_url}) into '{acw_sheet_name}' sheet!")
                        if self.sheets_mgr:
                            try:
                                self.sheets_mgr.add_application(acw_app)
                            except Exception:
                                pass
                        if self.notifier:
                            self.notifier.send_applied_notification(
                                app=acw_app,
                                match_pct=match_pct,
                                matched_skills=matched_skills
                            )
                    else:
                        self.log(f"📋 [Dry-Run] External Company Site ({match_pct}% | Chance: {chance}): Would record {comp} - '{title}' into dedicated ACW(Date) sheet (Target: {target_portal_url}).")

                    continue

                # STRICT VERIFICATION GUARD FOR DIRECT APPLY:
                # Do NOT log or count as applied unless portal submission was physically verified!
                if not dry_run:
                    if not submission_result or submission_result.status != ApplicationStatus.APPLIED:
                        if submission_result and submission_result.verification_source == "QUOTA_EXCEEDED":
                            self.seen_mgr.record_job(url, comp, title, "QUOTA_EXCEEDED", match_pct)
                            self.log(f"🛑 Naukri Daily Limit Reached: {submission_result.notes}. Cooldown activated.")
                        else:
                            self.seen_mgr.record_job(url, comp, title, "FAILED_UNCONFIRMED", match_pct)
                            self.log(f"⚠️ Live submission could not be confirmed on portal for {comp} ('{title}'). Cooldown activated to prevent endless loop.")
                        continue
                    else:
                        self.log(f"✓ Submission physically verified on portal for {comp}: {submission_result.notes}")

                res_notes = submission_result.notes if submission_result and submission_result.notes else f"Auto-applied ({match_pct}% match: {', '.join(matched_skills[:4])})"
                app_record = JobApplication(
                    app_id=f"AUTO-{comp[:3].upper()}-{int(time.time()) % 10000}-{uuid.uuid4().hex[:4].upper()}",
                    date_applied=datetime.now().strftime("%Y-%m-%d"),
                    company=comp,
                    job_title=title,
                    location=job.get("location", "Gurugram / India"),
                    job_url=url,
                    platform=platform_label,
                    status=ApplicationStatus.APPLIED,
                    notes=res_notes,
                )

                # Log to Google Sheets
                if self.sheets_mgr and not dry_run:
                    try:
                        self.sheets_mgr.add_application(app_record)
                        self.log(f"✓ Recorded {comp} application into Google Sheet.")
                    except Exception as e:
                        self.log(f"Sheets update note: {e}")

                # Log to local Excel (Auto-categorized into Naukri Jobs or Indeed Jobs tab with Chance column)
                follow_up_due = (datetime.now() + timedelta(days=4)).strftime("%Y-%m-%d")
                self.excel_mgr.append_application(app_record, match_pct=match_pct, follow_up_date=follow_up_due, chance=chance)
                self.seen_mgr.record_job(url, comp, title, "APPLIED", match_pct)
                self.log(f"✓ Recorded {comp} application into Job_Applications_Tracker.xlsx [{platform_label}] (Chance: {chance}).")

                # Send self-notification email to Shiva (tagged with 'Job Applied' label in Gmail)
                if self.notifier and not dry_run:
                    self.notifier.send_applied_notification(
                        app=app_record,
                        match_pct=match_pct,
                        matched_skills=matched_skills
                    )
                    self.log(f"✓ Sent confirmation email to {self.profile.personal_info.email} (Filed in 'Job Applied' folder).")

                applied_in_cycle += 1
                self.stats["total_applied"] += 1
                if is_naukri:
                    naukri_applied_count += 1
                else:
                    indeed_applied_count += 1

                # Check if user-requested limit is reached
                if applied_in_cycle >= max_limit:
                    self.log(f"🏁 Target limit reached ({applied_in_cycle}/{max_limit} applications submitted). Stopping cycle cleanly.")
                    break

                # Polite delay between applications
                time.sleep(2)

            results["applied"] = applied_in_cycle
            self.stats["cycles_completed"] += 1
            total_tracked = len(self.excel_mgr.get_all_rows())
            self.stats["total_applied"] = total_tracked
            self.stats["seen_jobs_cached"] = len(self.seen_mgr.data.get("seen_jobs", {}))
            self.stats["avg_jobs_per_cycle"] = round(total_tracked / max(self.stats["cycles_completed"], 1), 1)
            self.stats["avg_jobs_per_hour"] = round((self.stats["avg_jobs_per_cycle"] / max(duration_minutes, 1)) * 60, 1)

            self.stats["last_cycle_status"] = "Completed"
            self.log(f"🎉 Cycle Complete: Successfully submitted {applied_in_cycle} jobs (Target limit: {max_limit}). Average: {self.stats['avg_jobs_per_cycle']} jobs/cycle. Excel & Google Sheets updated.")

        except Exception as e:
            self.log(f"❌ Error during cycle: {e}")
            self.stats["last_cycle_status"] = f"Error: {e}"
        finally:
            self.is_executing = False
            self.stats["cycle_end_deadline"] = None
            self.stats["active_time_remaining_seconds"] = 0

        return results

    def start_scheduler(self):
        """Starts background daemon that runs every 30 minutes with keyword rotation."""
        if self._thread and self._thread.is_alive():
            return

        DEFAULT_KEYWORDS = [
            "data analyst",
            "business analyst",
            "ai product owner",
            "product management",
            "analyst"
        ]

        def _loop():
            self.log("30-Minute Scheduler daemon started with automated keyword rotation.")
            while not self._stop_event.is_set():
                if self.autopilot_active:
                    next_kw = self.seen_mgr.get_next_rotated_keyword(DEFAULT_KEYWORDS)
                    self.log(f"🔄 [Autopilot Rotation] Executing scheduled run for target role: '{next_kw.title()}'")
                    self.run_pipeline(keyword=next_kw)

                # Sleep in increments of 5s up to 30 minutes to allow smooth stopping
                interval_seconds = self.interval_minutes * 60
                slept = 0
                while slept < interval_seconds and not self._stop_event.is_set():
                    time.sleep(5)
                    slept += 5

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop_scheduler(self):
        self._stop_event.set()


# Global engine instance
engine = AutonomousEngine()
