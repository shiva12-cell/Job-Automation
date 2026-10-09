"""
Dynamic Question Solver for Job Application Screening Questions.
Matches form inputs/labels to active candidate profile answers using heuristic matching,
and records unreviewed/unseen questions to a review queue for user verification in the UI.
"""

import os
import re
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.models import CandidateProfile
from src.applier.question_superset import QuestionSupersetResolver

UNREVIEWED_QUEUE_FILE = Path("config/logs/unreviewed_questions.json")


class QuestionSolver:
    """Answers common ATS and portal screening questions based on the active candidate profile."""

    def __init__(self, profile: CandidateProfile):
        self.profile = profile
        self.superset = QuestionSupersetResolver(profile)
        UNREVIEWED_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def log_unreviewed_question(self, question_text: str, suggested_answer: str, company: str = "", job_title: str = ""):
        """Saves an unreviewed screening question into the queue for user inspection in the dashboard."""
        try:
            records = []
            if UNREVIEWED_QUEUE_FILE.exists():
                try:
                    with open(UNREVIEWED_QUEUE_FILE, "r", encoding="utf-8") as f:
                        records = json.load(f)
                except Exception:
                    records = []

            # Deduplicate by question text
            clean_q = question_text.strip().lower()
            if any(r.get("question_text", "").strip().lower() == clean_q for r in records):
                return

            records.append({
                "id": str(uuid.uuid4())[:8],
                "question_text": question_text.strip(),
                "suggested_answer": suggested_answer,
                "company": company,
                "job_title": job_title,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "status": "pending",
            })

            # Keep latest 50 records
            records = records[-50:]
            with open(UNREVIEWED_QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[QuestionSolver] Notice: Could not log unreviewed question ({e})")

    def answer_text_question(self, label_text: str, company: str = "", job_title: str = "") -> Optional[str]:
        """
        Determines the appropriate string answer for an open-ended input or textarea
        using active candidate profile information.
        """
        lower = label_text.lower().strip()

        # 1. Check explicit custom answers in profile first
        for key, value in self.profile.screening_answers.items():
            if key.lower() in lower and value:
                return value

        # 1b. Identity & Contact Details
        if any(k in lower for k in ["first name", "firstname", "given name", "first_name"]):
            return self.profile.personal_info.first_name or (self.profile.personal_info.full_name.split()[0] if self.profile.personal_info.full_name else "")

        if any(k in lower for k in ["last name", "lastname", "surname", "family name", "last_name"]):
            parts = (self.profile.personal_info.full_name or "").split()
            return self.profile.personal_info.last_name or (parts[-1] if len(parts) > 1 else "")

        if any(k in lower for k in ["full name", "fullname", "candidate name", "your name", "full_name"]) and "company" not in lower:
            return self.profile.personal_info.full_name or f"{self.profile.personal_info.first_name} {self.profile.personal_info.last_name}".strip()

        if any(k in lower for k in ["email", "e-mail", "email address", "email_address"]):
            return self.profile.personal_info.email or ""

        if any(k in lower for k in ["phone", "mobile", "contact number", "telephone", "phone number", "mobile number", "cell"]):
            return self.profile.personal_info.phone or ""

        # 2. Work authorization & sponsorship
        if "sponsorship" in lower or "sponsor" in lower:
            ans = "No" if not self.profile.work_authorization.requires_sponsorship_now else "Yes"
            return ans

        if "authorized" in lower or "legally eligible" in lower or "work permit" in lower:
            ans = "Yes" if self.profile.work_authorization.authorized_to_work_in_country else "No"
            return ans

        # 3. Salary / CTC expectations
        if any(w in lower for w in ["expected ctc", "expected salary", "salary expectation", "package expectation"]):
            return self.profile.screening_answers.get("expected_ctc") or self.profile.screening_answers.get("salary") or "6 LPA"

        if any(w in lower for w in ["current ctc", "current salary", "present salary"]):
            return self.profile.screening_answers.get("current_ctc") or "0 / Fresher"

        if any(w in lower for w in ["salary", "compensation", "ctc", "pay expectation", "package"]):
            return self.profile.screening_answers.get("salary") or self.profile.screening_answers.get("expected_ctc") or "6 LPA"

        # 4. Notice period
        if "notice period" in lower or "available to start" in lower or "start date" in lower or "joining time" in lower:
            return self.profile.screening_answers.get("notice_period") or self.profile.screening_answers.get("notice") or "Immediate"

        # 5. Years of experience
        if any(w in lower for w in ["years of experience", "how many years", "total experience", "relevant experience"]):
            exp_val = "0"
            if self.profile.experience:
                exp_val = str(self.profile.experience.years_of_experience)
            elif "experience" in self.profile.screening_answers:
                exp_val = str(self.profile.screening_answers["experience"])
            return exp_val

        # 6. Relocation
        if "relocate" in lower or "relocation" in lower:
            return self.profile.screening_answers.get("relocation") or "Yes, completely open to relocate"

        # 7. Education / University / Degree
        if "degree" in lower or "highest qualification" in lower:
            if self.profile.education and self.profile.education.degree:
                return self.profile.education.degree
            return self.profile.screening_answers.get("degree") or "Bachelor's Degree"

        if "university" in lower or "college" in lower or "institute" in lower:
            if self.profile.education and self.profile.education.university:
                return self.profile.education.university
            return self.profile.screening_answers.get("university") or "University Graduate"

        # 8. Headline / Summary
        if "headline" in lower or "summary" in lower or "cover letter" in lower:
            if self.profile.screening_answers.get("headline"):
                return self.profile.screening_answers["headline"]
            title = self.profile.personal_info.current_title or "Professional"
            return f"{title} with strong problem solving and analytics capabilities."

        # 9. URLs
        if "linkedin" in lower:
            return self.profile.personal_info.linkedin_url or ""
        if "github" in lower:
            return self.profile.personal_info.github_url or ""
        if "portfolio" in lower or "website" in lower:
            return self.profile.personal_info.portfolio_url or ""

        # 10. Location / City
        if any(w in lower for w in ["current city", "city", "location", "residing"]):
            return (
                self.profile.screening_answers.get("location")
                or self.profile.personal_info.location
                or "Pan-India"
            )

        # 11. How did you hear
        if "hear about" in lower or "referral" in lower or "source" in lower:
            return self.profile.screening_answers.get("how_did_you_hear", "Naukri.com")

        # 12. Consult 12-Pillar Question Superset Engine
        superset_ans = self.superset.resolve_answer(label_text, field_type="text")
        if superset_ans and superset_ans.lower() != "yes":
            return superset_ans

        # Fallback & Queue logging for novel questions
        fallback_ans = superset_ans or "Yes"
        self.log_unreviewed_question(label_text, suggested_answer=fallback_ans, company=company, job_title=job_title)
        return fallback_ans

    def select_best_option(self, label_text: str, options: List[str], company: str = "", job_title: str = "") -> Optional[str]:
        """
        Selects the best matching option from a dropdown or radio button list.
        """
        lower_label = label_text.lower().strip()

        # 1. Sponsorship question
        if "sponsorship" in lower_label or "sponsor" in lower_label:
            target = "no" if not self.profile.work_authorization.requires_sponsorship_future else "yes"
            for opt in options:
                if target in opt.lower():
                    return opt

        # 2. Authorization to work
        if "authorized" in lower_label or "legally eligible" in lower_label or "work permit" in lower_label:
            target = "yes" if self.profile.work_authorization.authorized_to_work_in_country else "no"
            for opt in options:
                if target in opt.lower():
                    return opt

        # 3. Gender / Race / Veteran / Disability standard disclosures
        if "gender" in lower_label:
            pref = self.profile.screening_answers.get("gender", "Decline").lower()
            for opt in options:
                if pref in opt.lower() or "prefer not" in opt.lower() or "decline" in opt.lower():
                    return opt

        if "race" in lower_label or "ethnicity" in lower_label:
            pref = self.profile.screening_answers.get("race", "Decline").lower()
            for opt in options:
                if pref in opt.lower() or "prefer not" in opt.lower() or "decline" in opt.lower():
                    return opt

        if "veteran" in lower_label:
            pref = self.profile.screening_answers.get("veteran", "not a protected").lower()
            for opt in options:
                if pref in opt.lower() or "not a" in opt.lower() or "decline" in opt.lower():
                    return opt

        if "disability" in lower_label:
            pref = self.profile.screening_answers.get("disability", "do not have").lower()
            for opt in options:
                if pref in opt.lower() or "do not have" in opt.lower() or opt.strip().lower() == "no" or "decline" in opt.lower():
                    return opt

        # 4. Notice period options
        if "notice" in lower_label:
            pref_notice = (self.profile.screening_answers.get("notice_period") or self.profile.screening_answers.get("notice") or "immediate").lower()
            for opt in options:
                if pref_notice in opt.lower() or "immediate" in opt.lower() or "0" in opt.lower() or "15" in opt.lower():
                    return opt

        # 5. Relocation options
        if "relocate" in lower_label:
            for opt in options:
                if "yes" in opt.lower() or "open" in opt.lower():
                    return opt

        # 6. Try matching screening answers directly
        for key, ans in self.profile.screening_answers.items():
            if key.lower() in lower_label:
                for opt in options:
                    if ans.lower() in opt.lower():
                        return opt

        # 7. Check for positive choices (Yes, Agree)
        for opt in options:
            if opt.lower().strip() in ["yes", "agree", "true", "i agree"]:
                return opt

        # 8. Check Question Superset Engine for options
        superset_opt = self.superset.resolve_answer(label_text, options=options, field_type="select")
        if superset_opt:
            return superset_opt

        picked = options[0] if options else None
        if picked:
            self.log_unreviewed_question(
                label_text,
                suggested_answer=picked,
                company=company,
                job_title=job_title,
            )
        return picked
