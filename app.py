"""
NexaBank — Intelligent Onboarding Backend (v2)
Real Flask + Real SQLite + Real File Storage + Claude AI Chat
+ User Authentication + Chat History + Admin Approvals
"""

import os, json, uuid, hashlib, random, time, re
from datetime import datetime
from functools import wraps
from flask import (Flask, request, jsonify, session, render_template,
                   send_from_directory, redirect, url_for)
from werkzeug.utils import secure_filename
import sqlite3
from google import genai
from deepface import DeepFace
from dotenv import load_dotenv
load_dotenv()

import pytesseract
from PIL import Image

OCR_AVAILABLE = True


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# try:
#     from PIL import Image
#     import pytesseract
#     OCR_AVAILABLE = True
# except ImportError:
#     OCR_AVAILABLE = False

# ─── CONFIG ──────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, 'instance', 'nexabank.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
DOC_DIR    = os.path.join(UPLOAD_DIR, 'documents')
SELFIE_DIR = os.path.join(UPLOAD_DIR, 'selfies')

for d in [os.path.join(BASE_DIR, 'instance'), DOC_DIR, SELFIE_DIR]:
    os.makedirs(d, exist_ok=True)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'nexabank-secret-2025-v2'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # True only if using HTTPS
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_DOC    = {'png', 'jpg', 'jpeg', 'pdf'}
ALLOWED_SELFIE = {'png', 'jpg', 'jpeg', 'webp'}

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)
# client = None
# if GEMINI_API_KEY:
#     client = genai.Client(api_key=GEMINI_API_KEY)

OCR_API_KEY=os.getenv('OCR_API_KEY')

import requests
def run_external_ocr(file_path):
    url = "https://api.ocr.space/parse/image"

    with open(file_path, 'rb') as f:
        response = requests.post(url, files={
            'file': f
        }, data={
            'apikey': OCR_API_KEY,
            'language': 'eng'
        })

    result = response.json()

    try:
        text = result['ParsedResults'][0]['ParsedText']
    except:
        text = ""

    return text

