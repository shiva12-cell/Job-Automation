"""
AutoJob AI - Streamlit Command Center & Analytics Dashboard
Built for local monitoring and Streamlit Community Cloud (share.streamlit.io).
"""

import os
from pathlib import Path
from datetime import datetime
import pandas as pd
import yaml
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="AutoJob AI | Copilot Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #1E88E5, #43A047);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #6c757d;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 18px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
    }
    .metric-title {
        color: #6c757d;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        color: #1a1a1a;
        font-size: 2rem;
        font-weight: 700;
        margin: 5px 0;
    }
    .metric-badge {
        font-size: 0.8rem;
        padding: 3px 8px;
        border-radius: 12px;
        font-weight: 600;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 16px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 18px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Helpers & Data Loading
# ---------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.resolve()
DEFAULT_EXCEL_PATH = PROJECT_ROOT / "Job_Applications_Tracker.xlsx"
PROFILE_PATH = PROJECT_ROOT / "config" / "profile.yaml"

@st.cache_data(ttl=30)
def load_excel_data(file_path: Path):
    """Loads all sheets from the Excel application tracker."""
    if not file_path.exists():
        return None, []
    try:
        excel_file = pd.ExcelFile(file_path)
        sheet_names = excel_file.sheet_names
        sheets_dict = {}
        for s in sheet_names:
            try:
                sheets_dict[s] = pd.read_excel(excel_file, sheet_name=s)
            except Exception:
                continue
        return sheets_dict, sheet_names
    except Exception as e:
        st.error(f"Error loading Excel file: {e}")
        return None, []

def load_profile():
    """Loads candidate profile configuration."""
    if not PROFILE_PATH.exists():
        return None
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None

# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/rocket.png", width=64)
    st.title("AutoJob AI")
    st.caption("Autonomous Application Copilot")

    st.markdown("---")
    st.subheader("⚙️ Data Source")
    
    excel_exists = DEFAULT_EXCEL_PATH.exists()
    if excel_exists:
        st.success("✅ `Job_Applications_Tracker.xlsx` Connected")
        file_mtime = datetime.fromtimestamp(DEFAULT_EXCEL_PATH.stat().st_mtime)
        st.caption(f"Last updated: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        st.warning("⚠️ Local Excel file not found. Upload below or sync via Google Sheets.")

    uploaded_file = st.file_uploader("Upload Tracker (.xlsx)", type=["xlsx"])
    
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    profile = load_profile()
    if profile:
        st.subheader("👤 Candidate Info")
        p_info = profile.get("personal_info", {})
        st.markdown(f"**{p_info.get('first_name', '')} {p_info.get('last_name', '')}**")
        st.caption(f"🎯 {p_info.get('current_title', 'Job Seeker')} | 📍 {p_info.get('location', 'India')}")
        if p_info.get("linkedin_url"):
            st.markdown(f"[🔗 LinkedIn]({p_info.get('linkedin_url')})")
        if p_info.get("github_url"):
            st.markdown(f"[🐙 GitHub]({p_info.get('github_url')})")

    st.markdown("---")
    st.info("💡 **Streamlit Cloud**: Link your GitHub repository at [share.streamlit.io](https://share.streamlit.io) to host this dashboard online.")

# ---------------------------------------------------------
# Main Content
# ---------------------------------------------------------
st.markdown('<div class="main-header">🚀 AutoJob AI Copilot Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Real-time job application intelligence, status tracking & ATS analytics</div>', unsafe_allow_html=True)

# Select Data Source
sheets_dict = None
sheet_names = []

if uploaded_file is not None:
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        sheet_names = excel_file.sheet_names
        sheets_dict = {s: pd.read_excel(excel_file, sheet_name=s) for s in sheet_names}
    except Exception as err:
        st.error(f"Failed to read uploaded file: {err}")
elif excel_exists:
    sheets_dict, sheet_names = load_excel_data(DEFAULT_EXCEL_PATH)

if not sheets_dict:
    st.warning("No application data available yet. Start the AutoJob AI bot or upload your `Job_Applications_Tracker.xlsx` tracker file.")
    st.stop()

# Master DataFrame selection (prefer 'All Applications' or fallback to first sheet)
master_sheet = "All Applications" if "All Applications" in sheets_dict else sheet_names[0]
df_master = sheets_dict[master_sheet].copy()

# Ensure required columns exist
for col in ["Company", "Job Title", "Platform", "Status", "Date Applied"]:
    if col not in df_master.columns:
        df_master[col] = "Unknown"

# Format Dates if possible
if "Date Applied" in df_master.columns:
    df_master["Date Applied"] = pd.to_datetime(df_master["Date Applied"], errors="coerce")

# Clean Status
df_master["Status"] = df_master["Status"].fillna("Applied")

# ---------------------------------------------------------
# Top KPI Metric Cards
# ---------------------------------------------------------
total_apps = len(df_master)
naukri_apps = len(df_master[df_master["Platform"].str.contains("Naukri", case=False, na=False)])
indeed_apps = len(df_master[df_master["Platform"].str.contains("Indeed", case=False, na=False)])
interviews = len(df_master[df_master["Status"].str.contains("Interview|Assessment|Shortlist", case=False, na=False)])
companies_count = df_master["Company"].nunique()

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
with kpi1:
    st.metric(label="Total Applications", value=total_apps, delta="All Platforms")
with kpi2:
    st.metric(label="Naukri.com", value=naukri_apps, delta="Auto-Applied")
with kpi3:
    st.metric(label="Indeed / Others", value=indeed_apps, delta="Synced")
with kpi4:
    st.metric(label="Interviews / Shortlists", value=interviews, delta="Active Pipeline")
with kpi5:
    st.metric(label="Unique Companies", value=companies_count)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------
# Navigation Tabs
# ---------------------------------------------------------
tab_analytics, tab_tracker, tab_profile, tab_deploy = st.tabs([
    "📊 Analytics & Insights",
    "📋 Applications Tracker",
    "👤 Candidate Profile & QA",
    "☁️ Streamlit Cloud Deploy Guide"
])

# =========================================================
# TAB 1: ANALYTICS & INSIGHTS
# =========================================================
with tab_analytics:
    row1_c1, row1_c2 = st.columns([1, 1])

    with row1_c1:
        st.subheader("Platform Distribution")
        platform_counts = df_master["Platform"].value_counts().reset_index()
        platform_counts.columns = ["Platform", "Count"]
        fig_platform = px.pie(
            platform_counts, 
            values="Count", 
            names="Platform", 
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Safe
        )
        fig_platform.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=320)
        st.plotly_chart(fig_platform, use_container_width=True)

    with row1_c2:
        st.subheader("Status Breakdown")
        status_counts = df_master["Status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Count"]
        fig_status = px.bar(
            status_counts, 
            x="Status", 
            y="Count", 
            color="Status",
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_status.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=320, showlegend=False)
        st.plotly_chart(fig_status, use_container_width=True)

    row2_c1, row2_c2 = st.columns([1, 1])

    with row2_c1:
        st.subheader("Top 10 Target Companies")
        top_companies = df_master["Company"].value_counts().head(10).reset_index()
        top_companies.columns = ["Company", "Applications"]
        fig_companies = px.bar(
            top_companies,
            x="Applications",
            y="Company",
            orientation="h",
            color="Applications",
            color_continuous_scale="Blues"
        )
        fig_companies.update_layout(
            yaxis=dict(autorange="reversed"),
            margin=dict(t=10, b=10, l=10, r=10),
            height=340
        )
        st.plotly_chart(fig_companies, use_container_width=True)

    with row2_c2:
        st.subheader("Applications Timeline")
        if "Date Applied" in df_master.columns and df_master["Date Applied"].notna().any():
            timeline_df = df_master.dropna(subset=["Date Applied"]).copy()
            timeline_df["Date"] = timeline_df["Date Applied"].dt.date
            daily_counts = timeline_df.groupby("Date").size().reset_index(name="Applications")
            fig_timeline = px.line(
                daily_counts, 
                x="Date", 
                y="Applications", 
                markers=True,
                title=""
            )
            fig_timeline.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=340)
            st.plotly_chart(fig_timeline, use_container_width=True)
        else:
            st.info("No dated entries available for timeline rendering.")

