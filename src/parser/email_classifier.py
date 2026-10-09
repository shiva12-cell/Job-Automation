"""
Email Classifier & Information Extractor for Job Application Emails.
Extracts company name, job role, and application status from Gmail messages.
"""

import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from src.models import ApplicationStatus, EmailJobEvent
from datetime import datetime


# Regular expression patterns for status classification
STATUS_PATTERNS = {
    ApplicationStatus.OFFER: [
        r"\boffer letter\b",
        r"\bformal offer\b",
        r"\bdelighted to offer\b",
        r"\bpleased to offer\b",
        r"\bjob offer\b",
        r"\bcongratulations.*offer\b",
    ],
    ApplicationStatus.REJECTED: [
        r"\bunfortunately\b",
        r"\bregret to inform\b",
        r"\bnot moving forward\b",
        r"\bdecided to pursue other candidates\b",
        r"\bother candidates whose qualifications\b",
        r"\bwill not be moving forward\b",
        r"\bnot selected for\b",
        r"\bposition has been filled\b",
        r"\bwish you (the best|every success) in your job search\b",
        r"\bimpressive.*however\b",
    ],
    ApplicationStatus.INTERVIEW: [
        r"\binvitation to interview\b",
        r"\bschedule (an?|your) interview\b",
        r"\bschedule a (call|chat|phone screen|conversation)\b",
        r"\binterview request\b",
        r"\bnext steps.*interview\b",
        r"\bchat with (our team|the hiring manager|the recruiter)\b",
        r"\bcalendly\.com\b",
        r"\bcalendar invite\b",
    ],
    ApplicationStatus.ASSESSMENT: [
        r"\bonline assessment\b",
        r"\bhackerrank\b",
        r"\bcodility\b",
        r"\btake-home\b",
        r"\bcoding challenge\b",
        r"\btechnical assessment\b",
        r"\bcomplete the assessment\b",
    ],
    ApplicationStatus.UNDER_REVIEW: [
        r"\bunder review\b",
        r"\breviewing your application\b",
        r"\bcurrently reviewing\b",
        r"\brecruiter viewed your application\b",
        r"\brecruiter viewed your cv\b",
        r"\brecruiter downloaded your (cv|resume)\b",
        r"\bapplication viewed\b",
        r"\bshortlisted for\b",
    ],
    ApplicationStatus.APPLIED: [
        r"\bthank you for applying\b",
        r"\bapplication received\b",
        r"\breceived your application\b",
        r"\bapplication submitted\b",
        r"\bthanks for applying\b",
        r"\bthank you for your application\b",
        r"\bwe have received your resume\b",
        r"\bapplication confirmation\b",
        r"\bapplication sent for\b",
        r"\bapplication has been sent\b",
        r"\bapplication was sent\b",
        r"\bindeed application:\b",
        r"\bapplied successfully\b",
        r"\bsuccessfully applied\b",
    ],
}

# Common ATS email domains & known job board domains
ATS_DOMAINS = [
    "naukri.com",
    "naukrialerts.com",
    "indeed.com",
    "indeedapply.com",
    "greenhouse.io",
    "lever.co",
    "myworkday.com",
    "workday.com",
    "smartrecruiters.com",
    "ashbyhq.com",
    "jobvite.com",
    "icims.com",
    "bamboohr.com",
    "breezy.hr",
    "recruitee.com",
]


