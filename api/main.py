import os
# DEV ONLY: allow http://localhost for OAuth during local development (remove in production)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

import re
import smtplib
import json
import random
import time
import base64
import email
import email.policy
from email.message import EmailMessage
from datetime import datetime, timedelta
from collections import defaultdict
import fitz  # PyMuPDF
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_groq import ChatGroq

# ==================== CONFIGURATION ====================
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

CLIENT_CONFIG = {
    "web": {
            "client_id": os.getenv("CLIENT_ID"),
            "project_id": os.getenv("PROJECT_ID"),
            "auth_uri": os.getenv("AUTH_URI"),
            "token_uri": os.getenv("TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_CERT_URL"),
            "client_secret": os.getenv("CLIENT_SECRET"),
            "redirect_uris": os.getenv("REDIRECT_URI")
    }
}
import smtplib



GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TEMPORARY_FOLDER = "temp_resumes"
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = os.getenv("SMTP_PORT")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


# Domain keywords for analysis
KEYWORDS = {
    'data_analytics': ['Python', 'SQL', 'Tableau', 'Presto', 'Redshift', 'PySpark', 'Data Analysis', 'ETL', 'Dashboard'],
    'data_quality': ['Data Governance', 'Data Profiling', 'Data Validation', 'DQ Tools', 'Quality Metrics', 'Data Cleansing'],
    'machine_learning': ['Python', 'TensorFlow', 'PyTorch', 'Data Science', 'AI', 'Machine Learning', 'NLP', 'Keras'],
    'business_intelligence': ['Power BI', 'Tableau', 'Qlik', 'Looker', 'Data Visualization', 'KPIs', 'Metrics'],
    'cloud': ['AWS', 'Azure', 'GCP', 'DevOps', 'CI/CD', 'Kubernetes', 'Docker', 'Terraform']
}
EXCLUDE_SENDERS = ['noreply', 'do-not-reply', 'system', 'newsletter', 'notification', 'alert', 'auto']
RESUME_KEYWORDS = ['resume', 'cv', 'profile', 'biodata', 'application', 'job', 'candidate', 'bio data', 'my details', 'applying', 'seeking', 'submission']
EXCLUDE_KEYWORDS = ['manual', 'form', 'insurance', 'doc', 'brochure', 'lab', 'syllabus', 'report']

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ==================== GMAIL & RESUME PROCESSING LOGIC ====================
def get_llm():
    """Initializes and returns the Groq LLM instance."""
    try:
        return ChatGroq(
            groq_api_key=GROQ_API_KEY,
            model_name="llama-3.1-8b-instant",
            temperature=0.18
        )
    except Exception as e:
        print(f"Failed to initialize LLM: {str(e)}")
        return None

def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True if successful."""
    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"Email sending error: {e}")
        return False

def get_acceptance_email(candidate_name: str, job_title: str):
    """Generates the subject and body for an acceptance email."""
    subject = f"Congratulations {candidate_name} - Application Accepted!"
    body = f"""Dear {candidate_name},
We are pleased to inform you that your application for the position of {job_title} has been shortlisted. 🎉
Our HR team was impressed with your skills and background. We will be contacting you shortly with the next steps in the hiring process.
Best regards,  
HR Team
"""
    return subject, body

def get_rejection_email(candidate_name: str, job_title: str):
    """Generates the subject and body for a rejection email."""
    subject = f"Application Update - {job_title}"
    body = f"""Dear {candidate_name},
