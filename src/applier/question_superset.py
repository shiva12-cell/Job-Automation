"""
Question Superset Knowledge Base & Semantic Resolver.
Exhaustively covers every screening question variation across top MNC career portals:
Workday, Greenhouse, Lever, Taleo, SAP SuccessFactors, Darwinbox, SmartRecruiters, iCIMS.

Divided into 12 Comprehensive Pillars:
1. Core Personal Identity & Socials
2. Work Authorization, Visas & Sponsorship
3. Compensation & Benefits
4. Availability, Notice Period & Joining Date
5. Experience, Technical Depth & Employment Gaps
6. Education & Academic Background
7. Location, Work Modality & Shift Flexibility
8. Self-Ratings & Tool Proficiencies
9. Background Verification & Compliance
10. Equal Employment Opportunity (EEO) & Diversity Disclosures
11. Behavioral, Motivational & Cover Letter Questions
12. Professional References
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from src.models import CandidateProfile

QUESTION_SUPERSET_SCHEMA = {
    "categories": [
        {
            "id": "identity",
            "name": "1. Personal Identity & Links",
            "description": "Full name, phone prefix, LinkedIn, GitHub, Portfolio",
            "questions": [
                {"key": "full_name", "label": "Full Name", "default": ""},
                {"key": "email", "label": "Email Address", "default": ""},
                {"key": "phone", "label": "Phone Number with Country Code", "default": "+91"},
                {"key": "current_city", "label": "Current City / Town", "default": "Gurugram, India"},
                {"key": "linkedin_url", "label": "LinkedIn Profile URL", "default": ""},
                {"key": "github_url", "label": "GitHub Profile URL", "default": ""},
                {"key": "portfolio_url", "label": "Portfolio / Personal Website", "default": ""},
            ]
        },
        {
            "id": "work_auth",
            "name": "2. Work Authorization & Visas",
            "description": "Citizen status, sponsorship, work permits across India, US, UK, EU",
            "questions": [
                {"key": "authorized_in_country", "label": "Are you legally authorized to work in the country of application?", "default": "Yes"},
                {"key": "requires_sponsorship", "label": "Will you now or in the future require visa sponsorship?", "default": "No"},
                {"key": "has_valid_passport", "label": "Do you hold a valid passport for business travel?", "default": "Yes"},
                {"key": "country_of_citizenship", "label": "Country of Citizenship", "default": "India"},
            ]
        },
        {
            "id": "compensation",
            "name": "3. Compensation & Expectations",
            "description": "Current CTC, Expected CTC, Fixed vs Variable, Currency",
            "questions": [
                {"key": "current_ctc", "label": "Current CTC / Salary (Annual)", "default": "0 / Fresher"},
                {"key": "expected_ctc", "label": "Expected CTC / Salary (Annual)", "default": "6 - 8 LPA"},
                {"key": "is_salary_negotiable", "label": "Is your salary expectation negotiable?", "default": "Yes, negotiable based on role and learning potential"},
            ]
        },
        {
            "id": "availability",
            "name": "4. Notice Period & Joining Date",
            "description": "Official notice period, buyout, earliest start date",
            "questions": [
                {"key": "notice_period", "label": "Official Notice Period (in days)", "default": "Immediate / 0 days"},
                {"key": "can_buyout_notice", "label": "Can your notice period be bought out / negotiated early?", "default": "Immediate joiner"},
                {"key": "earliest_start_date", "label": "Earliest Date you can join?", "default": "Immediate"},
            ]
        },
        {
            "id": "experience",
            "name": "5. Experience & Skill Gaps",
            "description": "Total experience, relevant experience, employment gap justification",
            "questions": [
                {"key": "total_experience_years", "label": "Total Years of Professional Experience", "default": "0-1 Years"},
                {"key": "relevant_experience_years", "label": "Years of Relevant Experience in Target Role", "default": "1 Year"},
                {"key": "employment_gap_reason", "label": "Do you have any employment gaps? If yes, explain.", "default": "No gaps. Focused continuously on university academics, live technical projects, and skill development."},
            ]
        },
        {
            "id": "education",
            "name": "6. Academic Background",
            "description": "Highest degree, specialization, GPA/Percentage, graduation year",
            "questions": [
                {"key": "highest_degree", "label": "Highest Degree Attained", "default": "B.Tech Computer Science and Engineering"},
                {"key": "university_name", "label": "University / College Name", "default": "Engineering College"},
                {"key": "graduation_year", "label": "Year of Graduation", "default": "2024"},
                {"key": "gpa_percentage", "label": "CGPA / Percentage", "default": "8.0 CGPA"},
            ]
        },
        {
            "id": "location_shifts",
            "name": "7. Location & Work Modality",
            "description": "Remote/Hybrid/WFO, willingness to relocate, shift hours",
            "questions": [
                {"key": "willing_to_relocate", "label": "Are you willing to relocate to job location?", "default": "Yes, open to relocate immediately"},
                {"key": "preferred_work_mode", "label": "Preferred Work Mode (Remote / Hybrid / On-site)", "default": "Flexible with Hybrid, On-site, or Remote"},
                {"key": "comfortable_with_rotational_shifts", "label": "Are you comfortable working in rotational / US / UK shifts?", "default": "Yes, comfortable with standard or rotational shifts"},
            ]
        },
        {
            "id": "tool_ratings",
            "name": "8. Tool Proficiencies & Self Ratings",
            "description": "SQL, Python, Excel, Power BI, Tableau, Git",
            "questions": [
                {"key": "sql_proficiency", "label": "Rate your proficiency in SQL (1 to 5)", "default": "5/5 (Advanced queries, CTEs, Window functions, Aggregations)"},
                {"key": "python_proficiency", "label": "Rate your proficiency in Python (1 to 5)", "default": "4/5 (Pandas, NumPy, Scripting, Automation)"},
                {"key": "excel_proficiency", "label": "Rate your proficiency in Microsoft Excel (1 to 5)", "default": "5/5 (VLOOKUP, XLOOKUP, Pivot Tables, Formulas)"},
                {"key": "bi_tool_proficiency", "label": "Rate your proficiency in Power BI / Tableau (1 to 5)", "default": "4/5 (Interactive DAX dashboards, reports, KPIs)"},
            ]
        },
        {
            "id": "background_compliance",
            "name": "9. Background Verification & Compliance",
            "description": "Clean criminal history, willing to undergo BGV, NDAs, non-competes",
            "questions": [
                {"key": "willing_bgv", "label": "Are you willing to undergo standard Background Verification (BGV)?", "default": "Yes, agree unconditionally"},
                {"key": "criminal_record", "label": "Have you ever been convicted of a criminal offense?", "default": "No"},
                {"key": "non_compete_obligation", "label": "Are you bound by any non-compete agreements?", "default": "No"},
            ]
        },
        {
            "id": "eeo_diversity",
            "name": "10. EEO & Diversity Disclosures",
            "description": "Voluntary declarations (Gender, Veteran, Disability, Ethnicity)",
            "questions": [
                {"key": "gender_declaration", "label": "Gender Identity", "default": "Decline to specify / Prefer not to say"},
                {"key": "veteran_status", "label": "Veteran Status", "default": "I am not a protected veteran"},
                {"key": "disability_status", "label": "Disability Status", "default": "No, I do not have a disability"},
                {"key": "race_ethnicity", "label": "Race / Ethnicity", "default": "Decline to specify / Asian"},
            ]
        },
        {
            "id": "behavioral",
            "name": "11. Behavioral & Motivations",
            "description": "Why this company, why you, strengths, cover letter blurb",
            "questions": [
                {"key": "why_this_company", "label": "Why do you want to join our company?", "default": "Your company leads technological innovation and industry impact. I am excited to apply my data analytics and problem-solving skills to build actionable business value in your collaborative environment."},
                {"key": "biggest_strength", "label": "What is your greatest professional strength?", "default": "Strong analytical acumen, rapid self-learning capability, and transforming complex data into clear stakeholder insights."},
                {"key": "cover_letter_snippet", "label": "Short Cover Letter / Professional Pitch", "default": "Results-oriented Data & Business Analyst with rigorous analytical problem-solving foundation in SQL, Python, Excel, and BI reporting. Proven track record of delivering clean actionable insights and eager to contribute to organizational success."},
            ]
        },
        {
            "id": "references",
            "name": "12. Professional References",
            "description": "References available on request",
            "questions": [
                {"key": "references_available", "label": "Can you provide professional/academic references upon request?", "default": "Yes, available upon request"},
            ]
        }
    ]
}


class QuestionSupersetResolver:
    """
    Intelligent semantic resolver that matches any MNC career portal form field
    against the 12 Question Superset categories and candidate profile.
    """

    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def resolve_answer(
        self,
        label_text: str,
        options: Optional[List[str]] = None,
        field_type: str = "text"
    ) -> Optional[str]:
        """
        Resolves an answer for a question label and optional dropdown options.
        """
        clean = (label_text or "").strip().lower()

        # If options are provided (dropdown, radio, select), resolve best matching option
        if options and len(options) > 0:
            return self._resolve_option(clean, options)

        # Open-ended text field
        return self._resolve_text(clean)

    def _resolve_text(self, label: str) -> str:
        # Check custom screening answers in profile first
        for k, v in self.profile.screening_answers.items():
            if k.lower() in label and v:
                return str(v)

        # 1. Identity & URLs
        if "linkedin" in label:
            return self.profile.personal_info.linkedin_url or ""
        if "github" in label:
            return self.profile.personal_info.github_url or ""
        if "portfolio" in label or "website" in label:
            return self.profile.personal_info.portfolio_url or ""
        if "first name" in label:
            parts = (self.profile.personal_info.full_name or "").split()
            return parts[0] if parts else "Candidate"
        if "last name" in label:
            parts = (self.profile.personal_info.full_name or "").split()
            return parts[-1] if len(parts) > 1 else ""
        if "full name" in label or "candidate name" in label:
            return self.profile.personal_info.full_name or "Candidate"
        if "phone" in label or "mobile" in label or "contact" in label:
            return self.profile.personal_info.phone or "+919876543210"
        if "email" in label:
            return self.profile.personal_info.email or ""

        # 2. Work Auth & Visas
        if "sponsor" in label or "sponsorship" in label:
            return "No" if not self.profile.work_authorization.requires_sponsorship_now else "Yes"
        if any(w in label for w in ["authorized", "legally eligible", "work permit", "right to work"]):
            return "Yes" if self.profile.work_authorization.authorized_to_work_in_country else "No"
        if "citizen" in label or "nationality" in label:
            return "India"
        if "passport" in label:
            return "Yes"

        # 3. Compensation
        if any(w in label for w in ["expected ctc", "expected salary", "salary expectation", "package expectation"]):
            return self.profile.screening_answers.get("expected_ctc") or "6 LPA"
        if any(w in label for w in ["current ctc", "current salary", "present salary", "current package"]):
            return self.profile.screening_answers.get("current_ctc") or "0 / Fresher"
        if any(w in label for w in ["salary", "compensation", "ctc", "pay expectation", "package"]):
            return self.profile.screening_answers.get("expected_ctc") or "6 LPA"

        # 4. Notice period & Availability
        if any(w in label for w in ["notice period", "days notice", "how many days notice"]):
            return self.profile.screening_answers.get("notice_period") or "0"
        if any(w in label for w in ["available to start", "start date", "earliest join", "joining time", "when can you start"]):
            return "Immediate"

        # 5. Experience & Skill Gaps
        if any(w in label for w in ["years of experience", "total experience", "how many years"]):
            if self.profile.experience:
                return str(self.profile.experience.years_of_experience)
            return "1"
        if "relevant experience" in label:
            return "1"
        if "gap" in label:
            return "No gaps. Focused continuously on university academics, live technical projects, and skill development."

        # 6. Education
        if any(w in label for w in ["degree", "qualification", "highest education"]):
            return (self.profile.education.degree if self.profile.education else None) or "B.Tech Computer Science and Engineering"
        if any(w in label for w in ["university", "college", "institute", "school"]):
            return (self.profile.education.university if self.profile.education else None) or "Engineering College"
        if "cgpa" in label or "gpa" in label or "percentage" in label or "marks" in label:
            return "8.0"
        if "graduation year" in label or "year of passing" in label or "pass out" in label:
            return "2024"

        # 7. Location & Relocation & Shift
        if "relocate" in label or "relocation" in label:
            return "Yes, completely open to relocate"
        if any(w in label for w in ["current city", "city", "residing", "location", "address"]):
            return self.profile.personal_info.location or "Gurugram, India"
        if "shift" in label:
            return "Yes, comfortable with standard or rotational shifts"

        # 8. Tool Proficiencies (SQL, Python, Excel, BI)
        if "sql" in label:
            return "5" if "rate" in label or "1-5" in label or "1 to 5" in label else "Advanced (CTEs, Joins, Window Functions)"
        if "python" in label:
            return "4" if "rate" in label or "1-5" in label or "1 to 5" in label else "Proficient (Pandas, NumPy, Automation)"
        if "excel" in label:
            return "5" if "rate" in label or "1-5" in label or "1 to 5" in label else "Advanced (VLOOKUP, Pivot Tables, Modeling)"
        if "power bi" in label or "tableau" in label or "dashboard" in label:
            return "4" if "rate" in label or "1-5" in label or "1 to 5" in label else "Proficient in interactive reports & DAX"

        # 9. Background & Compliance
        if "background check" in label or "bgv" in label or "verification" in label:
            return "Yes, agree"
        if "criminal" in label or "felony" in label:
            return "No"
        if "non-compete" in label or "restrictive covenant" in label:
            return "No"

        # 10. EEO
        if "gender" in label:
            return "Prefer not to say"
        if "veteran" in label:
            return "I am not a protected veteran"
        if "disability" in label:
            return "No"

        # 11. Behavioral / Why this company
        if "why do you want" in label or "why our company" in label or "why should we hire" in label:
            return "Your company is an industry leader in engineering and data-driven impact. I want to bring my strong technical analytical foundation in SQL, Python, and business problem-solving to drive measurable value for your team."
        if "strength" in label:
            return "Fast analytical problem-solving, attention to detail, and rapid technical adaptability."
        if "cover letter" in label or "summary" in label or "headline" in label:
            title = self.profile.personal_info.current_title or "Data & Business Analyst"
            return f"Proactive {title} with strong analytical expertise in SQL, Python, Excel, and BI dashboards. Eager to solve challenging problems and deliver impactful insights."

        # 12. References
        if "reference" in label:
            return "Available upon request"

        # Default fallback
        return "Yes"

    def _resolve_option(self, label: str, options: List[str]) -> str:
        # Check custom screening answers in profile
        for k, v in self.profile.screening_answers.items():
            if k.lower() in label and v:
                for opt in options:
                    if str(v).lower() in opt.lower():
                        return opt

        # Work Auth / Sponsorship
        if "sponsor" in label:
            target = "no" if not self.profile.work_authorization.requires_sponsorship_now else "yes"
            for opt in options:
                if target in opt.lower():
                    return opt

        if any(w in label for w in ["authorized", "legally eligible", "work permit", "right to work"]):
            target = "yes" if self.profile.work_authorization.authorized_to_work_in_country else "no"
            for opt in options:
                if target in opt.lower():
                    return opt

        # Criminal
        if "criminal" in label or "convicted" in label:
            for opt in options:
                if "no" in opt.lower():
                    return opt

        # Notice period
        if "notice" in label:
            for opt in options:
                if any(w in opt.lower() for w in ["immediate", "0", "15 days", "less than 15"]):
                    return opt

        # Relocation
        if "relocate" in label:
            for opt in options:
                if "yes" in opt.lower() or "open" in opt.lower():
                    return opt

        # EEO Disclosures
        if "gender" in label:
            for opt in options:
                if any(w in opt.lower() for w in ["decline", "prefer not", "not specified"]):
                    return opt

        if "disability" in label:
            for opt in options:
                if any(w in opt.lower() for w in ["no", "do not have", "decline", "prefer not"]):
                    return opt

        if "veteran" in label:
            for opt in options:
                if any(w in opt.lower() for w in ["not a protected", "no", "decline", "prefer not"]):
                    return opt

        if "race" in label or "ethnicity" in label:
            for opt in options:
                if any(w in opt.lower() for w in ["decline", "prefer not", "asian"]):
                    return opt

        # Degree
        if "degree" in label or "education" in label:
            for opt in options:
                if any(w in opt.lower() for w in ["bachelor", "b.tech", "engineering", "btech", "degree"]):
                    return opt

        # Affirmative checks (Yes, Agree)
        for opt in options:
            if opt.strip().lower() in ["yes", "agree", "i agree", "true"]:
                return opt

        # Fallback to first non-empty option
        return options[0] if options else "Yes"