# =========================================================
# TAB 2: APPLICATIONS TRACKER
# =========================================================
with tab_tracker:
    st.subheader("Search & Filter Applications")

    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 2])
    
    with filter_col1:
        selected_sheet = st.selectbox("Select Tracker Sheet", sheet_names, index=sheet_names.index(master_sheet) if master_sheet in sheet_names else 0)
    
    df_current = sheets_dict.get(selected_sheet, df_master).copy()

    with filter_col2:
        available_statuses = ["All"] + sorted([str(s) for s in df_current["Status"].dropna().unique()])
        selected_status = st.selectbox("Filter Status", available_statuses)

    with filter_col3:
        search_query = st.text_input("🔍 Search Company, Job Title, or Location", "")

    # Apply filters
    filtered_df = df_current.copy()
    if selected_status != "All":
        filtered_df = filtered_df[filtered_df["Status"].astype(str) == selected_status]

    if search_query.strip():
        q = search_query.strip().lower()
        search_mask = (
            filtered_df["Company"].astype(str).str.lower().str.contains(q, na=False) |
            filtered_df["Job Title"].astype(str).str.lower().str.contains(q, na=False) |
            (filtered_df["Location"].astype(str).str.lower().str.contains(q, na=False) if "Location" in filtered_df.columns else False)
        )
        filtered_df = filtered_df[search_mask]

    st.markdown(f"**Showing {len(filtered_df)} of {len(df_current)} entries**")

    # Column configuration for links
    column_config = {}
    if "Job URL" in filtered_df.columns:
        column_config["Job URL"] = st.column_config.LinkColumn("Job Posting", display_text="Open Link ↗")
    if "Date Applied" in filtered_df.columns:
        column_config["Date Applied"] = st.column_config.DateColumn("Date Applied", format="YYYY-MM-DD")

    st.dataframe(
        filtered_df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=480
    )

    # Export Buttons
    col_dl1, col_dl2 = st.columns([1, 4])
    with col_dl1:
        csv_data = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Filtered CSV",
            data=csv_data,
            file_name=f"job_applications_{selected_sheet.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True
        )

