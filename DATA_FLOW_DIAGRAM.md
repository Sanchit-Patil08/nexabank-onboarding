# NexaBank Data Flow Diagram

## Complete Application Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CUSTOMER ONBOARDING FLOW                          │
└─────────────────────────────────────────────────────────────────────────────┘

1. LANDING PAGE
   ┌──────────────────┐
   │  Start Onboarding│
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────────────────────┐
   │ ensureAppId()                    │
   │ - Call /api/session/start        │
   │ - Receive: NXB-ABC12345          │
   │ - Save to S.appId                │
   │ [ensureAppId] ✓ Session created  │
   └────────┬─────────────────────────┘
            │
            ▼
   ┌──────────────────────────────────┐
   │ Chat Interface Ready             │
   │ S.appId = "NXB-ABC12345"         │
   └──────┬───────────────────────────┘
          │
          ├─────────────────────────────────────┐
          │                                     │
          ▼                                     ▼

2. IDENTITY ENTRY                       3. DOCUMENT UPLOAD
   ┌──────────────────┐                   ┌──────────────────┐
   │ Name: John Doe   │                   │ Select: Aadhaar  │
   │ DOB: 1995-03-15  │                   │ Upload: photo    │
   │ Email: john@... │ 📤                │ 📤              │
   │ Phone: +91-...  │ POST/api/identity │ POST/api/docs   │
   └────────┬─────────┘                   └────────┬─────────┘
            │                                      │
            ▼                                      ▼
   ┌──────────────────────────────────┐  ┌──────────────────────────────────┐
   │ Backend: update applications     │  │ Backend: store document + OCR    │
   │         SET name, dob, email,   │  │ - Save file to /uploads/docs    │
   │             phone                │  │ - Run OCR → extract name, ID   │
   │ WHERE id='NXB-ABC12345'          │  │ - Verify: file_hash, confidence│
   │                                  │  │ WHERE id='NXB-ABC12345'        │
   │ [Identity] ✓ Verified saved      │  │                                │
   │            to DB                │  │ Document record created         │
   │ name=John Doe, email=john@...   │  │                                │
   └──────────────────────────────────┘  └──────────────────────────────────┘
            │                                      │
            │  ✅ Response                         │  ✅ Response
            │  {success: true,                     │  {success: true,
            │   application_id: 'NXB-ABC12345'}    │   file_hash: 'abc123...'}
            │                                      │
            └──────────────┬───────────────────────┘
                           │
                           ▼

4. SELFIE CAPTURE                       5. OTP VERIFICATION
   ┌──────────────────┐                   ┌──────────────────┐
   │ Capture: selfie  │                   │ OTP: 123456      │
   │ 📸              │ 📤                │ Verify hash      │
   │ POST/api/selfie │┐                 │ POST/api/otp/ver │
   └────────┬─────────┘ │                └────────┬─────────┘
            │           │                         │
            ▼           │                         ▼
   ┌──────────────────────────────────┐  ┌──────────────────────────────────┐
   │ Backend: store selfie + face match│  │ Backend: verify OTP hash         │
   │ - Save file to /uploads/selfies  │  │ - Hash received OTP              │
   │ - Compute face_score (82-98%)    │  │ - Compare with stored hash       │
   │ - Verify: selfie_path, score     │  │ - Set otp_verified = 1           │
   │ WHERE id='NXB-ABC12345'          │  │ WHERE id='NXB-ABC12345'          │
   │                                  │  │                                  │
   │ [Selfie] ✓ Verified saved        │  │ [verifyOTP] ✓ Response:          │
   │          to DB                   │  │             {verified: true}     │
   │ path=NXB-ABC12345_selfie.jpg    │  └──────────────────────────────────┘
   │ score=92                          │           │
   └──────────────────────────────────┘            │
            │                                      │
            │  ✅ Response                         │
            │  {success: true,                     │
            │   face_score: 92,                    │
            │   face_status: 'Matched'}            │
            │                                      │
            └──────────────┬───────────────────────┘
                           │
                           ▼

6. RISK EVALUATION
   ┌──────────────────────────────────┐
   │ Analyze:                         │
   │ - Document integrity             │
   │ - AML watchlist                  │
   │ - CIBIL data                     │
   │ - Biometric confidence           │
   │ - Risk signals                   │
   │                                  │
   │ 📤 POST/api/risk/evaluate        │
   └────────┬─────────────────────────┘
            │
            ▼
   ┌──────────────────────────────────┐
   │ Backend: compute_risk()          │
   │ - Read: name, email, risk_signals│
   │ - Calculate: score, level        │
   │ - Level: Low (28) → Approved    │
   │ - Generate account if Low/Med    │
   │                                  │
   │ UPDATE applications              │
   │ SET risk_score = 28,             │
   │     risk_level = 'Low',          │
   │     status = 'Approved',         │
   │     account_number = '1234 5678' │
   │     ifsc = 'NXBA0001234'         │
   │ WHERE id='NXB-ABC12345'          │
   │                                  │
   │ [Risk] ✓ Verified saved to DB:   │
   │        risk=Low, status=Approved │
   │        account=1234 5678 9012    │
   └──────────────────────────────────┘
            │
            ▼
   ┅ ✅ Success Page Displayed ✅ ┅
   Account Created: NXB-ABC12345
   Account: 1234 5678 9012
   IFSC: NXBA0001234
   ┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅


