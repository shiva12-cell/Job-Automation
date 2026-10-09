"""
Configuration loader.
Loads YAML configurations and candidate profiles with fallback to environment variables,
and dynamically manages active candidate profiles saved via the web dashboard.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from dotenv import load_dotenv
from src.models import (
    CandidateProfile,
    CandidatePersonalInfo,
    CandidateWorkAuthorization,
    CandidateEducation,
    CandidateExperience,
)

# Load .env if present
load_dotenv()

PROFILES_DIR = Path("config/profiles")
ACTIVE_PROFILE_FILE = PROFILES_DIR / "active_profile.json"


def load_yaml(file_path: str) -> Dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    cfg = load_yaml(config_path)

    # Allow environment variable overrides
    if os.getenv("GOOGLE_SHEET_ID"):
        cfg.setdefault("google", {})["spreadsheet_id"] = os.getenv("GOOGLE_SHEET_ID")
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS_FILE"):
        cfg.setdefault("google", {})["client_secrets_file"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_FILE")
    if os.getenv("GOOGLE_TOKEN_FILE"):
        cfg.setdefault("google", {})["token_file"] = os.getenv("GOOGLE_TOKEN_FILE")
    if os.getenv("RESUME_PATH"):
        cfg.setdefault("applier", {})["resume_path"] = os.getenv("RESUME_PATH")

    return cfg


def load_candidate_profile(
    profile_path: str = "config/profile.yaml",
    resume_path: str = "resumes/resume.pdf"
) -> CandidateProfile:
    """
    Loads active candidate profile.
    Prioritizes config/profiles/active_profile.json (saved from in-app uploads).
    Falls back to config/profile.yaml if active_profile.json does not exist.
    """
    # 1. Check in-app saved dynamic profile first
    if ACTIVE_PROFILE_FILE.exists():
        try:
            with open(ACTIVE_PROFILE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            personal = CandidatePersonalInfo(**data.get("personal_info", {}))
            auth = CandidateWorkAuthorization(**data.get("work_authorization", {}))
            edu = CandidateEducation(**data.get("education", {})) if data.get("education") else None
            exp = CandidateExperience(**data.get("experience", {})) if data.get("experience") else None

            active_resume = data.get("resume_path") or resume_path
            return CandidateProfile(
                personal_info=personal,
                work_authorization=auth,
                education=edu,
                experience=exp,
                screening_answers=data.get("screening_answers", {}),
                cover_letter=data.get("cover_letter", ""),
                resume_path=active_resume,
            )
        except Exception as e:
            print(f"[Config Warning] Error loading active_profile.json ({e}), falling back to {profile_path}")

    # 2. Fallback to YAML profile
    path = Path(profile_path)
    if not path.exists():
        raise FileNotFoundError(f"Candidate profile not found at {path.resolve()}. Please create one from the template.")

    data = load_yaml(str(path))
    personal = CandidatePersonalInfo(**data.get("personal_info", {}))
    auth = CandidateWorkAuthorization(**data.get("work_authorization", {}))
    edu = CandidateEducation(**data.get("education", {})) if data.get("education") else None
    exp = CandidateExperience(**data.get("experience", {})) if data.get("experience") else None

    return CandidateProfile(
        personal_info=personal,
        work_authorization=auth,
        education=edu,
        experience=exp,
        screening_answers=data.get("screening_answers", {}),
        cover_letter=data.get("cover_letter", ""),
        resume_path=resume_path,
    )


def save_active_profile(profile_dict: Dict[str, Any]) -> CandidateProfile:
    """
    Saves candidate profile dictionary to config/profiles/active_profile.json.
    Ensures directory exists and returns updated CandidateProfile object.
    """
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    with open(ACTIVE_PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile_dict, f, indent=2, ensure_ascii=False)

    return load_candidate_profile()