Thank you for applying for the position of {job_title}. We truly appreciate the time and effort you put into the application process.
After careful consideration, we regret to inform you that your profile has not been shortlisted at this stage. However, we encourage you to apply for future opportunities with us.
Best wishes,  
HR Team
"""
    return subject, body

def parse_email_from_sender(sender: str) -> str:
    """Extracts just the email address from a sender string."""
    if not sender:
        return ""
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1).strip()
    match2 = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", sender)
    if match2:
        return match2.group(0).strip()
    return sender.strip()

def infer_job_title_from_jd(job_description: str) -> str:
    """Tries to guess job title from the job description."""
    if not job_description:
        return "Applicant"
    jd = job_description.strip()
    m = re.search(r"position\s+(?:of|for)\s+([A-Za-z0-9 &\-+]+)", jd, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip().splitlines()[0]
    m2 = re.search(r"looking for (an|a)?\s*([A-Za-z0-9 &\-+]+)", jd, flags=re.IGNORECASE)
    if m2:
        return m2.group(2).strip().splitlines()[0]
    first_line = jd.splitlines()[0]
    if len(first_line) < 80:
        return first_line[:80].strip()
    return "Applicant"

def get_timestamp_days_ago(days):
    """Calculates a timestamp from a number of days ago."""
    date_n_days_ago = datetime.utcnow() - timedelta(days=days)
    return int(date_n_days_ago.timestamp())

def is_resume_file(filename, subject):
    """Checks if a file and subject match resume criteria."""
    name = (filename or "").lower()
    subject = (subject or "").lower()
    is_subject_ok = any(kw in subject for kw in RESUME_KEYWORDS)
    is_filename_ok = any(kw in name for kw in RESUME_KEYWORDS)
    is_excluded = any(kw in name for kw in EXCLUDE_KEYWORDS)
    return (is_subject_ok or is_filename_ok) and not is_excluded

def is_valid_sender(sender):
    """Checks if a sender is valid (not a noreply address)."""
    sender_lower = sender.lower()
    return not any(exclude in sender_lower for exclude in EXCLUDE_SENDERS)

def download_resumes_from_gmail(creds, days_filter=30):
    """Downloads resumes from Gmail as PDF attachments."""
    try:
        gmail_service = build('gmail', 'v1', credentials=creds)
        timestamp = get_timestamp_days_ago(days_filter)
        query = f'has:attachment filename:pdf after:{timestamp}'
        results = gmail_service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        downloaded_files = []
        processed_senders = set()
        os.makedirs(TEMPORARY_FOLDER, exist_ok=True)
        
        for msg in messages[:20]:
            try:
                msg_data = gmail_service.users().messages().get(
                    userId='me', 
                    id=msg['id'], 
                    format='raw'
                ).execute()
                raw_msg = msg_data.get('raw')
                if not raw_msg:
                    continue
                if isinstance(raw_msg, str):
                    raw_msg = raw_msg.encode('ASCII')
                
                raw_msg = base64.urlsafe_b64decode(raw_msg)
                mime_msg = email.message_from_bytes(raw_msg, policy=email.policy.default)
                
                sender = mime_msg.get('From', '').lower()
                subject = mime_msg.get('Subject', '(No Subject)')

                if not is_valid_sender(sender) or sender in processed_senders:
                    continue
                processed_senders.add(sender)
                
                for part in mime_msg.walk():
                    filename = part.get_filename()
                    if filename and filename.lower().endswith('.pdf'):
                        if is_resume_file(filename, subject):
                            file_data = part.get_payload(decode=True)
                            sender_hash = hash(sender) % 10000
                            safe_filename = f"{sender_hash}_{filename}"
                            filepath = os.path.join(TEMPORARY_FOLDER, safe_filename)
                            if os.path.exists(filepath):
                                continue
                            with open(filepath, 'wb') as f:
                                f.write(file_data)
                            downloaded_files.append({
                                'filepath': filepath, 
                                'sender': sender, 
                                'subject': subject,
                                'original_filename': filename
                            })
                            
            except Exception as e:
                print(f"Skipping message due to error: {str(e)}")
                continue
        return downloaded_files
    except HttpError as e:
        print(f"Google API error: {str(e)}")
        return []
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return []

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file using PyMuPDF."""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {str(e)}")
        return ""

def clean_text(text):
    """Cleans up text by removing extra whitespace."""
    return re.sub(r'\s+', ' ', text).strip()

def keyword_match(text):
    """Matches keywords in text against predefined domains."""
    matches = defaultdict(list)
    lower_text = text.lower()
    for domain, words in KEYWORDS.items():
        for kw in words:
            if kw.lower() in lower_text:
                matches[domain].append(kw)
    return dict(matches)

