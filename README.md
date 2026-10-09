# 🚀 Universal AutoJob AI Copilot: Autonomous Naukri.com Applier & Dashboard

A portfolio-grade autonomous job hunting copilot built for **Naukri.com** with **zero-configuration in-app onboarding**:
1. **Zero-Prompt Onboarding**: Upload any candidate PDF resume directly in the web dashboard. Automatically parses skills, education, experience, and contact details without editing code or entering prompts in Antigravity.
2. **Pre-Flight Screening QA System**: Recruiter pop-up screening questions (CTC, notice period, experience, relocation, degree) are auto-extracted from the resume and presented in a dedicated review modal. Novel questions during live runs are saved to a review queue.
3. **Full Live Naukri Filter Suite**: Live-scrapes with all filters (Role, Location, Salary Range LPA, Experience, Freshness, Work Mode, Sort Order) and enforces **Strict 1-Click Direct Apply Only** (skips external redirect jobs).
4. **5-Attempt Strategic Submission Resolver**: Conquers multi-step portal hindrances (DOM clicks, chatbot drawer headline/pill prompts, multi-questionnaire forms, overlay clearance, and JS direct dispatch).
5. **Interactive HTML Dashboard**: Real-time web command center with countdown timers, Excel tracker sync, and safety kill switch.
6. **Detailed Portfolio Architecture Blueprint**: See [PORTFOLIO_GUIDE.md](file:///c:/Users/abcom/Downloads/Job/PORTFOLIO_GUIDE.md) for architecture diagrams and the exact Antigravity prompt playbook.

---

## 🏗️ Architecture Overview

```
                      +-----------------------------+
                      |       Job URLs / ATS        |
                      |    (Greenhouse, Lever...)   |
                      +--------------+--------------+
                                     |
                                     v
+----------------------+     +---------------+     +-----------------------+
| config/profile.yaml  | --> |  Auto Applier | --> | Google Sheets Tracker |
| resumes/resume.pdf   |     |  (Playwright) |     |  (Logged as Applied)  |
+----------------------+     +---------------+     +-----------^-----------+
                                                               |
+----------------------+     +---------------+                 |
|     Gmail Inbox      | --> | Gmail Tracker | ----------------+
| (Status Update Email)|     | & Classifier  |  (Status Updated: Interview /
+----------------------+     +---------------+   Assessment / Rejected)
```

---

## 📦 Project Structure

```
Job/
├── .venv/                      # Python virtual environment
├── config/
│   ├── config.yaml             # Main configuration (Sheet ID, query filters, limits)
│   ├── profile.yaml            # Candidate details, screening answers & cover letter
│   └── credentials/            # Google Cloud credentials (credentials.json / token.json)
├── resumes/
│   └── resume.pdf              # Your resume file
├── src/
│   ├── applier/
│   │   ├── base.py             # Playwright base automation framework
│   │   ├── greenhouse.py       # Greenhouse ATS direct applier
│   │   ├── lever.py            # Lever ATS direct applier
│   │   ├── question_solver.py  # Screening question resolver
│   │   └── factory.py          # URL router & applier selector
│   ├── google_services/
│   │   ├── auth.py             # Unified OAuth 2.0 / Service Account manager
│   │   ├── sheets_manager.py   # Google Sheets CRUD & column formatting
│   │   └── gmail_tracker.py    # Gmail email scanning & auto-updating
│   ├── parser/
│   │   └── email_classifier.py # Email parsing for company, role, & status
│   ├── config.py               # Settings loader
│   ├── models.py               # Data models & schemas
│   └── runner.py               # Central CLI tool
├── tests/                      # Automated test suite (100% passing)
├── .env.example                # Environment variables template
├── requirements.txt            # Python dependencies
└── README.md                   # Documentation
```

---

## ⚡ Quick Start Guide

### 1. Configure Your Candidate Profile
Edit [config/profile.yaml](file:///c:/Users/abcom/Downloads/Job/config/profile.yaml) with your personal information, work authorization, salary expectations, and screening answers:
- Name, Email, Phone, Location
- LinkedIn, GitHub, Portfolio links
- Work authorization & visa requirements
- Answers to typical questions (notice period, gender/veteran/disability preferences)

Place your PDF resume into [resumes/resume.pdf](file:///c:/Users/abcom/Downloads/Job/resumes/resume.pdf).

---

### 2. Set Up Google Cloud (Gmail & Sheets API)

To enable automatic tracking in Gmail and Google Sheets:

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g. `Job-Tracker`).
3. Enable **Google Sheets API** and **Gmail API** in **APIs & Services > Library**.
4. Go to **APIs & Services > Credentials**:
   - Click **Create Credentials > OAuth client ID**.
   - Select Application type: **Desktop App**.
   - Download the client secret JSON file and save it as:
     ```
     config/credentials/credentials.json
     ```
5. Create a Google Sheet:
   - Open [Google Sheets](https://sheets.new) and create a new blank spreadsheet.
   - Copy the Spreadsheet ID from the URL:
     `https://docs.google.com/spreadsheets/d/`**`<YOUR_SPREADSHEET_ID>`**`/edit`
   - Paste it into [config/config.yaml](file:///c:/Users/abcom/Downloads/Job/config/config.yaml) under `google.spreadsheet_id` or in `.env` as `GOOGLE_SHEET_ID`.

---

## 🛠️ CLI Usage & Commands

All operations are executed via `src/runner.py`:

### 1. Test Email Classification (Offline / No Setup Required)
Test how the system detects company, role, and application status from job emails:
```powershell
.\.venv\Scripts\python.exe src/runner.py test-parser --subject "Invitation to Interview: Senior Backend Engineer at Datadog" --sender "recruiting@datadoghq.com" --body "We would love to schedule a phone interview with our team."
```

### 2. Auto-Apply to Jobs (Naukri, Indeed India, Greenhouse, Lever)

#### A. Naukri.com
Naukri requires a 1-time browser login to store session cookies (`config/credentials/naukri_state.json`):
```powershell
# 1. Log in once into your Naukri account
.\.venv\Scripts\python.exe src/runner.py naukri-login

# 2. Apply to any Naukri job posting
.\.venv\Scripts\python.exe src/runner.py apply --url "https://www.naukri.com/job-listings-data-analyst..." --submit
```

#### B. Indeed (India & Global)
Supports "Easily apply" jobs on `in.indeed.com` and `indeed.com`:
```powershell
# Test in dry-run mode (captures review screenshot without submitting)
.\.venv\Scripts\python.exe src/runner.py apply --url "https://in.indeed.com/viewjob?jk=..."

# Live submission & Google Sheets logging
.\.venv\Scripts\python.exe src/runner.py apply --url "https://in.indeed.com/viewjob?jk=..." --submit
```

#### C. Greenhouse & Lever
```powershell
.\.venv\Scripts\python.exe src/runner.py apply --url "https://boards.greenhouse.io/<company>/jobs/<id>" --submit
```

### 3. Sync Gmail Updates to Google Sheets
Scans your inbox for job application emails (including **Naukri alerts**, **Indeed applications**, and ATS notifications):
```powershell
.\.venv\Scripts\python.exe src/runner.py sync --lookback 30
```
*(On first run, a Google OAuth consent page will open in your browser to authorize access, and your login session will be cached in `config/credentials/token.json`)*.

### 4. View Application Status Table
Displays all tracked applications directly in your terminal:
```powershell
.\.venv\Scripts\python.exe src/runner.py list
```

### 5. Run Continuous Background Sync (Daemon)
Monitors Gmail periodically (e.g. every 30 minutes) and automatically keeps Google Sheets updated:
```powershell
.\.venv\Scripts\python.exe src/runner.py daemon --interval 30
```

---

## 📊 Google Sheets Tracking Columns

The sheet automatically configures with formatted headers:
1. **Application ID**: Unique identifier (e.g. `GH-a1b2c3d4` or `AUTO-9f8e7d`)
2. **Date Applied**: Timestamp when applied or email received
3. **Company**: Company name
4. **Job Title**: Position role
5. **Location**: Job location
6. **Job URL**: Application link
7. **Platform**: Source (Greenhouse, Lever, Auto-Detected Email)
8. **Status**: `Applied` | `Under Review` | `Assessment Sent` | `Interview Scheduled` | `Offer Received` | `Rejected`
9. **Last Updated**: Timestamp of latest progression
10. **Gmail Thread ID**: Direct thread reference for cross-linking
11. **Notes**: Extracted email snippets and audit log

---

## 🧪 Running Automated Tests

Run the test suite with pytest:
```powershell
.\.venv\Scripts\pytest.exe -v
```
All 11 unit tests verify models, parsing heuristics, screening question matching, and sheet operations.
