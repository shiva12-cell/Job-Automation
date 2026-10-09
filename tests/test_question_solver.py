import pytest
from src.models import CandidateProfile, CandidatePersonalInfo, CandidateWorkAuthorization
from src.applier.question_solver import QuestionSolver


@pytest.fixture
def sample_profile():
    return CandidateProfile(
        personal_info=CandidatePersonalInfo(
            first_name="Alex",
            last_name="Doe",
            email="alex@example.com",
            phone="+1234567890",
            location="San Francisco, CA",
            linkedin_url="https://linkedin.com/in/alex",
            github_url="https://github.com/alex",
            portfolio_url="https://alex.dev",
        ),
        work_authorization=CandidateWorkAuthorization(
            authorized_to_work_in_country=True,
            requires_sponsorship_now=False,
            requires_sponsorship_future=False,
        ),
        screening_answers={
            "salary": "130000",
            "notice": "2 weeks",
            "gender": "Decline to self-identify",
        },
    )


def test_question_solver_text(sample_profile):
    solver = QuestionSolver(sample_profile)

    # Sponsorship
    assert solver.answer_text_question("Will you require visa sponsorship now or in the future?") == "No"

    # Authorization
    assert solver.answer_text_question("Are you legally authorized to work in the United States?") == "Yes"

    # Salary
    assert solver.answer_text_question("What is your expected salary?") == "130000"

    # Location
    assert solver.answer_text_question("What is your current city / location?") == "San Francisco, CA"

    # LinkedIn
    assert solver.answer_text_question("LinkedIn Profile URL") == "https://linkedin.com/in/alex"


def test_question_solver_options(sample_profile):
    solver = QuestionSolver(sample_profile)

    # Select sponsorship option
    options = ["Yes, I will need sponsorship", "No, I am authorized without sponsorship"]
    assert solver.select_best_option("Do you need sponsorship?", options) == "No, I am authorized without sponsorship"

    # Select gender disclosure
    gender_options = ["Male", "Female", "Non-binary", "Decline to self-identify"]
    assert solver.select_best_option("Gender identity", gender_options) == "Decline to self-identify"