class EmailClassifier:
    """Classifies emails related to job applications and extracts structured metadata."""

    @staticmethod
    def clean_text(html_or_text: str) -> str:
        """Strips HTML tags and normalizes whitespace."""
        if not html_or_text:
            return ""
        if "<" in html_or_text and ">" in html_or_text:
            try:
                soup = BeautifulSoup(html_or_text, "html.parser")
                text = soup.get_text(separator=" ")
            except Exception:
                text = html_or_text
        else:
            text = html_or_text
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def classify_status(cls, subject: str, body: str) -> Tuple[ApplicationStatus, float]:
        """
        Determines the application status and confidence score from subject and body.
        Checks in strict precedence order: Offer > Rejected > Interview > Assessment > Under Review > Applied
        """
        combined = f"{subject}\n{body}".lower()

        # Check status patterns in priority order
        for status, patterns in STATUS_PATTERNS.items():
            for pattern in patterns:
                # Subject matches carry higher weight
                if re.search(pattern, subject.lower()):
                    return status, 0.95
                if re.search(pattern, combined):
                    return status, 0.85

        return ApplicationStatus.UNKNOWN, 0.3

    @classmethod
    def extract_company_name(cls, sender: str, subject: str, body: str) -> str:
        """
        Attempts to extract company name using multiple heuristics:
        1. From Subject patterns ('at [Company]', 'with [Company]', 'to [Company]')
        2. From Sender display name ('Company Careers', 'Recruiting at Company')
        3. From Sender domain name
        """
        # 1. Subject extraction:
        # e.g., "Thank you for applying to Acme Corp"
        # e.g., "Indeed Application: Data Analyst - Swiggy"
        # e.g., "Application sent for Data Analyst at Zomato"
        patterns = [
            r"Indeed Application:\s*(?:.+?)\s*-\s*([A-Za-z0-9&.,' ]{2,30})",
            r"(?:applying to|application to|applied to|role at|position at|application at|interview with)\s+([A-Z0-9][A-Za-z0-9&.,' ]{2,30}?)(?:\s+for|\s+-|\s+!|\s+\(|\.|$)",
            r"(?:sent to|submitted to)\s+([A-Z0-9][A-Za-z0-9&.,' ]{2,30}?)(?:\s+for|\s+-|\s+!|\s+\(|\.|$)",
            r"(?:application sent for .+? at|viewed your application for .+? at)\s+([A-Z0-9][A-Za-z0-9&.,' ]{2,30}?)(?:\s+on Naukri|\s+-|\s+!|\s+\(|\.|$)",
            r"(?:welcome to|careers at)\s+([A-Z0-9][A-Za-z0-9&.,' ]{2,25}?)(?:\s+for|\s+-|\s+!|\s+\(|\.|$)",
            r"\[([A-Z0-9][A-Za-z0-9&.,' ]{2,25}?)\]\s+(?:Application|Thank you|Interview)",
        ]

        for pat in patterns:
            match = re.search(pat, subject, re.IGNORECASE)
            if match:
                company = match.group(1).strip(" .,-!")
                if company and len(company) > 1 and company.lower() not in ["the", "your", "our", "naukri", "indeed"]:
                    return company

        # 2. Sender Display Name:
        # e.g. "Airbnb Careers <careers@airbnb.com>" -> "Airbnb"
        sender_match = re.search(r"^\"?([A-Za-z0-9\s.,&'-]+?)\"?\s*<", sender)
        if sender_match:
            display_name = sender_match.group(1).strip()
            # Clean common suffixes like "Recruiting", "Careers", "Talent Acquisition", "Jobs"
            cleaned_sender = re.sub(
                r"\s+(careers|recruiting|talent|team|talent acquisition|jobs|people ops|hiring)$",
                "",
                display_name,
                flags=re.IGNORECASE,
            ).strip()
            if cleaned_sender and len(cleaned_sender) > 1 and not any(ats in cleaned_sender.lower() for ats in ["greenhouse", "lever", "workday", "smartrecruiters", "ashby", "naukri", "indeed"]):
                return cleaned_sender

        # 3. Domain Name heuristic (fallback):
        # e.g. "jobs@uber.com" -> "Uber"
        domain_match = re.search(r"@([a-zA-Z0-9-]+)\.[a-zA-Z]{2,}", sender)
        if domain_match:
            domain = domain_match.group(1).lower()
            if domain not in ["gmail", "outlook", "yahoo", "hotmail", "mail", "sendgrid", "mailer", "naukri", "indeed"] and not any(ats.startswith(domain) for ats in ATS_DOMAINS):
                return domain.capitalize()

        return "Unknown Company"

    @classmethod
    def extract_job_title(cls, subject: str, body: str) -> Optional[str]:
        """
        Extracts potential job title from subject or opening lines of body.
        e.g. "for the Senior Software Engineer position", "Indeed Application: Data Analyst - Swiggy", "Application sent for Data Analyst at Zomato"
        """
        # Patterns to check in subject first, then body
        patterns = [
            r"Indeed Application:\s*([A-Za-z0-9\s/.,#+-]{3,50}?)(?:\s+-\s+|\s+at\s+|$)",
            r"(?:application sent for|viewed your application for)\s+([A-Za-z0-9\s/.,#+-]{3,50}?)(?:\s+at|\s+with|\s+-|$)",
            r"(?:interview:?|invitation to interview:?|interview for:?)\s+([A-Za-z0-9\s/.,#+-]{3,50}?)(?:\s+at|\s+with|\s+-|$)",
            r"(?:in the|for the|as a|as an)\s+([A-Za-z0-9\s/.,#+-]{3,50}?)\s+(?:position|role|job|opening|opportunity)",
            r"\b([A-Z][A-Za-z0-9\s/.,#+-]{2,40}?)\s+(?:position|role|job|opening|opportunity)\b",
            r"(?:application for:?|role of:?|position of:?|role as:?|position as:?)\s+([A-Za-z0-9\s/.,#+-]{3,50}?)(?:$|\n|\.|\sat\s|,|\()",
            r"(?:applied for\s+(?:the|a)?)\s*([A-Za-z0-9\s/.,#+-]{3,50}?)(?:$|\n|\.|\sat\s|,|\()",
        ]

        # Prioritize matching in subject first
        for text in [subject, body[:500]]:
            for pat in patterns:
                match = re.search(pat, text, re.IGNORECASE)
                if match:
                    title = match.group(1).strip(" -:.,")
                    # Clean out common noise prefix words
                    title = re.sub(r"^(applying to the|applying to a|applying to|submitting for the|interest in the|the|a|an|at)\s+", "", title, flags=re.IGNORECASE).strip()
                    # Clean out trailing company references e.g. "Software Engineer at Google"
                    title = re.sub(r"\s+at\s+.*$", "", title, flags=re.IGNORECASE).strip()
                    if len(title) > 2 and len(title) < 50 and not any(verb in title.lower() for verb in ["interest in", "working at", "update regarding"]):
                        # Check it's not just "at Company"
                        if not title.lower().startswith("at "):
                            return title

        return None

    @classmethod
    def parse_message(
        cls,
        message_id: str,
        thread_id: str,
        date_received: datetime,
        sender: str,
        subject: str,
        body_text: str,
    ) -> Optional[EmailJobEvent]:
        """
        Parses an email message into an EmailJobEvent.
        Returns None if message is not identified as job-related.
        """
        cleaned_body = cls.clean_text(body_text)
        status, confidence = cls.classify_status(subject, cleaned_body)

        # If status is unknown and no keywords match, it's not a job application email
        if status == ApplicationStatus.UNKNOWN and confidence < 0.4:
            return None

        company = cls.extract_company_name(sender, subject, cleaned_body)
        job_title = cls.extract_job_title(subject, cleaned_body)

        # Snippet for notes
        snippet = cleaned_body[:200] if len(cleaned_body) > 200 else cleaned_body

        return EmailJobEvent(
            message_id=message_id,
            thread_id=thread_id,
            date_received=date_received,
            sender=sender,
            subject=subject,
            detected_company=company,
            detected_job_title=job_title,
            status=status,
            snippet=snippet,
            confidence=confidence,
        )