def extract_candidate_name(filepath):
    """Tries to extract a candidate name from a filename."""
    filename = os.path.basename(filepath)
    if '_' in filename and filename.split('_')[0].isdigit():
        filename = '_'.join(filename.split('_')[1:])
    name_no_ext = os.path.splitext(filename)[0]
    name_no_ext = re.sub(r'[_\- ]?\d{1,3}$', '', name_no_ext)
    candidate_name = " ".join([w.capitalize() for w in re.split(r'[_\- ]+', name_no_ext) if w])
    return candidate_name

def extract_contact_info(text):
    """Extracts email and phone number from resume text."""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    email_val = emails[0] if emails else "Not found"
    phone_patterns = [
        r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',
        r'\b\(\d{3}\)\s*\d{3}[-.\s]?\d{4}\b',
        r'\b\d{10}\b',
        r'\b\+\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    ]
    phone = "Not found"
    for pattern in phone_patterns:
        phones = re.findall(pattern, text)
        if phones:
            phone = phones[0]
            break
    return email_val, phone

def generate_candidate_profile_hr(job_description, resume_text, matched_keywords, name, email, phone):
    """Generates an HR profile for a candidate using an LLM."""
    prompt = f"""
You are a senior HR analyst and technical recruiter. Your job is to analyze the resume evidence deeply and compare it with the job description, providing uniquely detailed, non-repetitive, and actionable HR insights. Use different evidence for each section and avoid repeating sentences or phrasing.
Inputs:
Job Description: {job_description}
Resume Text: {resume_text}
Matched Keywords: {json.dumps(matched_keywords, indent=2)}
Candidate Name: {name}
Candidate Email: {email}
Candidate Phone: {phone}

Output Format (use explicit section headers):
Basic Information:
- Name: {name}
- Email: {email}
- Phone: {phone}
- Total years of experience (estimate if not explicit)
- Highest education (if available)
- Most recent position and employer

Strengths & Weaknesses:
List 2-3 unique strengths and 2-3 unique weaknesses, each with distinct evidence from the resume (skills, projects, impact, achievements, missing skills, gaps, etc). Use this format:
- **Strength:** [evidence...]
- **Weakness:** [evidence...]

HR Summary & Justification:
Write a comprehensive, non-repetitive analysis (at least 3-5 lines, with specific, concrete resume evidence in each sentence), combining HR summary and justification. Start with a sub-heading **HR Summary:** and then a sub-heading **Justification:**, and then write the corresponding content for each. The HR Summary must be at least 4-6 lines, and should mention: domain expertise, technical proficiency, business acumen, teamwork, communication, project/role highlights, and unique strengths. Do not repeat phrases or evidence. The Justification must be at least 4-5 lines and reference project/role/skill evidence from the resume. Each major point must reference different evidence from the resume. Highlight both positive and negative aspects, and address business value, culture fit, and any observable upskilling or future potential.

Recommendation:
Provide a decisive recommendation in three clearly marked sections (each at least 2-3 sentences, all using different language/evidence than above):
- **Why Select This Candidate:** Reference at least two unique strengths from the resume.
- **Why Not Select This Candidate:** Reference at least two unique weaknesses or potential concerns from the resume.
- **Additional Future Potential:** Discuss what roles or upskilling would benefit this candidate and the company, referencing new evidence from the resume.

ATS Evaluation JSON:
A valid JSON array with 1 object in this format:
[
  {{
    "name": "{name}",
    "ats_score": [0-100],
    "hr_score": [1-10]
  }}
]

JD-Based Interview Questions & Resume Match Evaluation:
Generate 4-5 highly relevant, domain-specific interview questions based on the JD. For each, rate the resume's match: [Match level: Clear / Partial / Not Evident] — [Explanation, referencing a different project, skill, or achievement from the resume for each question.]

Your output must have these sections clearly separated, each detailed and actionable, with minimal repetition.
"""
    llm = get_llm()
    if not llm:
        return "LLM initialization failed"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = llm.invoke(prompt)
            return response.content
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait_time = (attempt + 1) * 5
                print(f"Rate limit reached. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            else:
                return f"Error generating profile: {str(e)}"
    return "Failed to generate profile after multiple attempts"

def parse_hr_response_sections(response_text):
    """Parses the LLM response text into structured sections."""
    sections = {
        'basic_info': '', 'strengths_weaknesses': '', 'hr_summary_justification': '',
        'recommendation': '', 'ats_json': '', 'interview_questions': ''
    }
    text = response_text.strip()
    markers = [
        ("basic_info", "basic information"), ("strengths_weaknesses", "strengths & weaknesses"),
        ("hr_summary_justification", "hr summary & justification"), ("recommendation", "recommendation"),
        ("ats_json", "ats evaluation json"), ("interview_questions", "jd-based interview questions")
    ]
    positions = []
    for key, marker in markers:
        idx = text.lower().find(marker)
        if idx != -1:
            positions.append((idx, key, marker))
    positions.sort()
    for i, (idx, key, marker) in enumerate(positions):
        start = idx + len(marker)
        end = positions[i+1][0] if i+1 < len(positions) else len(text)
        content = text[start:end].strip(" :\n*")
        sections[key] = content
    if sections["ats_json"]:
        json_match = re.search(r'\[[\s\S]*\]', sections["ats_json"])
        if json_match:
            sections["ats_json"] = json_match.group(0)
    return sections

def extract_subsections_hr_summary_justification(text):
    """Splits the summary/justification section into two parts."""
    summary, justification = "", ""
    parts = re.split(r"\*\*HR Summary:\*\*|\*\*Justification:\*\*|HR Summary:|Justification:", text, flags=re.IGNORECASE)
    if len(parts) == 3:
        _, summary, justification = parts
    elif len(parts) == 2:
        if "summary" in text.lower():
            _, summary = parts
        else:
            _, justification = parts
    else:
        summary = text
    return summary.strip(), justification.strip()

def style_recommendation_subheadings(recommendation):
    """Adds markdown formatting to the recommendation subheadings."""
    rec_out = recommendation
    rec_out = re.sub(r"(?<!\*)\s*Why Select This Candidate\s*:(?!\*)", "\n\n**Why Select This Candidate:**", rec_out, flags=re.IGNORECASE)
    rec_out = re.sub(r"(?<!\*)\s*Why Not Select This Candidate\s*:(?!\*)", "\n\n**Why Not Select This Candidate:**", rec_out, flags=re.IGNORECASE)
    rec_out = re.sub(r"(?<!\*)\s*Additional Future Potential\s*:(?!\*)", "\n\n**Additional Future Potential:**", rec_out, flags=re.IGNORECASE)
    return rec_out

# ==================== FLASK ROUTES ====================
@app.route("/")
def index():
    # Ensure you have an 'index.html' in templates folder; otherwise return a simple message
    try:
        return render_template("index.html")
    except Exception:
        return "<h3>Hai App - Visit /authenticate to connect Gmail</h3>"

@app.route("/authenticate")
def authenticate():
    """Start OAuth flow using web Flow"""
    flow = Flow.from_client_config(CLIENT_CONFIG, SCOPES)
    flow.redirect_uri = url_for("callback", _external=True)
    authorization_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    state = session.get('oauth_state')
    if not state or state != request.args.get('state'):
        return jsonify({"error": "Authentication state lost."}), 400

    flow = Flow.from_client_config(CLIENT_CONFIG, SCOPES, state=state)
    flow.redirect_uri = url_for("callback", _external=True)

    # Exchange code for tokens
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        return jsonify({"error": "Failed to fetch token", "details": str(e)}), 500

    creds = flow.credentials
    # Store JSON string in session
    session['creds'] = creds.to_json()
    return redirect(url_for('index'))

@app.route("/fetch_resumes", methods=["POST"])
def fetch_resumes():
    if 'creds' not in session:
        return jsonify({"error": "Authentication required"}), 401

    try:
        creds = Credentials.from_authorized_user_info(json.loads(session['creds']), SCOPES)
    except Exception as e:
        return jsonify({"error": "Invalid stored credentials", "details": str(e)}), 401

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                session['creds'] = creds.to_json()
            except Exception as e:
                return jsonify({"error": "Failed to refresh token", "details": str(e)}), 401
        else:
            return jsonify({"error": "Authentication token expired or invalid. Please re-authenticate."}), 401

    data = request.json or {}
    job_description = data.get("job_description", "")
    days_filter = int(data.get("days_filter", 30))

    downloaded_resumes = download_resumes_from_gmail(creds, days_filter)

    if not downloaded_resumes:
        return jsonify({"message": "No new resumes found."})

    candidates = []
    for i, meta in enumerate(downloaded_resumes):
        filepath = meta.get("filepath")
        if not filepath or not os.path.exists(filepath):
            continue

        raw_text = extract_text_from_pdf(filepath)
        if not raw_text:
            continue

        cleaned_text = clean_text(raw_text)
        matched_keywords = keyword_match(cleaned_text)
        candidate_name = extract_candidate_name(filepath)
        if not candidate_name:
            first_line = cleaned_text.splitlines()[0].strip() if cleaned_text else ""
            if first_line and len(first_line) < 60:
                candidate_name = first_line
            else:
                candidate_name = os.path.splitext(os.path.basename(filepath))[0]

        email_from_sender = parse_email_from_sender(meta.get("sender", ""))
        email_from_text, phone_from_text = extract_contact_info(cleaned_text)
        candidate_email = email_from_sender or email_from_text
        candidate_phone = phone_from_text

        profile = generate_candidate_profile_hr(
            job_description,
            cleaned_text,
            matched_keywords,
            candidate_name,
            candidate_email,
            candidate_phone,
        )

        if profile.startswith("Error") or profile.startswith("Failed") or profile == "LLM initialization failed":
            print(f"Failed to generate profile for {candidate_name}: {profile}")
            continue

        sections = parse_hr_response_sections(profile)
        summary, justification = extract_subsections_hr_summary_justification(sections.get("hr_summary_justification", ""))
        sections["hr_summary"] = summary
        sections["justification"] = justification
        sections["recommendation"] = style_recommendation_subheadings(sections.get("recommendation", ""))

        ats_score = None
        hr_score = None
        ats_json_text = sections.get("ats_json", "")
        if ats_json_text:
            try:
                ats_list = json.loads(ats_json_text)
                if ats_list and isinstance(ats_list[0], dict):
                    ats_score = ats_list[0].get("ats_score")
                    hr_score = ats_list[0].get("hr_score")
            except Exception as e:
                print(f"Could not parse ATS JSON for {candidate_name}: {e}")

        sections["ats_score"] = ats_score
        sections["hr_score"] = hr_score

        candidates.append({
            "name": candidate_name,
            "email": candidate_email,
            "phone": candidate_phone,
            "filename": meta.get("original_filename", ""),
            "sender": meta.get("sender", ""),
            "subject": meta.get("subject", ""),
            "sections": sections
        })

    return jsonify({"candidates": candidates})

@app.route("/send_email", methods=["POST"])
def send_email_route():
    data = request.json or {}
    candidate_email = data.get("email")
    candidate_name = data.get("name")
    job_description = data.get("job_description")
    email_type = data.get("type")

    if not candidate_email or not candidate_name or not job_description or not email_type:
        return jsonify({"success": False, "message": "Missing required data."}), 400

    job_title = infer_job_title_from_jd(job_description)

    if email_type == "accept":
        subject, body = get_acceptance_email(candidate_name, job_title)
    elif email_type == "reject":
        subject, body = get_rejection_email(candidate_name, job_title)
    else:
        return jsonify({"success": False, "message": "Invalid email type."}), 400

    if send_email(candidate_email, subject, body):
        return jsonify({"success": True, "message": f"{email_type.capitalize()} email sent successfully!"})
    else:
        return jsonify({"success": False, "message": "Failed to send email."})

if __name__ == "__main__":
    # Debug mode useful while developing; keep HTTPS/ngrok+secure production later.
    app.run(debug=True)
