"""
FastAPI Server for AutoJob AI Web Dashboard.
Exposes REST APIs for triggering auto-apply, monitoring 4-hour status, and tracking Excel & Google Sheets.
"""

import os
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from src.autonomous_engine import engine

app = FastAPI(title="AutoJob AI Dashboard", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATE_PATH = Path(__file__).parent / "templates" / "dashboard.html"


@app.on_event("startup")
def on_startup():
    """Starts the 30-minute scheduler with keyword rotation."""
    engine.start_scheduler()
    engine.log("🚀 Web server online. 30-minute autopilot armed with smart pagination & keyword rotation.")


@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """Serves the main HTML dashboard."""
    if not TEMPLATE_PATH.exists():
        return HTMLResponse("<h1>Dashboard template not found</h1>", status_code=404)
    return HTMLResponse(TEMPLATE_PATH.read_text(encoding="utf-8"))


import time
import re
import json
import shutil
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Body
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from src.autonomous_engine import engine
from src.resume_parser import extract_text_from_pdf, parse_resume_data
from src.config import save_active_profile, load_candidate_profile, ACTIVE_PROFILE_FILE

UNREVIEWED_QUEUE_FILE = Path("config/logs/unreviewed_questions.json")


# =====================================================================
# Profile & Dynamic Resume Onboarding Endpoints
# =====================================================================

@app.get("/api/profile")
def get_profile():
    """Returns the current active candidate profile, skills, and screening configuration."""
    prof = engine.profile
    resume_name = Path(prof.resume_path).name if prof.resume_path else "resume.pdf"
    return {
        "personal_info": prof.personal_info.model_dump(),
        "work_authorization": prof.work_authorization.model_dump(),
        "education": prof.education.model_dump() if prof.education else {},
        "experience": prof.experience.model_dump() if prof.experience else {
            "years_of_experience": 0,
            "target_experience_range": "0 - 1 years",
            "skills": list(engine.matcher.candidate_skills)
        },
        "screening_answers": prof.screening_answers,
        "resume_path": str(prof.resume_path) if prof.resume_path else "resumes/resume.pdf",
        "resume_name": resume_name,
        "total_skills": len(engine.matcher.candidate_skills),
    }


@app.post("/api/profile/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """Accepts uploaded PDF resume, extracts skills & personal details, and updates active candidate profile."""
    if not file.filename.lower().endswith(".pdf"):
        return {"status": "error", "message": "Only PDF resume files (.pdf) are supported."}

    resumes_dir = Path("resumes")
    resumes_dir.mkdir(parents=True, exist_ok=True)
    clean_name = re.sub(r"[^\w\-_\.]", "_", file.filename)
    target_path = resumes_dir / clean_name

    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        raw_text = extract_text_from_pdf(target_path)
        parsed = parse_resume_data(raw_text)
        parsed["resume_path"] = str(target_path)

        # Merge with existing screening answers if present
        existing_answers = dict(engine.profile.screening_answers)
        existing_answers.update(parsed.get("screening_answers", {}))
        parsed["screening_answers"] = existing_answers

        save_active_profile(parsed)
        engine.reload_profile()

        return {
            "status": "success",
            "message": f"Resume '{file.filename}' parsed successfully! Candidate: {parsed['personal_info']['full_name']}.",
            "profile": {
                "full_name": parsed["personal_info"]["full_name"],
                "email": parsed["personal_info"]["email"],
                "phone": parsed["personal_info"]["phone"],
                "location": parsed["personal_info"]["location"],
                "title": parsed["personal_info"]["current_title"],
                "skills_count": len(parsed["experience"]["skills"]),
                "skills": parsed["experience"]["skills"],
            }
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse resume: {str(e)}"}


@app.post("/api/profile")
def update_profile(data: dict = Body(...)):
    """Updates candidate profile fields directly from the dashboard."""
    curr = engine.profile.model_dump()
    if "personal_info" in data:
        curr.setdefault("personal_info", {}).update(data["personal_info"])
    if "education" in data:
        curr.setdefault("education", {}).update(data["education"])
    if "experience" in data:
        curr.setdefault("experience", {}).update(data["experience"])
    if "screening_answers" in data:
        curr.setdefault("screening_answers", {}).update(data["screening_answers"])

    save_active_profile(curr)
    engine.reload_profile()
    return {"status": "success", "message": "Candidate profile updated successfully."}


@app.get("/api/screening-qa")
def get_screening_qa():
    """Returns candidate's active screening QA answers along with any logged unreviewed recruiter questions and 12-pillar Superset."""
    from src.applier.question_superset import QUESTION_SUPERSET_SCHEMA
    answers = engine.profile.screening_answers
    queue = []
    if UNREVIEWED_QUEUE_FILE.exists():
        try:
            with open(UNREVIEWED_QUEUE_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)
        except Exception:
            queue = []

    return {
        "answers": answers,
        "queue": queue,
        "count_queue": len([q for q in queue if q.get("status") == "pending"]),
        "superset": QUESTION_SUPERSET_SCHEMA,
    }


@app.get("/api/superset")
def get_superset():
    """Returns the 12-Pillar Question Superset structure populated with candidate profile answers."""
    from src.applier.question_superset import QUESTION_SUPERSET_SCHEMA
    return {
        "schema": QUESTION_SUPERSET_SCHEMA,
        "answers": engine.profile.screening_answers,
    }


@app.post("/api/screening-qa")
def update_screening_qa(answers: dict = Body(...)):
    """Updates approved screening question answers from UI edits."""
    curr = engine.profile.model_dump()
    curr.setdefault("screening_answers", {}).update(answers)
    save_active_profile(curr)
    engine.reload_profile()
    return {"status": "success", "message": "Screening answers updated and saved."}


@app.post("/api/screening-qa/review-queue/resolve")
def resolve_unreviewed_question(item: dict = Body(...)):
    """Resolves an unreviewed question: saves answer and updates question status."""
    q_id = item.get("id")
    q_text = item.get("question_text", "").lower()
    answer = item.get("answer", "")

    # Save to screening answers
    curr = engine.profile.model_dump()
    curr.setdefault("screening_answers", {})[q_text] = answer
    save_active_profile(curr)
    engine.reload_profile()

    # Update queue file
    if UNREVIEWED_QUEUE_FILE.exists():
        try:
            with open(UNREVIEWED_QUEUE_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)
            for q in queue:
                if q.get("id") == q_id:
                    q["status"] = "resolved"
                    q["resolved_answer"] = answer
            with open(UNREVIEWED_QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(queue, f, indent=2)
        except Exception:
            pass

    return {"status": "success", "message": f"Answer for '{q_text}' saved to knowledge base."}


@app.delete("/api/screening-qa/review-queue/{question_id}")
def delete_queue_item(question_id: str):
    """Dismisses an item from the screening review queue."""
    if UNREVIEWED_QUEUE_FILE.exists():
        try:
            with open(UNREVIEWED_QUEUE_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)
            queue = [q for q in queue if q.get("id") != question_id]
            with open(UNREVIEWED_QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(queue, f, indent=2)
        except Exception:
            pass
    return {"status": "success", "message": "Queue item dismissed."}


# =====================================================================
# Application Trigger Endpoint
# =====================================================================
@app.post("/api/trigger")
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    limit: int = 50,
    keyword: str = "data analyst",
    duration_minutes: int = 30,
    headless: bool = True,
    location: str = "any",
    min_salary: float = 0.0,
    max_salary: float = 99.0,
    experience_years: int = 0,
    job_age_days: int = 0,
    work_mode: str = "all",
    sort_by: str = "relevance",
    apply_mode: str = "all"
):
    """Triggers application cycle with user-specified limit, keyword, duration timer, location, salary range, live Naukri filters, and apply_mode."""
    background_tasks.add_task(
        engine.run_pipeline,
        max_limit=limit,
        keyword=keyword,
        duration_minutes=duration_minutes,
        dry_run=False,
        headless=headless,
        enable_indeed=False,
        location=location,
        min_salary_lpa=min_salary,
        max_salary_lpa=max_salary,
        experience_years=experience_years,
        job_age_days=job_age_days,
        work_mode=work_mode,
        sort_by=sort_by,
        apply_mode=apply_mode
    )
    sal_str = f"{min_salary}-{max_salary} LPA" if (min_salary > 0 or max_salary < 99) else "Any CTC"
    mode_str = "silent background mode (no popups)" if headless else "visible browser mode"
    return {
        "status": "triggered",
        "message": f"Cycle launched in {mode_str}: target {limit} jobs for '{keyword}' in '{location}' ({sal_str}), timer {duration_minutes}m."
    }


@app.post("/api/reset-tracker")
def reset_tracker():
    """Backs up existing tracker and resets all sheets so deduplication unblocks fresh applications."""
    backup_file = engine.excel_mgr.backup_and_reset()
    engine.stats["total_applied"] = 0
    engine.stats["matched_65_pct"] = 0
    engine.log(f"🧹 Tracker reset & backed up to '{backup_file}'. Deduplication unblocked for fresh applications!")
    return {
        "status": "success",
        "backup_file": backup_file,
        "message": f"Tracker backed up to {backup_file} and reset cleanly."
    }


@app.post("/api/clear-entries")
def clear_entries(tab: str = "all"):
    """
    Clears applications from the Excel tracker (either a specific sheet tab or all sheets).
    Always creates an automatic timestamped backup first.
    """
    sheet_name = None if tab.lower() in ["all", "all applications"] else tab
    backup_file = engine.excel_mgr.backup_and_reset(sheet_name=sheet_name)
    try:
        all_rows = engine.excel_mgr.get_all_rows(sheet_name="All Applications")
        engine.stats["total_applied"] = len(all_rows)
    except Exception:
        pass
    engine.log(f"🧹 Tracker entries cleared for tab '{tab}' (backed up to '{backup_file}').")
    return {
        "status": "success",
        "backup_file": backup_file,
        "message": f"Successfully cleared entries for '{tab}'. Backup saved to {backup_file}."
    }


@app.post("/api/purge-manual")
def purge_manual_jobs():
    """Purges all manual application entries across sheets and wipes MANUAL_SAVED from seen cache."""
    excel_purged = engine.excel_mgr.purge_manual_applications()
    seen_purged = engine.seen_mgr.purge_manual_seen_jobs()
    engine.stats["manual_needed"] = 0
    engine.log(f"🧹 Purged {excel_purged} manual rows from Excel tracker and {seen_purged} entries from seen cache.")
    return {
        "status": "success",
        "excel_purged": excel_purged,
        "seen_purged": seen_purged,
        "message": f"Purged {excel_purged} manual sheet entries and {seen_purged} cached manual records."
    }


@app.delete("/api/applications/{app_id}")
def delete_application(app_id: str):
    """Deletes a specific application entry by ID from the Excel tracker."""
    deleted = engine.excel_mgr.delete_entry(app_id)
    if deleted:
        try:
            all_rows = engine.excel_mgr.get_all_rows(sheet_name="All Applications")
            engine.stats["total_applied"] = len(all_rows)
        except Exception:
            pass
        engine.log(f"🗑️ Deleted application entry '{app_id}' from tracker.")
        return {"status": "success", "message": f"Entry {app_id} deleted."}
    return {"status": "error", "message": f"Entry {app_id} not found."}


@app.get("/api/status")
def get_status():
    """Returns engine state, run duration timer, next schedule, stats, and logs."""
    rem_seconds = 0
    if engine.is_executing and engine.stats.get("cycle_end_deadline"):
        rem_seconds = max(0, int(engine.stats["cycle_end_deadline"] - time.time()))
    engine.stats["active_time_remaining_seconds"] = rem_seconds

    try:
        all_rows = engine.excel_mgr.get_all_rows(sheet_name="All Applications")
        nau_rows = engine.excel_mgr.get_all_rows(sheet_name="Naukri Jobs")
        ind_rows = engine.excel_mgr.get_all_rows(sheet_name="Indeed Jobs")
        man_rows = engine.excel_mgr.get_all_rows(sheet_name="Manual")
        acw_rows = engine.excel_mgr.get_all_rows(sheet_name="ACW")
        engine.stats["manual_needed"] = len(man_rows)
        engine.stats["acw_total"] = len(acw_rows)
        engine.stats["total_applied"] = len(all_rows)
        engine.stats["seen_jobs_cached"] = len(engine.seen_mgr.data.get("seen_jobs", {}))
        cat_stats = engine.excel_mgr.get_category_stats()
        engine.stats["category_counts"] = cat_stats
        engine.stats["tab_counts"] = {
            "all": len(all_rows),
            "naukri": len(nau_rows),
            "indeed": len(ind_rows),
            "manual": len(man_rows),
            "acw": len(acw_rows),
            "data_analyst": cat_stats.get("Data Analyst", {}).get("total", 0),
            "business_analyst": cat_stats.get("Business Analyst", {}).get("total", 0),
            "ai_product": cat_stats.get("AI & Product Management", {}).get("total", 0),
            "data_engineering": cat_stats.get("Data Engineering & Science", {}).get("total", 0),
            "other_tech": cat_stats.get("Other Tech & Roles", {}).get("total", 0),
        }
    except Exception:
        pass

    return {
        "is_executing": engine.is_executing,
        "autopilot_active": engine.autopilot_active,
        "next_run": engine.next_run_time.isoformat() if engine.next_run_time else None,
        "last_run": engine.last_run_time.isoformat() if engine.last_run_time else None,
        "stats": engine.stats,
        "logs": list(engine.logs),
    }


@app.get("/api/keywords")
def get_keywords():
    """Returns candidate keyword roles."""
    return [
        {"id": "data analyst", "label": "Data Analyst"},
        {"id": "business analyst", "label": "Business Analyst"},
        {"id": "ai product owner", "label": "AI Product Owner"},
        {"id": "product management", "label": "Product Management"},
        {"id": "analyst", "label": "Analyst (B.Tech CSE)"},
        {"id": "all", "label": "⚡ All Matching Roles (Auto-Rotate)"},
    ]


@app.get("/api/applications")
def get_applications(tab: str = "All Applications"):
    """Returns tracked applications from the local Excel file for a specific tab or all."""
    rows = engine.excel_mgr.get_all_rows(sheet_name=tab)
    return rows


@app.get("/api/failures")
def get_failures():
    """Returns captured diagnostic records for applications that failed after 5 attempts."""
    log_file = Path("config/logs/submission_failures.json")
    if log_file.exists():
        try:
            import json
            with open(log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


@app.get("/api/cache-stats")
def get_cache_stats():
    """Returns telemetry on seen jobs cache and smart pagination cursors."""
    return engine.seen_mgr.get_stats()


@app.post("/api/reset-cache")
def reset_cache():
    """Clears the seen jobs cache, re-syncs from local Excel, and resets pagination."""
    cleared = engine.seen_mgr.clear_seen_cache()
    synced = engine.seen_mgr.sync_from_excel(engine.excel_mgr)
    engine.stats["seen_jobs_cached"] = len(engine.seen_mgr.data.get("seen_jobs", {}))
    engine.log(f"🔄 Seen jobs cache reset & re-synced from Excel ({synced} records).")
    return {
        "status": "success",
        "cleared": cleared,
        "synced": synced,
        "message": f"Cache reset and re-synced {synced} jobs from Excel tracker.",
        "stats": engine.seen_mgr.get_stats(),
    }


@app.post("/api/reset-pagination")
def reset_pagination():
    """Resets pagination cursors for all search roles to Page 1."""
    engine.seen_mgr.reset_cursor()
    engine.log("📑 Smart pagination cursors reset to Page 1 for all keywords.")
    return {
        "status": "success",
        "message": "Pagination cursors reset to Page 1 for all keywords.",
        "cursors": engine.seen_mgr.data.get("pagination_cursors", {}),
    }


@app.get("/api/accounts")
def get_accounts():
    """Returns linked platform session statuses."""
    naukri_file = Path("config/credentials/naukri_state.json")
    naukri_linked = naukri_file.exists()
    gmail_linked = Path("config/credentials/token.json").exists()

    naukri_info = {
        "linked": naukri_linked,
        "name": "Naukri.com (Primary)",
        "cookie_count": 0,
        "file_size_kb": 0.0,
    }
    if naukri_linked:
        try:
            with open(naukri_file, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                cookies = c_data.get("cookies", [])
                naukri_info["cookie_count"] = len(cookies)
                naukri_info["file_size_kb"] = round(naukri_file.stat().st_size / 1024, 1)
        except Exception:
            pass

    return {
        "naukri": naukri_info,
        "gmail": {"linked": gmail_linked, "name": "Gmail & Google Sheets"},
    }


@app.post("/api/link-indeed")
def link_indeed():
    """Indeed integration disabled; application pipeline focuses 100% on Naukri.com."""
    return {"status": "disabled", "message": "Indeed integration disabled. Focusing on Naukri.com."}


@app.post("/api/link-naukri")
def link_naukri(background_tasks: BackgroundTasks):
    """Launches interactive browser to log into Naukri and save session."""
    from src.applier.naukri import NaukriApplier
    def _run():
        applier = NaukriApplier(engine.profile)
        applier.interactive_login()
    background_tasks.add_task(_run)
    return {"status": "started", "message": "Naukri login browser opened."}


@app.post("/api/shutdown")
def shutdown_app():
    """Kill switch: safely stops engine, scheduler, and shuts down the process."""
    engine.stop_scheduler()
    engine.log("🛑 Kill switch activated. AutoJob AI shutting down cleanly...")
    import threading
    def _kill():
        import time
        time.sleep(1)
        import os
        os._exit(0)
    threading.Thread(target=_kill, daemon=True).start()
    return {"status": "shutdown", "message": "AutoJob AI successfully stopped."}


@app.post("/api/toggle-autopilot")
def toggle_autopilot():
    """Toggles the 30-minute background scheduler."""
    engine.autopilot_active = not engine.autopilot_active
    state = "Active" if engine.autopilot_active else "Paused"
    engine.log(f"30-Minute Autopilot state switched to: {state}")
    return {"autopilot_active": engine.autopilot_active, "state": state}


@app.get("/download/excel")
def download_excel():
    """Directly downloads the local Excel tracker file."""
    excel_file = Path("Job_Applications_Tracker.xlsx")
    if not excel_file.exists():
        engine.excel_mgr._ensure_workbook()
    return FileResponse(
        path=str(excel_file),
        filename="Job_Applications_Tracker.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