# ─── DATABASE ────────────────────────────────────────────────────────────────
# def db_connect():
#     conn = sqlite3.connect(DB_PATH, timeout=10)
#     conn.row_factory = sqlite3.Row
#     conn.execute("PRAGMA journal_mode=WAL")
#     conn.execute("PRAGMA busy_timeout=3000")
#     return conn
def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db():
    con = db_connect()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name     TEXT,
        role          TEXT DEFAULT 'reviewer',
        created_at    TEXT
    );

    CREATE TABLE IF NOT EXISTS user_accounts (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       TEXT UNIQUE NOT NULL,
        name          TEXT NOT NULL,
        email         TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at    TEXT,
        last_login    TEXT
    );

    CREATE TABLE IF NOT EXISTS applications (
        id              TEXT PRIMARY KEY,
        user_id         TEXT,
        name            TEXT,
        dob             TEXT,
        email           TEXT,
        phone           TEXT,
        id_type         TEXT,
        id_number       TEXT,
        address         TEXT,
        method          TEXT DEFAULT 'Manual',
        selfie_path     TEXT,
        doc_path        TEXT,
        ocr_raw         TEXT,
        face_score      INTEGER,
        face_status     TEXT DEFAULT 'Pending',
        risk_score      INTEGER,
        risk_level      TEXT,
        risk_signals    TEXT,
        risk_reason     TEXT,
        otp_hash        TEXT,
        otp_verified    INTEGER DEFAULT 0,
        account_number  TEXT,
        ifsc            TEXT,
        branch          TEXT DEFAULT 'NexaBank Digital Branch',
        account_type    TEXT DEFAULT 'Savings',
        status          TEXT DEFAULT 'In Progress',
        created_at      TEXT,
        updated_at      TEXT
    );

    CREATE TABLE IF NOT EXISTS documents (
        id              TEXT PRIMARY KEY,
        application_id  TEXT NOT NULL,
        doc_type        TEXT,
        original_name   TEXT,
        stored_name     TEXT,
        file_hash       TEXT,
        file_size       INTEGER,
        ocr_text        TEXT,
        ocr_name        TEXT,
        ocr_dob         TEXT,
        ocr_id_number   TEXT,
        tamper_flags    TEXT,
        confidence      INTEGER,
        verified        INTEGER DEFAULT 0,
        uploaded_at     TEXT,
        FOREIGN KEY(application_id) REFERENCES applications(id)
    );

    CREATE TABLE IF NOT EXISTS chat_messages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  TEXT,
        user_id         TEXT,
        role            TEXT,
        content         TEXT,
        timestamp       TEXT
    );

    CREATE TABLE IF NOT EXISTS behavior_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id TEXT,
        step TEXT,
        response_time INTEGER,
        created_at TEXT,
        FOREIGN KEY(application_id) REFERENCES applications(id)
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  TEXT,
        action          TEXT NOT NULL,
        actor           TEXT DEFAULT 'SYSTEM',
        detail          TEXT,
        ip              TEXT,
        timestamp       TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS admin_decisions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  TEXT NOT NULL,
        admin_username  TEXT,
        decision        TEXT,
        notes           TEXT,
        ai_overridden   INTEGER DEFAULT 0,
        decided_at      TEXT
    );
    """)

    # Seed admin users
    pw_hash = hashlib.sha256('admin123'.encode()).hexdigest()
    con.execute("""
        INSERT OR IGNORE INTO admin_users (username, password_hash, full_name, role, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, ('admin', pw_hash, 'System Administrator', 'superadmin', now()))

    pw2 = hashlib.sha256('reviewer123'.encode()).hexdigest()
    con.execute("""
        INSERT OR IGNORE INTO admin_users (username, password_hash, full_name, role, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, ('reviewer', pw2, 'KYC Reviewer', 'reviewer', now()))

    seed_applications(con)
    con.commit()
    con.close()

def seed_applications(con):
    count = con.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    if count > 0:
        return
    demos = [
        ('NXB-DEMO-001', 'Rohan Mehta', '1992-04-15', 'rohan.mehta@gmail.com',
         '+91-9876543210', 'Aadhaar', 'XXXX-XXXX-7842', 'Manual', 82, 'Low',
         'Approved', '7742 8910 3351', 'NXBA0001234'),
        ('NXB-DEMO-002', 'Priya Sharma', '1988-11-22', 'priya.sharma@gmail.com',
         '+91-9812345678', 'PAN', 'ABCDE1234F', 'Manual', 54, 'Medium',
         'Pending', None, None),
        ('NXB-DEMO-003', 'Anjali Gupta', '2001-07-08', 'anjali.g@gmail.com',
         '+91-9900112233', 'Passport', 'P1234567', 'Manual', 18, 'High',
         'Escalated', None, None),
        ('NXB-DEMO-004', 'Vikram Singh', '1995-03-30', 'vikram.s@gmail.com',
         '+91-9988776655', 'Aadhaar', 'XXXX-XXXX-3391', 'Manual', 91, 'Low',
         'Approved', '6612 4430 9981', 'NXBA0001234'),
        ('NXB-DEMO-005', 'Kavitha Nair', '1990-09-12', 'kavitha.n@gmail.com',
         '+91-9871234560', 'PAN', 'FGHIJ5678K', 'Manual', 48, 'Medium',
         'Pending', None, None),
    ]
    reasons = {
        'Low':    'All checks passed. Document integrity verified. Biometric match strong. No AML flags.',
        'Medium': 'Minor OCR discrepancy detected. Manual secondary verification recommended.',
        'High':   'Multiple face-match attempts failed. Potential document tampering. AML flag raised.',
    }
    for d in demos:
        ts = now()
        con.execute("""
            INSERT INTO applications
            (id,name,dob,email,phone,id_type,id_number,method,risk_score,risk_level,
             status,account_number,ifsc,risk_reason,face_score,otp_verified,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
        """, (*d, reasons[d[9]], random.randint(80, 99), ts, ts))
        log(con, d[0], 'APPLICATION_SEEDED', f'Demo data: {d[1]}')

def now():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

def to_dict(row):
    return dict(row) if row else None

def log(con, app_id, action, detail='', actor='SYSTEM'):
    con.execute(
        "INSERT INTO audit_log(application_id,action,actor,detail,ip,timestamp) VALUES(?,?,?,?,?,?)",
        (app_id, action, actor, detail,
         request.remote_addr if request else '127.0.0.1', now())
    )

# ─── AUTH HELPERS ─────────────────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Unauthorized. Please login.'}), 401
        return f(*args, **kwargs)
    return decorated

def user_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_logged_in') and not session.get('demo_user'):
            return jsonify({'error': 'Please login to continue.'}), 401
        return f(*args, **kwargs)
    return decorated

#================== Helper Functions ========================================
import re

def clean_name(msg):
    msg = msg.strip()

    # Remove common phrases
    patterns = [
        r"my name is",
        r"i am",
        r"i'm",
        r"this is",
        r"hello,? my name is",
    ]

    msg_lower = msg.lower()

    for p in patterns:
        if p in msg_lower:
            msg = re.sub(p, "", msg, flags=re.IGNORECASE)

    # Remove extra symbols/numbers
    msg = re.sub(r"[^a-zA-Z\s]", "", msg)

    # Remove extra spaces
    msg = " ".join(msg.split())

    return msg.title()

# ─── OCR ENGINE ──────────────────────────────────────────────────────────────

def run_ocr(file_path, doc_type):
    result = {
        'raw_text': '', 'name': None, 'dob': None, 'id_number': None,
        'confidence': 0, 'tamper_flags': []
    }

    text = ""

    # ─── TRY EXTERNAL OCR FIRST ─────────────────────────
    try:
        text = run_external_ocr(file_path)

        if text and len(text.strip()) > 20:
            result['confidence'] = 85
        else:
            raise Exception("Weak OCR result")

    except Exception as e:
        # ─── FALLBACK TO LOCAL OCR ───────────────────────
        try:
            img = Image.open(file_path).convert('L')
            text = pytesseract.image_to_string(img, config='--psm 6')
            result['confidence'] = 60
            result['tamper_flags'].append('Used fallback OCR (external failed)')
        except Exception as e2:
            result['tamper_flags'].append(f'OCR failed: {str(e2)}')
            return result

    result['raw_text'] = text

    # ─── YOUR EXISTING EXTRACTION LOGIC ─────────────────
    for line in text.splitlines():
        line = line.strip()
        if len(line.split()) >= 2 and re.match(r'^[A-Za-z ]{4,40}$', line):
            result['name'] = line.title()
            break

    dob_match = re.search(r'\b(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{4})\b', text)
    if dob_match:
        result['dob'] = dob_match.group(1)

    if doc_type == 'Aadhaar':
        m = re.search(r'\b(\d{4}\s?\d{4}\s?\d{4})\b', text)
        if m: result['id_number'] = m.group(1)

    elif doc_type == 'PAN':
        m = re.search(r'\b([A-Z]{5}\d{4}[A-Z])\b', text)
        if m: result['id_number'] = m.group(1)

    elif doc_type == 'Passport':
        m = re.search(r'\b([A-Z]\d{7})\b', text)
        if m: result['id_number'] = m.group(1)

    # ─── SIMPLE TAMPER CHECK ────────────────────────────
    word_count = len(text.split())

    if word_count < 5:
        result['tamper_flags'].append('Very low text content')
    if word_count > 200:
        result['tamper_flags'].append('Unusual text density')

    return result

# ─── RISK ENGINE ──────────────────────────────────────────────────────────────
def compute_risk(app_row, doc_rows, behavior_rows):
    score   = 100
    signals = []

    if doc_rows:
        confidences = [d['confidence'] or 50 for d in doc_rows]
        avg_conf = sum(confidences) / len(confidences)
        if avg_conf >= 75:
            signals.append({'factor': 'OCR Confidence', 'weight': 0, 'note': f'{avg_conf:.0f}% — high quality document image'})
        elif avg_conf >= 50:
            score -= 10
            signals.append({'factor': 'OCR Confidence', 'weight': -10, 'note': f'{avg_conf:.0f}% — moderate quality'})
        else:
            score -= 25
            signals.append({'factor': 'OCR Confidence', 'weight': -25, 'note': f'{avg_conf:.0f}% — low quality or illegible'})

        all_flags = []
        for d in doc_rows:
            flags = json.loads(d['tamper_flags'] or '[]')
            all_flags.extend(flags)
        if all_flags:
            score -= 20 * len(all_flags)
            signals.append({'factor': 'Tamper Detection', 'weight': -20 * len(all_flags), 'note': '; '.join(all_flags)})
        else:
            signals.append({'factor': 'Tamper Detection', 'weight': 0, 'note': 'No anomalies detected'})

    try:
        dob = datetime.strptime(app_row['dob'], '%Y-%m-%d')
        age = (datetime.now() - dob).days // 365
        if age < 18:
            score -= 100
            signals.append({'factor': 'Age Gate', 'weight': -100, 'note': f'Applicant is {age} — below 18'})
        elif 18 <= age <= 65:
            signals.append({'factor': 'Age Gate', 'weight': 0, 'note': f'Age {age} — valid range'})
        else:
            score -= 5
            signals.append({'factor': 'Age Gate', 'weight': -5, 'note': f'Age {age} — senior applicant'})
    except:
        score -= 10
        signals.append({'factor': 'Age Gate', 'weight': -10, 'note': 'DOB parse error'})

    face = app_row['face_score'] or 0
    if face >= 90:
        signals.append({'factor': 'Biometric Match', 'weight': 0, 'note': f'{face}% — strong match'})
    elif face >= 75:
        score -= 10
        signals.append({'factor': 'Biometric Match', 'weight': -10, 'note': f'{face}% — acceptable'})
    elif face > 0:
        score -= 30
        signals.append({'factor': 'Biometric Match', 'weight': -30, 'note': f'{face}% — poor match'})
    else:
        score -= 15
        signals.append({'factor': 'Biometric Match', 'weight': -15, 'note': 'No biometric data'})

    if app_row['otp_verified']:
        signals.append({'factor': 'OTP Verification', 'weight': 0, 'note': 'Mobile/email OTP verified'})
    else:
        score -= 20
        signals.append({'factor': 'OTP Verification', 'weight': -20, 'note': 'OTP not verified'})

    email = app_row['email'] or ''
    disposable = ['tempmail', 'guerrillamail', 'mailinator', 'yopmail', 'throwam']
    if any(d in email for d in disposable):
        score -= 20
        signals.append({'factor': 'Email Trust', 'weight': -20, 'note': 'Disposable email detected'})
    elif email:
        signals.append({'factor': 'Email Trust', 'weight': 0, 'note': 'Email domain OK'})

    score = max(0, min(100, score))
    level = 'Low' if score >= 70 else 'Medium' if score >= 45 else 'High'

    neg_notes = [s['note'] for s in signals if s['weight'] < 0]
    pos_notes = [s['note'] for s in signals if s['weight'] == 0]


    # ─── BEHAVIOR ANALYSIS ─────────────────────────────
    if behavior_rows:
        delays = [b['response_time'] for b in behavior_rows if b['response_time']]

        if delays:
            avg_delay = sum(delays) / len(delays)

            if avg_delay > 15000:  # >15 sec avg
                score -= 10
                signals.append({
                    'factor': 'Behavior Pattern',
                    'weight': -10,
                    'note': f'High hesitation detected (avg {int(avg_delay/1000)}s per step)'
                })

            elif avg_delay < 800:  # <0.8 sec → bot-like
                score -= 15
                signals.append({
                    'factor': 'Behavior Pattern',
                    'weight': -15,
                    'note': 'Unnaturally fast responses (possible automation)'
                })

            else:
                signals.append({
                    'factor': 'Behavior Pattern',
                    'weight': 0,
                    'note': f'Normal interaction pattern ({int(avg_delay/1000)}s avg)'
                })

    neg = [f"{s['factor']}: {s['note']}" for s in signals if s['weight'] < 0]
    pos = [f"{s['factor']}: {s['note']}" for s in signals if s['weight'] == 0]

    if level == 'Low':
        reason = "All checks passed. " + "; ".join(pos[:3])
    elif level == 'Medium':
        reason = "Some risk signals detected: " + "; ".join(neg)
    else:
        reason = "High risk due to: " + "; ".join(neg)

    # if level == 'Low':
    #     reason = "All checks passed.\n" + "\n".join([f"✔ {n}" for n in pos_notes[:3]])
    # elif level == 'Medium':
    #     reason = "Moderate risk detected:\n" + "\n".join([f"⚠ {n}" for n in neg_notes])
    # else:
    #     reason = "High risk detected:\n" + "\n".join([f"❌ {n}" for n in neg_notes])

    # Comment out the below part later when fraud tag is defined

    # fraud_tag = None

    # if any('tamper' in s['factor'].lower() for s in signals):
    #     fraud_tag = 'Document Tampering Suspected'

    # elif any('Behavior' in s['factor'] and s['weight'] < 0 for s in signals):
    #     fraud_tag = 'Suspicious User Behavior'

    # elif any('Email Trust' in s['factor'] and s['weight'] < 0 for s in signals):
    #     fraud_tag = 'Synthetic Identity Risk'

    return score, level, signals, reason #,fraud_tag

# ─── CLAUDE AI CHAT (Conversational) ─────────────────────────────────────────
def ask_claude_conversational(messages, app_state):
    """
    Call Gemini API with full context about the onboarding state.
    Returns an intelligent, conversational response that can also
    answer general questions while guiding the KYC process.
    """
    if not GEMINI_API_KEY:
        return None

    # Build a rich system prompt that tells current state
    system = f"""You are ARIA, NexaBank's intelligent AI onboarding assistant. You are warm, professional, and genuinely helpful — like a knowledgeable bank relationship manager combined with a problem-solver.

## Current Application State:
- Application ID: {app_state.get('app_id', 'Not started')}
- Name collected: {app_state.get('name', 'Not yet')}
- DOB collected: {app_state.get('dob', 'Not yet')}
- Email collected: {app_state.get('email', 'Not yet')}
- Phone collected: {app_state.get('phone', 'Not yet')}
- Current step: {app_state.get('current_step', 'name')}
- Document uploaded: {app_state.get('doc_uploaded', False)}
- Selfie done: {app_state.get('selfie_done', False)}
- OTP verified: {app_state.get('otp_verified', False)}

## Your Personality:
- You are conversational and natural — NOT a rigid form-filler
- You can answer ANY banking or general question the user asks
- You give helpful advice and explanations when asked
- You gently guide back to the KYC flow after answering questions
- You remember context from earlier in the conversation
- If the user seems confused or frustrated, acknowledge it empathetically
- If the user gives you their name but asks a question first, answer the question THEN ask for what you need

## KYC Steps you need to complete IN ORDER:
1. Collect full name
2. Collect date of birth (YYYY-MM-DD format)
3. Collect email address
4. Collect mobile number
5. Request document upload (Aadhaar / PAN / Passport)
6. Request selfie photo
7. OTP verification
8. Risk assessment → account creation

## Important Rules:
- Never ask for full Aadhaar number
- Never ask for bank account numbers or passwords
- Be concise (2-4 sentences max)
- Adapt to user style
- Skip already completed steps
"""

    try:
        # Convert messages into text (same idea as before)
        convo = ""
        for m in messages:
            role = "User" if m["role"] == "user" else "Assistant"
            convo += f"{role}: {m['content']}\n"

        full_prompt = system + "\n\nConversation:\n" + convo + "\nAssistant:"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt
        )

        return response.text

    except Exception as e:
        print(f'Gemini API error: {e}')
        return None

def rule_based_response(step, msg, app_row):
    """Intelligent fallback when no Claude API key."""
    msg_lower = msg.lower()

    # Handle common questions regardless of step
    if any(w in msg_lower for w in ['document', 'which id', 'what id', 'id proof', 'kyc']):
        return ("For NexaBank KYC, you can use any one of: **Aadhaar Card**, **PAN Card**, or **Passport**. "
                "Make sure the document is clear, valid, and matches your personal details. "
                f"{'Now, ' + step_prompt(step) if step else ''}")

    if any(w in msg_lower for w in ['interest', 'rate', 'savings rate', '%']):
        return ("NexaBank Savings accounts offer **3.5% p.a.** on balances up to ₹1 lakh and **4% p.a.** above ₹1 lakh, "
                f"credited quarterly. {step_prompt(step)}")

    if any(w in msg_lower for w in ['eligible', 'eligibility', 'can i', 'who can']):
        return ("Any **Indian resident aged 18+** with a valid KYC document can open a NexaBank savings account. "
                f"NRIs require additional documentation. {step_prompt(step)}")

    if any(w in msg_lower for w in ['safe', 'security', 'secure', 'private', 'data']):
        return ("Your data is protected by **AES-256 encryption** and stored on RBI-compliant servers in India. "
                "We never share your information with third parties without consent. "
                f"{step_prompt(step)}")

    if any(w in msg_lower for w in ['hello', 'hi ', 'hey', 'namaste', 'hii']):
        return f"Hello! Great to have you here. {step_prompt(step)}"

    # Step-specific responses
    step_responses = {
        'name':   "Thank you! Could you please share your **full name** as it appears on your government-issued ID?",
        'dob':    f"Got it! Now I need your **date of birth** in YYYY-MM-DD format (e.g., 1995-06-20).",
        'email':  "Perfect. What's your **email address**? We'll send you important updates and your OTP there.",
        'phone':  "And your **mobile number** with country code? (e.g., +91-9876543210)",
        'doc':    "Now please **upload your ID document** — Aadhaar, PAN, or Passport using the button below.",
        'selfie': "Document looks good! Now I need a **selfie photo** for biometric verification.",
        'otp':    "Almost there! Please enter the **6-digit OTP** sent to your email/mobile.",
        'done':   "Processing your application. Please wait a moment!",
    }
    return step_responses.get(step or 'name', "I'm here to help! Please share your full name to get started.")

def step_prompt(step):
    prompts = {
        'name':   "To get started, what's your **full name** as on your ID?",
        'dob':    "What's your **date of birth**? (YYYY-MM-DD format)",
        'email':  "What's your **email address**?",
        'phone':  "And your **mobile number** with country code?",
        'doc':    "Ready to upload your **ID document**?",
        'selfie': "Ready for your **selfie verification**?",
        'otp':    "Please enter the **OTP** you received.",
    }
    return prompts.get(step, '')

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — PAGES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    # If not logged in, redirect to login
    if not session.get('user_logged_in') and not session.get('demo_user'):
        return redirect('/login')
    return render_template('index.html')

@app.route('/login')
def login_page():
    if session.get('user_logged_in') or session.get('demo_user'):
        return redirect('/')
    return render_template('user_login.html')

@app.route('/admin-login')
def admin_login_page():
    if session.get('admin_logged_in'):
        return redirect('/admin')
    return render_template('admin_login.html')

@app.route('/admin')
def admin_page():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    return render_template('admin.html')

@app.route('/uploads/selfies/<filename>')
def serve_selfie(filename):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    return send_from_directory(SELFIE_DIR, filename)

@app.route('/uploads/documents/<filename>')
def serve_doc(filename):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    return send_from_directory(DOC_DIR, filename)

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — USER AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/user/register', methods=['POST'])
def user_register():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not name or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    if not re.match(r'^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({'error': 'Invalid email address'}), 400

    user_id = 'USR-' + uuid.uuid4().hex[:8].upper()
    ts = now()

    con = db_connect()
    try:
        con.execute("""
            INSERT INTO user_accounts (user_id, name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, name, email, hash_pw(password), ts))
        con.commit()
    except sqlite3.IntegrityError:
        con.close()
        return jsonify({'error': 'An account with this email already exists. Please sign in.'}), 409
    finally:
        con.close()

    session['user_logged_in'] = True
    session['user_id'] = user_id
    session['user_name'] = name
    session['user_email'] = email

    return jsonify({'success': True, 'name': name, 'user_id': user_id})

@app.route('/api/user/login', methods=['POST'])
def user_login():
    data = request.get_json()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    con = db_connect()
    user = con.execute(
        "SELECT * FROM user_accounts WHERE email=? AND password_hash=?",
        (email, hash_pw(password))
    ).fetchone()

    if not user:
        con.close()
        return jsonify({'error': 'Invalid email or password'}), 401

    # Update last login
    con.execute("UPDATE user_accounts SET last_login=? WHERE user_id=?", (now(), user['user_id']))
    con.commit()
    con.close()

    session['user_logged_in'] = True
    session['user_id'] = user['user_id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']

    return jsonify({'success': True, 'name': user['name'], 'user_id': user['user_id']})

@app.route('/api/user/demo-login', methods=['POST'])
def demo_login():
    """Allow guest/demo access without registration."""
    session['demo_user'] = True
    session['user_id'] = 'DEMO-' + uuid.uuid4().hex[:6].upper()
    session['user_name'] = 'Guest User'
    session['user_email'] = 'demo@nexabank.in'
    return jsonify({'success': True, 'name': 'Guest User', 'demo': True})

@app.route('/api/user/logout', methods=['POST'])
def user_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/user/me', methods=['GET'])
def user_me():
    if session.get('user_logged_in') or session.get('demo_user'):
        return jsonify({
            'logged_in': True,
            'user_id': session.get('user_id'),
            'name': session.get('user_name'),
            'email': session.get('user_email'),
            'demo': session.get('demo_user', False)
        })
    return jsonify({'logged_in': False}), 200

@app.route('/api/user/applications', methods=['GET'])
def user_applications():
    """Get all applications for the logged-in user."""
    if not session.get('user_logged_in') and not session.get('demo_user'):
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    con = db_connect()
    apps = con.execute(
        "SELECT id, name, status, risk_level, risk_score, account_number, ifsc, created_at, updated_at FROM applications WHERE user_id=? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    con.close()
    return jsonify({'applications': [to_dict(a) for a in apps]})

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — ADMIN AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    con = db_connect()
    user = con.execute(
        "SELECT * FROM admin_users WHERE username=? AND password_hash=?",
        (username, hash_pw(password))
    ).fetchone()
    con.close()

    if not user:
        return jsonify({'error': 'Invalid username or password'}), 401

    session['admin_logged_in'] = True
    session['admin_username']  = user['username']
    session['admin_name']      = user['full_name']
    session['admin_role']      = user['role']

    return jsonify({
        'success': True,
        'username': user['username'],
        'full_name': user['full_name'],
        'role': user['role']
    })

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    for k in ['admin_logged_in', 'admin_username', 'admin_name', 'admin_role']:
        session.pop(k, None)
    return jsonify({'success': True})

@app.route('/api/admin/me', methods=['GET'])
@admin_required
def admin_me():
    return jsonify({
        'username': session.get('admin_username'),
        'full_name': session.get('admin_name'),
        'role': session.get('admin_role')
    })

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — ONBOARDING SESSION
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/session/start', methods=['POST'])
def session_start():
    user_id = session.get('user_id', 'GUEST')
    app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
    ts = now()
    con = db_connect()
    con.execute(
        "INSERT INTO applications(id, user_id, status, method, created_at, updated_at) VALUES(?,?,?,?,?,?)",
        (app_id, user_id, 'In Progress', 'Manual', ts, ts)
    )
    welcome_msg = (
        f"Welcome to NexaBank! I'm **ARIA**, your AI banking assistant. "
        "I'm here to help you open your account — but I can also answer any banking questions you have along the way. "
        "What's your **full name** as it appears on your ID?"
    )
    con.execute(
        "INSERT INTO chat_messages(application_id, user_id, role, content, timestamp) VALUES(?,?,?,?,?)",
        (app_id, user_id, 'assistant', welcome_msg, ts)
    )
    log(con, app_id, 'SESSION_STARTED', f'New application by user {user_id}')
    con.commit()
    con.close()

    session['app_id'] = app_id
    return jsonify({'application_id': app_id, 'created_at': ts})

@app.route('/api/session/resume', methods=['POST'])
def session_resume():
    """Re-attach an existing application to the current session."""
    data   = request.get_json() or {}
    app_id = data.get('application_id')
    user_id = session.get('user_id', 'GUEST')

    if not app_id:
        return jsonify({'error': 'Missing application_id'}), 400

    con     = db_connect()
    app_row = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    con.close()

    if not app_row:
        return jsonify({'error': 'Application not found'}), 404

    # Restore session
    session['app_id'] = app_id
    return jsonify({'success': True, 'application_id': app_id, 'status': app_row['status']})

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — AI CHAT (Conversational with full history)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/chat/message', methods=['POST'])
def chat_message():
    data   = request.get_json()
    app_id = session.get('app_id') or data.get('application_id')
    msg    = (data.get('message') or '').strip()
    step   = data.get('step', 'name')

    # if step == 'name':
    #     cleaned_name = clean_name(msg)

    if not app_id or not msg:
        return jsonify({'error': 'Missing app_id or message'}), 400

    ts  = now()
    con = db_connect()

    con.execute(
        "INSERT INTO chat_messages(application_id,role,content,timestamp) VALUES(?,?,?,?)",
        (app_id, 'user', msg, ts)
    )

    app_row = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    app_dict = dict(app_row) if app_row else {}

    ai_reply = None

    if GEMINI_API_KEY:
        history = con.execute(
            "SELECT role, content FROM chat_messages WHERE application_id=? ORDER BY id",
            (app_id,)
        ).fetchall()

        system = f"""You are ARIA, NexaBank's friendly AI onboarding assistant.

Current onboarding step: {step}
Collected so far:
- Name: {app_dict.get('name') or 'not yet'}
- DOB: {app_dict.get('dob') or 'not yet'}
- Email: {app_dict.get('email') or 'not yet'}
- Phone: {app_dict.get('phone') or 'not yet'}
- Document: {app_dict.get('id_type') or 'not uploaded'}

Your job:
1. If the user is answering the current step (giving name/dob/email/phone), acknowledge it warmly and ask for the next piece of info.
2. If the user asks a question (eligibility, documents needed, interest rates, security, fees, how long it takes, etc.), answer it helpfully in 2-3 sentences, then gently guide back to the current step.
3. If the user says something unclear, ask for clarification, then re-prompt for the current step.

Steps in order: name → dob (YYYY-MM-DD) → email → phone → document upload → selfie → OTP → done.
Skip already-collected steps. Never ask for full Aadhaar number or passwords.
Keep responses under 3 sentences. Be warm, not robotic."""

        try:
            claude_msgs = [{'role': r['role'], 'content': r['content']} for r in history]
            ai_reply = ask_claude_conversational(claude_msgs, {
                'app_id': app_id,
                'name': app_dict.get('name'),
                'dob': app_dict.get('dob'),
                'email': app_dict.get('email'),
                'phone': app_dict.get('phone'),
                'current_step': step,
                'doc_uploaded': bool(app_dict.get('id_type')),
                'selfie_done': False,
                'otp_verified': False
            })
        except Exception as e:
            print(f'Claude error: {e}')
            ai_reply = None

    if not ai_reply:
        ai_reply = rule_based_response(step, msg)

    con.execute(
        "INSERT INTO chat_messages(application_id,role,content,timestamp) VALUES(?,?,?,?)",
        (app_id, 'assistant', ai_reply, now())
    )
    log(con, app_id, 'CHAT_MESSAGE', f'Step:{step} | Msg:{msg[:60]}')
    con.commit()
    con.close()

    return jsonify({'reply': ai_reply, 'application_id': app_id})


def rule_based_response(step, msg):
    """Smart fallback — detects questions vs step answers."""
    m = msg.lower()

    # Question detection
    is_question = any(w in m for w in [
        'what', 'how', 'which', 'who', 'when', 'why', 'can i',
        'eligible', 'document', 'safe', 'secure', 'interest', 'rate',
        'fee', 'charge', 'free', 'long', 'time', 'kyc', '?'
    ])

    if is_question:
        if any(w in m for w in ['document', 'which id', 'id proof', 'kyc', 'what do i need']):
            answer = "You can use any one of: **Aadhaar Card**, **PAN Card**, or **Passport** for KYC."
        elif any(w in m for w in ['interest', 'rate', 'return']):
            answer = "NexaBank offers **3.5%–4% p.a.** on savings accounts, credited quarterly."
        elif any(w in m for w in ['eligible', 'who can', 'can i open', 'qualify']):
            answer = "Any **Indian resident aged 18+** with a valid government ID can open an account."
        elif any(w in m for w in ['safe', 'secure', 'privacy', 'data', 'trust']):
            answer = "Your data is encrypted with **AES-256** and stored on RBI-compliant servers. We never share it without consent."
        elif any(w in m for w in ['fee', 'charge', 'cost', 'free', 'paid']):
            answer = "Opening a NexaBank savings account is **completely free** — zero maintenance charges for digital accounts."
        elif any(w in m for w in ['long', 'time', 'minutes', 'how long']):
            answer = "The entire process takes about **3–5 minutes**. Low-risk accounts are activated instantly!"
        elif any(w in m for w in ['ekyc', 'e-kyc', 'video kyc', 'offline']):
            answer = "We use **AI-powered eKYC** — just upload your document and take a selfie. No branch visit needed."
        else:
            answer = "Great question! I'm here to help with both your queries and account opening."

        # After answering, re-prompt for current step
        step_prompts = {
            'name':   " Now, could you share your **full name** as on your ID?",
            'dob':    " When you're ready, what's your **date of birth**? (YYYY-MM-DD)",
            'email':  " Please go ahead and share your **email address**.",
            'phone':  " And your **mobile number** with country code?",
            'doc':    " You can now **upload your ID document** using the button below.",
            'selfie': " Please go ahead with the **selfie capture**.",
            'otp':    " Please enter the **OTP** you received.",
        }
        return answer + (step_prompts.get(step, '') or '')

    # Step-specific responses for direct answers
    step_responses = {
        'name':   "Nice to meet you! 😊 Could you share your **date of birth** in YYYY-MM-DD format? (e.g., 1995-06-20)",
        'dob':    "Got it! What's your **email address**? We'll send your OTP and account details there.",
        'email':  "Perfect! And your **mobile number** with country code? (e.g., +91-9876543210)",
        'phone':  "All personal details saved! ✅ Please **upload your ID document** — Aadhaar, PAN, or Passport.",
        'doc':    "Document received! Now I need a quick **selfie** for biometric face verification.",
        'selfie': "Selfie done! Sending you an **OTP** to verify your contact details.",
        'otp':    "OTP verified! ✅ Running your final risk assessment now...",
        'done':   "Your application is complete! Welcome to NexaBank 🎉",
    }
    return step_responses.get(step, "Thanks! Let's continue — " + ({
        'name': "what's your **full name**?",
        'dob': "what's your **date of birth**?",
        'email': "what's your **email address**?",
        'phone': "what's your **mobile number**?",
    }.get(step, "please proceed to the next step.")))


@app.route('/api/chat/history/<app_id>', methods=['GET'])
def chat_history(app_id):
    """Load full chat history for a session — enables resume from where left off."""
    con = db_connect()
    # Security: only return history if user owns this app or is admin
    app_row = con.execute("SELECT user_id FROM applications WHERE id=?", (app_id,)).fetchone()
    if not app_row:
        con.close()
        return jsonify({'error': 'Not found'}), 404

    user_id = session.get('user_id')
    is_admin = session.get('admin_logged_in')
    owns_app = app_row['user_id'] == user_id or app_row['user_id'] == 'GUEST'

    if not is_admin and not owns_app and not session.get('demo_user'):
        con.close()
        return jsonify({'error': 'Unauthorized'}), 401

    msgs = con.execute(
        "SELECT role, content, timestamp FROM chat_messages WHERE application_id=? ORDER BY id",
        (app_id,)
    ).fetchall()
    app_data = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    con.close()

    return jsonify({
        'messages': [dict(m) for m in msgs],
        'application': to_dict(app_data)
    })

@app.route('/api/chat/sessions', methods=['GET'])
def user_chat_sessions():
    """Get all chat sessions for the logged-in user."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'sessions': []})

    con = db_connect()
    sessions_data = con.execute("""
        SELECT a.id, a.name, a.status, a.risk_level, a.created_at, a.updated_at,
               COUNT(c.id) as message_count,
               MAX(c.timestamp) as last_message
        FROM applications a
        LEFT JOIN chat_messages c ON c.application_id = a.id
        WHERE a.user_id = ?
        GROUP BY a.id
        ORDER BY a.updated_at DESC
    """, (user_id,)).fetchall()
    con.close()

    return jsonify({'sessions': [to_dict(s) for s in sessions_data]})

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — IDENTITY
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/identity/submit', methods=['POST'])
def submit_identity():
    data   = request.get_json()
    app_id = session.get('app_id') or data.get('application_id')

    if not app_id:
        app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
        user_id = session.get('user_id', 'GUEST')
        ts = now()
        con = db_connect()
        con.execute(
            "INSERT INTO applications(id, user_id, status, method, created_at, updated_at) VALUES(?,?,?,?,?,?)",
            (app_id, user_id, 'In Progress', 'Manual', ts, ts)
        )
        log(con, app_id, 'SESSION_AUTO_CREATED', 'Auto-created during identity submit')
        con.commit()
        con.close()
        session['app_id'] = app_id

    name  = (data.get('name') or '').strip()
    dob   = (data.get('dob') or '').strip()
    email = (data.get('email') or '').strip()
    phone = (data.get('phone') or '').strip()

    errors = {}
    if not name or len(name) < 2:
        errors['name'] = 'Full name is required (min 2 characters)'
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', dob):
        errors['dob'] = 'Date of birth must be in YYYY-MM-DD format'
    if not re.match(r'^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$', email):
        errors['email'] = 'Valid email address required'
    if errors:
        return jsonify({'error': 'Validation failed', 'fields': errors}), 400

    try:
        dob_dt = datetime.strptime(dob, '%Y-%m-%d')
        age    = (datetime.now() - dob_dt).days // 365
        if age < 18:
            return jsonify({'error': f'Applicant must be 18 or older. Calculated age: {age}'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date of birth'}), 400

    ts  = now()
    con = db_connect()
    con.execute("""
        UPDATE applications
        SET name=?, dob=?, email=?, phone=?, updated_at=?
        WHERE id=?
    """, (name, dob, email, phone, ts, app_id))
    log(con, app_id, 'IDENTITY_SUBMITTED', f'Name:{name} | DOB:{dob} | Email:{email}')

    con.commit()
    con.close()

    return jsonify({'success': True, 'application_id': app_id, 'age': age, 'name': name})

def get_face_score(selfie_path, doc_path):
    result = DeepFace.verify(
        img1_path=selfie_path,
        img2_path=doc_path,
        enforce_detection=False,
        detector_backend="opencv"
    )

    distance = result["distance"]
    score = int(max(0, (1 - distance) * 100))

    return score, result["verified"]

@app.route('/api/application/finalize', methods=['POST'])
def finalize_application():
    app_id = session.get('app_id')

    con = db_connect()

    app_row = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    doc_rows = con.execute("SELECT * FROM documents WHERE application_id=?", (app_id,)).fetchall()
    behavior_rows = con.execute("SELECT * FROM behavior_logs WHERE app_id=?", (app_id,)).fetchall()

    score, level, signals, reason = compute_risk(app_row, doc_rows, behavior_rows)

    con.execute("""
        UPDATE applications
        SET risk_score=?, risk_level=?, status=?, updated_at=?
        WHERE id=?
    """, (score, level, level, now(), app_id))

    con.commit()
    con.close()

    return jsonify({
        "application_id": app_id,
        "risk_score": score,
        "risk_level": level,
        "reason": reason,
        "signals": signals
    })

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — DOCUMENT UPLOAD
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/documents/upload', methods=['POST'])
def upload_document():
    app_id   = session.get('app_id') or request.form.get('application_id')
    doc_type = request.form.get('doc_type', 'Aadhaar')

    if not app_id:
        app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
        user_id = session.get('user_id', 'GUEST')
        ts = now()
        con = db_connect()
        con.execute(
            "INSERT INTO applications(id, user_id, status, method, created_at, updated_at) VALUES(?,?,?,?,?,?)",
            (app_id, user_id, 'In Progress', 'Manual', ts, ts)
        )
        con.commit()
        con.close()
        session['app_id'] = app_id

    if doc_type not in ('Aadhaar', 'PAN', 'Passport'):
        return jsonify({'error': 'Invalid document type'}), 400

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_DOC:
        return jsonify({'error': f'File type .{ext} not allowed. Use PNG, JPG, or PDF'}), 400

    doc_id      = str(uuid.uuid4())
    stored_name = f"{app_id}_{doc_type}_{doc_id[:8]}.{ext}"
    save_path   = os.path.join(DOC_DIR, stored_name)
    file.save(save_path)

    with open(save_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    file_size = os.path.getsize(save_path)

    ocr = run_ocr(save_path, doc_type)

    tamper_flags = ocr['tamper_flags']
    confidence   = ocr['confidence']
    verified     = len(tamper_flags) == 0 and confidence >= 30

    ts  = now()
    con = db_connect()
    con.execute("""
        INSERT INTO documents
        (id,application_id,doc_type,original_name,stored_name,file_hash,file_size,
         ocr_text,ocr_name,ocr_dob,ocr_id_number,tamper_flags,confidence,verified,uploaded_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (doc_id, app_id, doc_type, file.filename, stored_name,
          file_hash, file_size, ocr['raw_text'],
          ocr['name'], ocr['dob'], ocr['id_number'],
          json.dumps(tamper_flags), confidence, 1 if verified else 0, ts))

    con.execute("""
        UPDATE applications SET id_type=?, doc_path=?, updated_at=? WHERE id=?
    """, (doc_type, stored_name, ts, app_id))

    log(con, app_id, 'DOCUMENT_UPLOADED',
        f'Type:{doc_type} | File:{stored_name} | OCR:{confidence}%')
    con.commit()
    con.close()

    return jsonify({
        'success': True,
        'document_id': doc_id,
        'doc_type': doc_type,
        'file_hash': file_hash,
        'file_size_kb': round(file_size / 1024, 1),
        'ocr': {
            'name': ocr['name'], 'dob': ocr['dob'],
            'id_number': ocr['id_number'],
            'confidence': confidence,
            'raw_preview': ocr['raw_text'][:200] if ocr['raw_text'] else ''
        },
        'tamper_flags': tamper_flags,
        'verified': verified
    })

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — SELFIE
# ══════════════════════════════════════════════════════════════════════════════

# @app.route('/api/biometric/selfie', methods=['POST'])
# def upload_selfie():
#     app_id = session.get('app_id') or request.form.get('application_id')
#     if not app_id:
#         app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
#         user_id = session.get('user_id', 'GUEST')
#         ts = now()
#         con = db_connect()
#         con.execute(
#             "INSERT INTO applications(id, user_id, status, method, created_at, updated_at) VALUES(?,?,?,?,?,?)",
#             (app_id, user_id, 'In Progress', 'Manual', ts, ts)
#         )
#         con.commit()
#         con.close()
#         session['app_id'] = app_id

#     if 'selfie' not in request.files:
#         return jsonify({'error': 'No selfie file received'}), 400

#     file = request.files['selfie']
#     ext  = (file.filename or 'selfie.jpg').rsplit('.', 1)[-1].lower()
#     if ext not in ALLOWED_SELFIE:
#         ext = 'jpg'

#     selfie_name = f"{app_id}_selfie.{ext}"
#     save_path   = os.path.join(SELFIE_DIR, selfie_name)
#     file.save(save_path)

#     doc = con.execute("""
#         SELECT stored_name FROM documents
#         WHERE application_id=? ORDER BY uploaded_at DESC LIMIT 1
#     """, (app_id,)).fetchone()

#     doc_path = os.path.join(DOC_DIR, doc['stored_name'])
#     face_score, face_status_flag = get_face_score(save_path, doc_path)

#     face_status = "Matched" if face_status_flag else "Weak"

#     ts  = now()
#     con = db_connect()
#     con.execute("""
#         UPDATE applications
#         SET selfie_path=?, face_score=?, face_status=?, updated_at=?
#         WHERE id=?
#     """, (selfie_name, face_score, face_status, ts, app_id))
#     log(con, app_id, 'SELFIE_UPLOADED',
#         f'File:{selfie_name} | FaceScore:{face_score}% | Status:{face_status}')
#     con.commit()
#     con.close()

#     return jsonify({
#         'success': True,
#         'selfie_stored': selfie_name,
#         'face_score': face_score,
#         'face_status': face_status,
#         'liveness': True
#     })
@app.route('/api/biometric/selfie', methods=['POST'])
def upload_selfie():
    app_id = session.get('app_id') or request.form.get('application_id')

    if not app_id:
        app_id = 'NXB-' + uuid.uuid4().hex[:8].upper()
        user_id = session.get('user_id', 'GUEST')
        ts = now()
        con = db_connect()
        con.execute(
            "INSERT INTO applications(id, user_id, status, method, created_at, updated_at) VALUES(?,?,?,?,?,?)",
            (app_id, user_id, 'In Progress', 'Manual', ts, ts)
        )
        con.commit()
        con.close()
        session['app_id'] = app_id

    if 'selfie' not in request.files:
        return jsonify({'error': 'No selfie file received'}), 400

    file = request.files['selfie']
    ext  = (file.filename or 'selfie.jpg').rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_SELFIE:
        ext = 'jpg'

    selfie_name = f"{app_id}_selfie.{ext}"
    save_path   = os.path.join(SELFIE_DIR, selfie_name)
    file.save(save_path)

    # ✅ OPEN DB CONNECTION FIRST
    con = db_connect()

    # ✅ GET DOCUMENT
    doc = con.execute("""
        SELECT stored_name FROM documents
        WHERE application_id=? ORDER BY uploaded_at DESC LIMIT 1
    """, (app_id,)).fetchone()

    if not doc:
        con.close()
        return jsonify({'error': 'No document found. Upload document first.'}), 400

    doc_path = os.path.join(DOC_DIR, doc['stored_name'])

    # ✅ SAFE FACE MATCHING
    try:
        face_score, face_status_flag = get_face_score(save_path, doc_path)
        if face_score >= 75:
            face_status = "Matched"
        elif face_score >= 50:
            face_status = "Weak"
        else:
            face_status = "Mismatch"
    except Exception as e:
        face_score = 0
        face_status = "Error"

    ts = now()

    con.execute("""
        UPDATE applications
        SET selfie_path=?, face_score=?, face_status=?, updated_at=?
        WHERE id=?
    """, (selfie_name, face_score, face_status, ts, app_id))

    log(con, app_id, 'SELFIE_UPLOADED',
        f'File:{selfie_name} | FaceScore:{face_score}% | Status:{face_status}')

    con.commit()
    con.close()

    return jsonify({
        'success': True,
        'selfie_stored': selfie_name,
        'face_score': face_score,
        'face_status': face_status,
        'liveness': True
    })

def get_face_score(selfie_path, doc_path):
    result = DeepFace.verify(
        img1_path=selfie_path,
        img2_path=doc_path,
        enforce_detection=False,
        detector_backend="opencv"
    )

    distance = result["distance"]
    score = int(max(0, (1 - distance) * 100))

    return score, result["verified"]


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — OTP
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/otp/store', methods=['POST'])
def otp_store():
    data     = request.get_json() or {}
    app_id   = session.get('app_id') or data.get('application_id')
    otp_hash = data.get('otp_hash')

    if not otp_hash:
        return jsonify({'error': 'Missing otp_hash field'}), 400
    if not app_id:
        return jsonify({'error': 'Missing application_id'}), 400

    ts  = now()
    con = db_connect()

    if app_id.startswith('NXB-OFFLINE'):
        app_exists = con.execute("SELECT id FROM applications WHERE id=?", (app_id,)).fetchone()
        if not app_exists:
            user_id = session.get('user_id', 'GUEST')
            con.execute(
                "INSERT INTO applications(id, user_id, status, method, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                (app_id, user_id, 'In Progress', 'Manual', ts, ts)
            )

    con.execute("UPDATE applications SET otp_hash=?, updated_at=? WHERE id=?",
                (otp_hash, ts, app_id))
    log(con, app_id, 'OTP_GENERATED', 'OTP hash stored')
    con.commit()
    con.close()
    return jsonify({'success': True})

@app.route('/api/otp/verify', methods=['POST'])
def otp_verify():
    data     = request.get_json() or {}
    app_id   = session.get('app_id') or data.get('application_id')
    otp_hash = data.get('otp_hash')

    if not otp_hash:
        return jsonify({'error': 'Missing otp_hash field'}), 400
    if not app_id:
        return jsonify({'error': 'Missing application_id'}), 400

    con     = db_connect()
    app_row = con.execute("SELECT otp_hash FROM applications WHERE id=?", (app_id,)).fetchone()

    if not app_row:
        con.close()
        return jsonify({'error': f'Application {app_id} not found'}), 404

    if not app_row['otp_hash']:
        con.close()
        return jsonify({'error': 'No OTP stored for this application'}), 400

    if app_row['otp_hash'] != otp_hash:
        log(con, app_id, 'OTP_FAILED', 'Incorrect OTP entered')
        con.commit()
        con.close()
        return jsonify({'success': False, 'error': 'Incorrect OTP. Please try again.'}), 400

    ts = now()
    con.execute("UPDATE applications SET otp_verified=1, updated_at=? WHERE id=?", (ts, app_id))
    log(con, app_id, 'OTP_VERIFIED', 'OTP verified successfully')
    con.commit()
    con.close()
    return jsonify({'success': True, 'verified': True})

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — RISK + ACCOUNT
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/risk/evaluate', methods=['POST'])
def risk_evaluate():
    data   = request.get_json() or {}
    app_id = session.get('app_id') or data.get('application_id')
    if not app_id:
        return jsonify({'error': 'Missing application_id'}), 400

    con      = db_connect()
    app_row  = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    doc_rows = con.execute("SELECT * FROM documents WHERE application_id=?", (app_id,)).fetchall()
    behavior_rows = con.execute("SELECT * FROM behavior_logs WHERE application_id=?",(app_id,)).fetchall()

    behavior_rows = [dict(b) for b in behavior_rows]

    if not app_row:
        con.close()
        return jsonify({'error': 'Application not found'}), 404

    score, level, signals, reason = compute_risk(dict(app_row), [dict(d) for d in doc_rows],behavior_rows)

    account_number = None
    ifsc           = None
    if level in ('Low', 'Medium'):
        n = ''.join([str(random.randint(0, 9)) for _ in range(12)])
        account_number = f"{n[:4]} {n[4:8]} {n[8:]}"
        ifsc = 'NXBA0001234'

    new_status = {'Low': 'Approved', 'Medium': 'Pending', 'High': 'Escalated'}[level]
    ts = now()

    con.execute("""
        UPDATE applications
        SET risk_score=?, risk_level=?, risk_signals=?, risk_reason=?,
            account_number=?, ifsc=?, status=?, updated_at=?
        WHERE id=?
    """, (score, level, json.dumps(signals), reason,
          account_number, ifsc, new_status, ts, app_id))

    log(con, app_id, 'RISK_EVALUATED', f'Score:{score} | Level:{level} | Status:{new_status}')
    con.commit()
    con.close()

    return jsonify({
        'success': True,
        'risk_score': score,
        'risk_level': level,
        'risk_reason': reason,
        'signals': signals,
        'status': new_status,
        'account_number': account_number,
        'ifsc': ifsc,
        'branch': 'NexaBank Digital Branch'
    })

@app.route('/api/account/summary/<app_id>', methods=['GET'])
def account_summary(app_id):
    con     = db_connect()
    app_row = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    docs    = con.execute("SELECT * FROM documents WHERE application_id=?", (app_id,)).fetchall()
    con.close()
    if not app_row:
        return jsonify({'error': 'Not found'}), 404
    result = to_dict(app_row)
    result['documents'] = [to_dict(d) for d in docs]
    return jsonify(result)

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — ADMIN API
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    con = db_connect()
    def q(sql): return con.execute(sql).fetchone()[0]
    stats = {
        'total':       q("SELECT COUNT(*) FROM applications"),
        'approved':    q("SELECT COUNT(*) FROM applications WHERE status='Approved'"),
        'pending':     q("SELECT COUNT(*) FROM applications WHERE status='Pending'"),
        'escalated':   q("SELECT COUNT(*) FROM applications WHERE status='Escalated'"),
        'in_progress': q("SELECT COUNT(*) FROM applications WHERE status='In Progress'"),
        'rejected':    q("SELECT COUNT(*) FROM applications WHERE status='Rejected'"),
        'low':         q("SELECT COUNT(*) FROM applications WHERE risk_level='Low'"),
        'medium':      q("SELECT COUNT(*) FROM applications WHERE risk_level='Medium'"),
        'high':        q("SELECT COUNT(*) FROM applications WHERE risk_level='High'"),
        'avg_risk':    round(q("SELECT COALESCE(AVG(risk_score),0) FROM applications WHERE risk_score IS NOT NULL"), 1),
        'overrides':   q("SELECT COUNT(*) FROM admin_decisions WHERE ai_overridden=1"),
        'total_docs':  q("SELECT COUNT(*) FROM documents"),
        'total_chats': q("SELECT COUNT(*) FROM chat_messages"),
        'total_users': q("SELECT COUNT(*) FROM user_accounts"),
    }
    con.close()
    return jsonify(stats)

@app.route('/api/admin/applications', methods=['GET'])
@admin_required
def admin_applications():
    status  = request.args.get('status', '')
    risk    = request.args.get('risk', '')
    search  = request.args.get('q', '')
    page    = max(1, int(request.args.get('page', 1)))
    limit   = min(50, int(request.args.get('limit', 20)))
    offset  = (page - 1) * limit

    con    = db_connect()
    where  = ['1=1']
    params = []
    if status: where.append("status=?");             params.append(status)
    if risk:   where.append("risk_level=?");         params.append(risk)
    if search:
        where.append("(name LIKE ? OR email LIKE ? OR id LIKE ?)")
        params.extend([f'%{search}%'] * 3)

    sql   = f"SELECT * FROM applications WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    apps  = con.execute(sql, params + [limit, offset]).fetchall()
    total = con.execute(f"SELECT COUNT(*) FROM applications WHERE {' AND '.join(where)}", params).fetchone()[0]
    con.close()

    return jsonify({
        'applications': [to_dict(a) for a in apps],
        'total': total, 'page': page, 'limit': limit
    })

@app.route('/api/admin/application/<app_id>', methods=['GET'])
@admin_required
def admin_application_detail(app_id):
    con      = db_connect()
    app_row  = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    docs     = con.execute("SELECT * FROM documents WHERE application_id=?", (app_id,)).fetchall()
    audit    = con.execute("SELECT * FROM audit_log WHERE application_id=? ORDER BY id DESC LIMIT 30", (app_id,)).fetchall()
    decisions = con.execute("SELECT * FROM admin_decisions WHERE application_id=? ORDER BY id DESC", (app_id,)).fetchall()
    chats    = con.execute("SELECT * FROM chat_messages WHERE application_id=? ORDER BY id", (app_id,)).fetchall()
    con.close()

    if not app_row:
        return jsonify({'error': 'Not found'}), 404

    return jsonify({
        'application': to_dict(app_row),
        'documents':   [to_dict(d) for d in docs],
        'audit_log':   [to_dict(a) for a in audit],
        'decisions':   [to_dict(d) for d in decisions],
        'chat':        [to_dict(c) for c in chats],
    })

@app.route('/api/admin/decision', methods=['POST'])
@admin_required
def admin_decision():
    data     = request.get_json()
    app_id   = data.get('application_id')
    decision = data.get('decision')
    notes    = (data.get('notes') or '').strip()
    admin    = session.get('admin_username', 'admin')

    if not app_id or not decision:
        return jsonify({'error': 'Missing application_id or decision'}), 400
    if decision not in ('Approved', 'Rejected', 'More Info', 'Pending'):
        return jsonify({'error': 'Invalid decision value'}), 400

    con     = db_connect()
    app_row = con.execute("SELECT risk_level, status, account_number, email, name FROM applications WHERE id=?", (app_id,)).fetchone()
    if not app_row:
        con.close()
        return jsonify({'error': 'Application not found'}), 404

    ai_rec   = {'Low': 'Approved', 'Medium': 'Pending', 'High': 'Escalated'}.get(app_row['risk_level'], 'Pending')
    overrode = 1 if decision != ai_rec else 0

    new_status = {
        'Approved':  'Approved',
        'Rejected':  'Rejected',
        'More Info': 'Pending',
        'Pending':   'Pending'
    }.get(decision, 'Pending')

    account_number = app_row['account_number']
    ifsc = None
    if decision == 'Approved' and not account_number:
        n = ''.join([str(random.randint(0, 9)) for _ in range(12)])
        account_number = f"{n[:4]} {n[4:8]} {n[8:]}"
        ifsc = 'NXBA0001234'

    ts = now()
    con.execute("""
        UPDATE applications SET status=?, account_number=?, ifsc=COALESCE(ifsc, ?), updated_at=? WHERE id=?
    """, (new_status, account_number, ifsc, ts, app_id))

    con.execute("""
        INSERT INTO admin_decisions(application_id,admin_username,decision,notes,ai_overridden,decided_at)
        VALUES(?,?,?,?,?,?)
    """, (app_id, admin, decision, notes, overrode, ts))

    # Add a system message to the chat so user sees the decision when they resume
    status_msg = {
        'Approved': f"✅ Great news, {app_row['name'] or 'Applicant'}! Your application has been **approved** by a NexaBank reviewer. Your account is now active. Account number: **{account_number}**",
        'Rejected': f"❌ We regret to inform you that your application has been **rejected** by our review team. Notes: {notes or 'Please contact support for details.'}",
        'Pending':  f"ℹ️ Our team has requested **additional information** for your application. Notes: {notes or 'Please check your registered email for further instructions.'}",
    }.get(new_status, '')

    if status_msg:
        con.execute(
            "INSERT INTO chat_messages(application_id, user_id, role, content, timestamp) VALUES(?,?,?,?,?)",
            (app_id, 'SYSTEM', 'assistant', status_msg, ts)
        )

    log(con, app_id, 'ADMIN_DECISION',
        f'Decision:{decision} | Admin:{admin} | Override:{bool(overrode)} | Notes:{notes[:80]}',
        actor=admin)
    con.commit()
    con.close()

    return jsonify({
        'success':        True,
        'new_status':     new_status,
        'account_number': account_number,
        'ai_overridden':  bool(overrode),
        'decision':       decision
    })

@app.route('/api/admin/audit', methods=['GET'])
@admin_required
def admin_audit():
    app_id = request.args.get('application_id')
    page   = max(1, int(request.args.get('page', 1)))
    limit  = min(100, int(request.args.get('limit', 50)))
    offset = (page - 1) * limit

    con = db_connect()
    if app_id:
        rows  = con.execute("SELECT * FROM audit_log WHERE application_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (app_id, limit, offset)).fetchall()
        total = con.execute("SELECT COUNT(*) FROM audit_log WHERE application_id=?", (app_id,)).fetchone()[0]
    else:
        rows  = con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        total = con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    con.close()

    return jsonify({'logs': [to_dict(r) for r in rows], 'total': total, 'page': page})

@app.route('/health')
def health():
    try:
        con = db_connect()
        con.execute("SELECT 1").fetchone()
        con.close()
        db_ok = True
    except:
        db_ok = False

    return jsonify({
        'status': 'ok',
        'db':     'connected' if db_ok else 'error',
        'ocr':    'available' if OCR_AVAILABLE else 'not installed',
        'claude': 'configured' if ANTHROPIC_API_KEY else 'rule-based fallback',
        'time':   now()
    })

@app.errorhandler(sqlite3.OperationalError)
def sqlite_locked(e):
    return jsonify({'error': 'Database busy, please retry'}), 503

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Server error: ' + str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

if __name__ == '__main__':
    init_db()
    print("\n" + "=" * 58)
    print("  NexaBank Onboarding System v2")
    print(f"  User Login   : http://localhost:5000/login")
    print(f"  Customer App : http://localhost:5000")
    print(f"  Admin Login  : http://localhost:5000/admin-login")
    print(f"  Admin Panel  : http://localhost:5000/admin")
    print(f"  Health Check : http://localhost:5000/health")
    print()
    print("  Admin Credentials:")
    print("    Username: admin     Password: admin123")
    print("    Username: reviewer  Password: reviewer123")
    print()
    print("  User Registration: /login (Create Account tab)")
    print("  Optional: set ANTHROPIC_API_KEY for conversational AI")
    print("=" * 58 + "\n")
    app.run(debug=True, port=8000, host='0.0.0.0')