# =========================================================
# TAB 3: CANDIDATE PROFILE & QA
# =========================================================
with tab_profile:
    if profile:
        p_info = profile.get("personal_info", {})
        comp = profile.get("compensation", {})
        edu = profile.get("education", {})
        exp = profile.get("experience", {})
        qa = profile.get("screening_answers", {})

        p_col1, p_col2 = st.columns([1, 1])

        with p_col1:
            st.subheader("Personal & Education")
            st.markdown(f"- **Name:** {p_info.get('first_name', '')} {p_info.get('last_name', '')}")
            st.markdown(f"- **Email:** `{p_info.get('email', '')}`")
            st.markdown(f"- **Phone:** `{p_info.get('phone', '')}`")
            st.markdown(f"- **Location:** {p_info.get('location', '')}")
            st.markdown(f"- **Degree:** {edu.get('degree', '')} - {edu.get('university', '')} ({edu.get('graduation_year', '')})")
            st.markdown(f"- **GPA/Percentage:** {edu.get('gpa', 'N/A')}")

            st.subheader("Compensation & Availability")
            st.markdown(f"- **Expected Salary:** {comp.get('desired_lpa', 'Negotiable')}")
            st.markdown(f"- **Notice Period:** {comp.get('notice_period_weeks', 0)} weeks (Immediate Joiner)")
            st.markdown(f"- **Willing to Relocate:** {'Yes' if comp.get('willing_to_relocate') else 'No'}")

        with p_col2:
            st.subheader("Skills & Tech Stack")
            skills = exp.get("skills", [])
            if skills:
                st.write(" ".join([f"`{s}`" for s in skills]))
            
            st.subheader("Pre-Configured Screening Q&A")
            if qa:
                qa_df = pd.DataFrame([{"Question / Keyword": k, "Response": v} for k, v in qa.items()])
                st.dataframe(qa_df, use_container_width=True, hide_index=True)
            else:
                st.info("No custom screening answers defined.")
    else:
        st.warning("No `config/profile.yaml` found. Place your candidate profile configuration in `config/profile.yaml`.")

# =========================================================
# TAB 4: STREAMLIT CLOUD DEPLOYMENT GUIDE
# =========================================================
with tab_deploy:
    st.subheader("☁️ Deploying to Streamlit Community Cloud (Step-by-Step)")
    
    st.markdown("""
    You have a **Streamlit Account** and want to access this dashboard from any device or share it. 
    Follow these exact steps:

    ### 1️⃣ Step 1: Push Code to GitHub
    Streamlit Community Cloud (`share.streamlit.io`) links directly with your GitHub account.
    If you haven't pushed this repo to GitHub yet, run the following in your terminal:

    ```bash
    git init
    git add .
    git commit -m "feat: AutoJob AI Streamlit dashboard"
    git branch -M main
    git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>.git
    git push -u origin main
    ```

    ### 2️⃣ Step 2: Open Streamlit Cloud
    1. Go to [share.streamlit.io](https://share.streamlit.io).
    2. Sign in with your **GitHub account**.
    3. Click the blue **"Create app"** (or **"Deploy an app"**) button.

    ### 3️⃣ Step 3: Connect Your Repository
    Fill in the 3 deployment fields:
    - **Repository**: `<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>`
    - **Branch**: `main`
    - **Main file path**: `streamlit_app.py`
    - **App URL (optional)**: e.g. `shiva-autojob-dashboard.streamlit.app`

    ### 4️⃣ Step 4: Click 'Deploy!'
    Streamlit Cloud will automatically:
    - Clone your repository
    - Install all dependencies from `requirements.txt`
    - Launch your live web dashboard at your `.streamlit.app` URL!

    ---
    ### 🔒 Managing Secrets (Optional for Google Sheets)
    If you sync your job tracker to Google Sheets:
    1. In your Streamlit Cloud dashboard, go to **App Settings > Secrets**.
    2. Paste your Google Cloud service account credentials as TOML.
    3. Your app will automatically fetch live updates without committing private keys to GitHub!
    """)
