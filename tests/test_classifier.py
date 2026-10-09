from datetime import datetime
import pytest
from src.models import ApplicationStatus
from src.parser.email_classifier import EmailClassifier


def test_classify_applied():
    event = EmailClassifier.parse_message(
        message_id="msg1",
        thread_id="th1",
        date_received=datetime.now(),
        sender="Stripe Careers <careers@stripe.com>",
        subject="Thank you for applying to Stripe for Software Engineer",
        body_text="Hi Alex, we have received your application for the Software Engineer role.",
    )
    assert event is not None
    assert event.detected_company == "Stripe"
    assert event.detected_job_title == "Software Engineer"
    assert event.status == ApplicationStatus.APPLIED


def test_classify_interview():
    event = EmailClassifier.parse_message(
        message_id="msg2",
        thread_id="th2",
        date_received=datetime.now(),
        sender="Datadog <recruiting@datadoghq.com>",
        subject="Invitation to Interview: Senior Backend Engineer at Datadog",
        body_text="We would like to invite you for a 45-minute phone screen with the hiring manager.",
    )
    assert event is not None
    assert event.detected_company == "Datadog"
    assert event.detected_job_title == "Senior Backend Engineer"
    assert event.status == ApplicationStatus.INTERVIEW


def test_classify_rejection():
    event = EmailClassifier.parse_message(
        message_id="msg3",
        thread_id="th3",
        date_received=datetime.now(),
        sender="Airbnb Talent <talent@airbnb.com>",
        subject="Update regarding your application at Airbnb",
        body_text="Thank you for your interest in the Full Stack Developer position at Airbnb. Unfortunately, we have decided to pursue other candidates.",
    )
    assert event is not None
    assert event.detected_company == "Airbnb"
    assert event.detected_job_title == "Full Stack Developer"
    assert event.status == ApplicationStatus.REJECTED


def test_classify_assessment():
    event = EmailClassifier.parse_message(
        message_id="msg4",
        thread_id="th4",
        date_received=datetime.now(),
        sender="Amazon University <no-reply@hackerrank.com>",
        subject="Amazon: Online assessment invitation for SDE Intern",
        body_text="Please complete your online assessment on HackerRank within 5 business days.",
    )
    assert event is not None
    assert event.status == ApplicationStatus.ASSESSMENT


def test_classify_naukri():
    event = EmailClassifier.parse_message(
        message_id="msg5",
        thread_id="th5",
        date_received=datetime.now(),
        sender="Naukri Job Alerts <applications@naukri.com>",
        subject="Application sent for Data Analyst at Swiggy",
        body_text="Your application has been successfully sent to the recruiter at Swiggy on Naukri.com.",
    )
    assert event is not None
    assert event.detected_company == "Swiggy"
    assert event.detected_job_title == "Data Analyst"
    assert event.status == ApplicationStatus.APPLIED


def test_classify_naukri_recruiter_viewed():
    event = EmailClassifier.parse_message(
        message_id="msg6",
        thread_id="th6",
        date_received=datetime.now(),
        sender="Naukri <alerts@naukri.com>",
        subject="Recruiter viewed your application for Data Analyst at Zomato",
        body_text="Good news! The recruiter from Zomato viewed your application and downloaded your CV.",
    )
    assert event is not None
    assert event.detected_company == "Zomato"
    assert event.detected_job_title == "Data Analyst"
    assert event.status == ApplicationStatus.UNDER_REVIEW


def test_classify_indeed():
    event = EmailClassifier.parse_message(
        message_id="msg7",
        thread_id="th7",
        date_received=datetime.now(),
        sender="Indeed Apply <indeedapply@indeed.com>",
        subject="Indeed Application: Business Analyst - Meesho",
        body_text="Your application was sent to Meesho. They will reach out if there is a match.",
    )
    assert event is not None
    assert event.detected_company == "Meesho"
    assert event.detected_job_title == "Business Analyst"
    assert event.status == ApplicationStatus.APPLIED

