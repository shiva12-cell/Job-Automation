import pytest
from src.matcher import SkillMatcher
from src.models import CandidateProfile, CandidatePersonalInfo


@pytest.fixture
def sample_profile():
    return CandidateProfile(
        personal_info=CandidatePersonalInfo(
            first_name="Shiva",
            last_name="Upadhyay",
            email="shiva@example.com",
            phone="+91 1234567890",
            location="Any Location (Remote / Pan-India)",
        ),
        screening_answers={
            "skills": "python, sql, excel, power bi, tableau, data analysis, statistics"
        }
    )


def test_matcher_qualifies_at_65_percent(sample_profile):
    matcher = SkillMatcher(sample_profile, threshold_pct=65.0)
    job_title = "Data Analyst (0-2 years exp)"
    job_desc = "Looking for an entry level Data Analyst (0-2 years) skilled in Python, SQL, Excel, and Power BI."

    is_match, score, matched, chance = matcher.is_match(job_title, job_desc)
    assert is_match is True
    assert score >= 65.0
    assert "python" in matched
    assert "sql" in matched
    assert chance in ["High", "Mid"]


def test_matcher_rejects_exceeding_experience(sample_profile):
    matcher = SkillMatcher(sample_profile, threshold_pct=65.0)
    # Role matching skills, but demanding 5+ years experience
    job_title = "Senior Data Analyst"
    job_desc = "Mandatory 5+ years of experience in Python, SQL, Power BI, and Tableau."

    is_match, score, _, chance = matcher.is_match(job_title, job_desc)
    # Should be rejected because experience requirement exceeds 0-2 years
    assert is_match is False
    assert chance == "Low"


def test_matcher_rejects_unrelated_skills(sample_profile):
    matcher = SkillMatcher(sample_profile, threshold_pct=65.0)
    job_title = "Java Backend Developer"
    job_desc = "We require Java, Spring Boot, Microservices, Kubernetes, Docker, and AWS."

    is_match, score, _, chance = matcher.is_match(job_title, job_desc)
    assert is_match is False
    assert score < 65.0
    assert chance == "Low"


def test_matcher_matches_expanded_keywords(sample_profile):
    matcher = SkillMatcher(sample_profile, threshold_pct=65.0)
    
    # Business Analyst role matching B.Tech CSE skills
    ba_title = "Associate Business Analyst"
    ba_desc = "Need business analyst with SQL, Excel, data analysis, reporting, and agile knowledge (0-1 year experience)."
    is_match, score, matched, chance = matcher.is_match(ba_title, ba_desc)
    assert is_match is True
    assert "business analyst" in matched or "sql" in matched
    assert chance in ["High", "Mid"]

    # AI Product Owner / Product Management role
    po_title = "Associate AI Product Owner / Product Management"
    po_desc = "Looking for AI product owner or product management associate with Python, data analysis, and agile background."
    is_match, score, matched, chance = matcher.is_match(po_title, po_desc)
    assert is_match is True
    assert chance in ["High", "Mid"]

    # Any Analyst role matching B.Tech CSE
    cse_title = "Junior Analytics Engineer / Tech Analyst"
    cse_desc = "Seeking graduate with B.Tech CSE background, Python, SQL, data analysis, and problem solving skills."
    is_match, score, matched, chance = matcher.is_match(cse_title, cse_desc)
    assert is_match is True
    assert chance == "High"


def test_matcher_chance_calculation(sample_profile):
    matcher = SkillMatcher(sample_profile, threshold_pct=65.0)

    # High chance: high score with core project tools (Python, SQL, Power BI)
    chance_high = matcher.calculate_chance(85.0, ["python", "sql", "power bi"], "Data Analyst", "Python SQL Power BI")
    assert chance_high == "High"

    # Mid chance: 68% score
    chance_mid = matcher.calculate_chance(68.0, ["excel", "reporting"], "Junior Analyst", "Excel Reporting")
    assert chance_mid == "Mid"

    # Low chance: under 65%
    chance_low = matcher.calculate_chance(50.0, ["excel"], "Admin", "Excel")
    assert chance_low == "Low"