┌─────────────────────────────────────────────────────────────────────────────┐
│                        DATABASE STATE (applications table)                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ AFTER IDENTITY:                                                             │
│ id='NXB-ABC12345', name='John Doe', email='john@test.com', dob='1995-03-15'│
│ phone='+91-9876543210', status='In Progress'                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ + AFTER DOCUMENT:                                                           │
│ id_type='Aadhaar', id_number='XXXX-XXXX-1234'                              │
│ (documents table: doc_type, file_hash, confidence, etc.)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ + AFTER SELFIE:                                                             │
│ selfie_path='NXB-ABC12345_selfie.jpg', face_score=92, face_status='Matched'│
├─────────────────────────────────────────────────────────────────────────────┤
│ + AFTER OTP:                                                                │
│ otp_verified=1                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ + AFTER RISK:                                                               │
│ risk_level='Low', risk_score=28, status='Approved'                          │
│ account_number='1234 5678 9012', ifsc='NXBA0001234'                        │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                         ADMIN PANEL DATA RETRIEVAL                           │
└─────────────────────────────────────────────────────────────────────────────┘

Admin Login (admin/admin123)
        │
        ▼
/api/admin/stats          ← Shows counts
/api/admin/applications   ← Lists all applications

        │
        ▼
Click "Review" on application

        │
        ▼
GET /api/admin/application/NXB-ABC12345

        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ Backend: admin_application_detail()                              │
│                                                                   │
│ SELECT * FROM applications WHERE id='NXB-ABC12345'              │
│ [Admin] Application loaded with fields:                         │
│ id, name, dob, email, phone, id_type, id_number,               │
│ selfie_path, face_score, face_status, otp_verified,            │
│ risk_score, risk_level, risk_signals, risk_reason,             │
│ account_number, ifsc, status, created_at, updated_at           │
│                                                                   │
│ SELECT * FROM documents WHERE application_id='NXB-ABC12345'    │
│ SELECT * FROM audit_log WHERE application_id='NXB-ABC12345'    │
│ SELECT * FROM chat_messages WHERE application_id=...           │
│                                                                   │
│ Return JSON with all application data populated                 │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ Frontend: Admin Panel Modal                                      │
│                                                                  │
│ ✓ Application ID: NXB-ABC12345                                 │
│ ✓ Full Name: John Doe                    ← From applications   │
│ ✓ Email: john@test.com                   ← From applications   │
│ ✓ DOB: 1995-03-15                        ← From applications   │
│ ✓ ID Type: Aadhaar                       ← From applications   │
│ ✓ Face Score: 92% (Matched)              ← From applications   │
│ ✓ OTP Verified: Yes                      ← From applications   │
│ ✓ Risk: Low (28/100)                     ← From applications   │
│ ✓ Status: Approved                       ← From applications   │
│ ✓ Account Number: 1234 5678 9012         ← From applications   │
│ ✓ IFSC: NXBA0001234                      ← From applications   │
│                                                                  │
│ Documents:                               ← From documents table│
│ - Aadhaar (verified, OCR extracted)                             │
│                                                                  │
│ Audit Log:                               ← From audit_log table│
│ - SESSION_STARTED                                               │
│ - IDENTITY_SUBMITTED                                            │
│ - DOCUMENT_UPLOADED                                             │
│ - SELFIE_UPLOADED                                               │
│ - OTP_VERIFIED                                                  │
│ - RISK_EVALUATED                                                │
│                                                                  │
│ Chat Transcript:                         ← From chat_messages  │
│ - All conversation between user & ARIA                          │
└──────────────────────────────────────────────────────────────────┘


KEY VERIFICATION CHECKPOINTS
═════════════════════════════════════════════════════════════════

Step 1: Identity      → [Identity] ✓ Verified saved to DB
Step 2: Document      → [Document] ✓ Verified saved to DB
Step 3: Selfie        → [Selfie] ✓ Verified saved to DB
Step 4: OTP           → [verifyOTP] ✓ Verified hash match
Step 5: Risk          → [Risk] ✓ Verified saved to DB
Step 6: Admin Retrieve → [Admin] Application fields: ...long list...

⚠️ If ANY step shows ✗ (failure), data flow is broken at that point
✅ If ALL steps show ✓ (success), admin panel will have complete data
