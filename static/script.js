// ═══════════════════════════════════════════════════════════
// NEXABANK FRONTEND v2 — Conversational AI + Chat History
// ═══════════════════════════════════════════════════════════
const S = {
  appId: null,
  userData: {},
  currentStep: 'idle',
  riskLevel: null, riskScore: null,
  accountNumber: null, ifsc: null,
  generatedOTP: null,
  timerStart: Date.now(),
  selectedAppId: null,
  currentUser: null,
  stepStartTime : Date.now(),
};

// ═══════════════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════════════
async function api(method, path, body) {
  try {
    const opts = { method, headers: {'Content-Type': 'application/json'}, credentials: 'include' };
    if (body){
      opts.body = JSON.stringify(body);
      body.timestamp = Date.now();
    } 
    const res = await fetch(path, opts);
    if (res.status === 401 && !path.includes('/user/me')) {
      window.location.href = '/login';
      return;
    }
    const ct = res.headers.get('content-type') || '';
    const data = ct.includes('json') ? await res.json() : { error: await res.text() };
    if (!res.ok) throw new Error(data.error || 'API error ' + res.status);
    return data;
  } catch(e) {
    if (e.message && e.message.toLowerCase().includes('database busy')) {
      await delay(400);
      return api(method, path, body);
    }
    console.error(`[API Error] ${path}:`, e.message);
    showToast('❌ ' + e.message, 'error');
    throw e;
  }
}

async function apiForm(path, fd) {
  try {
    const res = await fetch(path, { method: 'POST', body: fd, credentials: 'include' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Upload error');
    return data;
  } catch(e) { showToast('❌ ' + e.message, 'error'); throw e; }
}

async function sha256(str) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('');
}

// ═══════════════════════════════════════════════════════════
// SCREENS
// ═══════════════════════════════════════════════════════════
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

setInterval(() => {
  const el = document.getElementById('sessionTimer');
  if (!el) return;
  const s = Math.floor((Date.now() - S.timerStart) / 1000);
  el.textContent = String(Math.floor(s / 60)).padStart(2,'0') + ':' + String(s % 60).padStart(2,'0');
}, 1000);

// ═══════════════════════════════════════════════════════════
// INIT — Check user session
// ═══════════════════════════════════════════════════════════
// async function checkUserSession() {
//   try {
//     const me = await api('GET', '/api/user/me');
//     if (me && me.logged_in) {
//       S.currentUser = me;
//       updateLandingForUser(me);
//     }
//   } catch(e) {
//     console.log('[Session] No active user session');
//   }
// }

async function checkUserSession() {
  try {
    const res = await fetch('/api/user/me', { credentials: 'include' });
    const me = await res.json();
    console.log('[Session check]', me);  // tells you exactly what's happening
    if (me && me.logged_in) {
      S.currentUser = me;
      updateLandingForUser(me);
    }
  } catch(e) {
    console.log('[Session] error:', e.message);
  }
}

function updateLandingForUser(user) {
  const landingEl = document.getElementById('landing');
  if (!landingEl) return;

  const old = document.getElementById('user-greeting');
  if (old) old.remove();

  const greet = document.createElement('div');
  greet.id = 'user-greeting';
  greet.style.cssText = `
    position: absolute; top: 20px; right: 24px;
    display: flex; align-items: center; gap: 12px;
    background: rgba(201,168,76,.08); border: 1px solid rgba(201,168,76,.2);
    border-radius: 10px; padding: 8px 16px; font-size: .82rem; z-index: 10;
  `;
  greet.innerHTML = `
    <span style="color:var(--gold);">👤 ${user.name}${user.demo ? ' (Guest)' : ''}</span>
    <button id="sessionsBtn" style="background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);color:var(--text2);border-radius:6px;padding:4px 10px;font-size:.72rem;cursor:pointer;font-family:'Outfit',sans-serif;">
      My Sessions
    </button>
    <button id="logoutBtn" style="background:none;border:none;color:var(--text2);font-size:.72rem;cursor:pointer;font-family:'Outfit',sans-serif;">Sign Out</button>
  `;
  landingEl.appendChild(greet);
  document.getElementById('sessionsBtn').addEventListener('click', showSessionHistory);
  document.getElementById('logoutBtn').addEventListener('click', doUserLogout);
}

async function doUserLogout() {
  await api('POST', '/api/user/logout');
  window.location.href = '/login';
}

// ═══════════════════════════════════════════════════════════
// SESSION HISTORY MODAL
// ═══════════════════════════════════════════════════════════
async function showSessionHistory() {
  try {
    const data = await api('GET', '/api/chat/sessions');
    const sessions = data.sessions || [];

    let sessionHtml = '';
    if (sessions.length === 0) {
      sessionHtml = '<div style="color:var(--text2);text-align:center;padding:20px;">No previous sessions found.</div>';
    } else {
      sessionHtml = sessions.map(s => `
        <div style="background:var(--bg3);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:14px;margin-bottom:10px;cursor:pointer;transition:border-color .2s;"
             onmouseover="this.style.borderColor='var(--gold)'" onmouseout="this.style.borderColor='rgba(255,255,255,.06)'"
             onclick="resumeSession('${s.id}')">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <span style="font-family:'DM Mono',monospace;font-size:.72rem;color:var(--gold);">${s.id}</span>
            <span style="font-size:.7rem;color:${
              s.status === 'Approved' ? 'var(--green)' :
              s.status === 'Rejected' ? 'var(--red)' :
              s.status === 'Escalated' ? '#f97316' :
              'var(--text2)'
            };font-weight:500;">${s.status || 'In Progress'}</span>
          </div>
          <div style="font-size:.85rem;font-weight:500;">${s.name || 'Unnamed Application'}</div>
          <div style="display:flex;justify-content:space-between;margin-top:4px;">
            <span style="font-size:.72rem;color:var(--text2);">${s.message_count || 0} messages</span>
            <span style="font-size:.72rem;color:var(--text2);">${(s.updated_at || '').substring(0,10)}</span>
          </div>
        </div>
      `).join('');
    }

    showInfoModal(`
      <div style="font-family:'Cormorant Garamond',serif;font-size:1.4rem;font-weight:600;margin-bottom:16px;">Your Sessions</div>
      <div style="max-height:400px;overflow-y:auto;">${sessionHtml}</div>
      <div style="margin-top:16px;text-align:center;">
        <button onclick="closeInfoModal();startOnboarding()" style="background:linear-gradient(135deg,var(--gold),var(--gold2));border:none;color:#0D0A00;font-family:'Outfit',sans-serif;font-size:.88rem;font-weight:600;padding:10px 24px;border-radius:8px;cursor:pointer;">
          + New Application
        </button>
      </div>
    `);
  } catch(e) {
    showToast('Failed to load sessions: ' + e.message, 'error');
  }
}

async function resumeSession(appId) {
  closeInfoModal();
  try {
    const data = await api('GET', `/api/chat/history/${appId}`);
    const msgs = data.messages || [];
    const appData = data.application || {};

    S.appId = appId;
    S.userData = {
      name:  appData.name,
      dob:   appData.dob,
      email: appData.email,
      phone: appData.phone,
    };

    if (appData.status === 'Approved' || appData.status === 'Rejected') {
      S.currentStep = 'done';
    } else if (appData.risk_score) {
      S.currentStep = 'done';
    } else if (appData.otp_verified) {
      S.currentStep = 'risk';
    } else if (appData.selfie_path) {
      S.currentStep = 'otp';
    } else if (appData.id_type) {
      S.currentStep = 'selfie';
    } else if (appData.phone) {
      S.currentStep = 'doc';
    } else if (appData.email) {
      S.currentStep = 'phone';
    } else if (appData.dob) {
      S.currentStep = 'email';
    } else if (appData.name) {
      S.currentStep = 'dob';
    } else {
      S.currentStep = 'name';
    }

    showScreen('onboarding');
    document.getElementById('chatMessages').innerHTML = '';
    document.getElementById('quickActions').innerHTML = '';

    if (appData.name)    document.getElementById('inf-name').textContent   = appData.name;
    if (appData.dob)     document.getElementById('inf-dob').textContent    = appData.dob;
    if (appData.email)   document.getElementById('inf-email').textContent  = appData.email;
    if (appData.id_type) document.getElementById('inf-idtype').textContent = appData.id_type;
    document.getElementById('inf-appid').textContent  = appId;
    document.getElementById('sessionId').textContent  = 'Session: ' + appId;

    await api('POST', '/api/session/resume', { application_id: appId });

    const replayMsgs = msgs.slice(-20);
    replayMsgs.forEach(m => {
      if (m.role === 'user') addUserMsg(m.content);
      else addAiMsgInstant(m.content);
    });

    addAiMsgInstant(`---\n👋 **Session resumed!** You're continuing from where you left off.\n\nApplication **${appId}** | Status: **${appData.status || 'In Progress'}**`);

    if (S.currentStep === 'done' || appData.status === 'Approved' || appData.status === 'Rejected') {
      if (appData.account_number) {
        S.accountNumber = appData.account_number;
        S.ifsc = appData.ifsc;
        S.riskLevel = appData.risk_level;
        setTimeout(showSuccessScreen, 800);
      } else {
        addAiMsgInstant(`Your application status is **${appData.status}**. Our team will contact you at ${appData.email || 'your registered email'}.`);
      }
    } else {
      await delay(500);
      continueFromStep(S.currentStep, appData);
    }

  } catch(e) {
    showToast('Failed to resume: ' + e.message, 'error');
  }
}

async function continueFromStep(step, appData) {
  switch(step) {
    case 'name':
      addAiMsg("Let's continue! What's your **full name** as on your ID?");
      enableInput('Your full name…');
      S.currentStep = 'name';
      break;
    case 'dob':
      addAiMsg(`Great to have you back, **${appData.name}**! I still need your **date of birth** in YYYY-MM-DD format.`);
      enableInput('YYYY-MM-DD');
      S.currentStep = 'dob';
      break;
    case 'email':
      addAiMsg("Please provide your **email address** to continue.");
      enableInput('your@email.com');
      S.currentStep = 'email';
      break;
    case 'phone':
      addAiMsg("What's your **mobile number** with country code?");
      enableInput('+91-XXXXXXXXXX');
      S.currentStep = 'phone';
      break;
    case 'doc':
      addAiMsg("Ready to continue! Please **upload your ID document** (Aadhaar / PAN / Passport).");
      S.currentStep = 'doc';
      setTimeout(showDocUpload, 400);
      break;
    case 'selfie':
      addAiMsg("Document verified! Now I need your **selfie** for biometric verification.");
      S.currentStep = 'selfie';
      setTimeout(showSelfieCapture, 400);
      break;
    case 'otp':
      addAiMsg("One last step! Please complete **OTP verification**.");
      S.currentStep = 'otp';
      await doOTP();
      break;
    case 'risk':
      addAiMsg("Running final **risk assessment**…");
      S.currentStep = 'busy';
      await runRiskEval();
      break;
  }
}

function showInfoModal(html) {
  let overlay = document.getElementById('info-modal-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'info-modal-overlay';
    overlay.style.cssText = `
      position: fixed; inset: 0; background: rgba(0,0,0,.82); backdrop-filter: blur(5px);
      z-index: 500; display: flex; align-items: center; justify-content: center;
    `;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) closeInfoModal(); });
    document.body.appendChild(overlay);
  }
  overlay.innerHTML = `
    <div style="background:#0D1117;border:1px solid rgba(201,168,76,.18);border-radius:18px;padding:28px;max-width:520px;width:93%;max-height:85vh;overflow-y:auto;animation:fadeUp .25s ease;">
      <button onclick="closeInfoModal()" style="float:right;background:rgba(255,255,255,.06);border:none;color:#8B949E;width:28px;height:28px;border-radius:6px;cursor:pointer;font-size:.9rem;">✕</button>
      ${html}
    </div>
  `;
  overlay.style.display = 'flex';
}

function closeInfoModal() {
  const el = document.getElementById('info-modal-overlay');
  if (el) el.style.display = 'none';
}

// ═══════════════════════════════════════════════════════════
// START — FIXED: removed step guard, await ensureAppId before initChat
// ═══════════════════════════════════════════════════════════
async function startOnboarding() {
  // Reset all state unconditionally
  S.userData = {};
  S.currentStep = 'idle';
  S.riskLevel = S.riskScore = null;
  S.accountNumber = S.ifsc = null;
  S.generatedOTP = null;
  S.timerStart = Date.now();
  S.appId = null;

  document.getElementById('chatMessages').innerHTML = '';
  document.getElementById('quickActions').innerHTML = '';
  ['inf-name','inf-dob','inf-email','inf-idtype'].forEach(id => {
    const el = document.getElementById(id); if (el) el.textContent = '—';
  });
  const riskEl = document.getElementById('inf-risk');
  if (riskEl) { riskEl.textContent = 'Evaluating'; riskEl.className = 'risk-badge pending'; }

  const statusEl = document.getElementById('apiStatus');
  if (statusEl) { statusEl.textContent = '● API Connected'; statusEl.style.color = 'var(--green)'; }

  showScreen('onboarding');

  // FIXED: await ensureAppId fully before doing anything else
  await ensureAppId();

  S.currentStep = 'name';
  enableInput('Ask me anything or enter your name…');

  // FIXED: call initChat directly, no setTimeout race condition
  initChat();
}

function initChat() {
  const user = S.currentUser;
  const greeting = user
    ? `👋 Welcome back, **${user.name}**! I'm **ARIA**, NexaBank's AI assistant.`
    : `👋 Welcome to **NexaBank**! I'm **ARIA**, your AI onboarding guide.`;

  addAiMsg(greeting);

  // FIXED: second message uses setTimeout but input is already enabled — no conflict
  setTimeout(() => {
    addAiMsg(
      "I'll help you open your account, but feel free to **ask me anything** — about documents needed, eligibility, how our accounts work, security, anything! " +
      "To begin, what's your **full name** as it appears on your government-issued ID?"
    );
  }, 1200);
}

// ═══════════════════════════════════════════════════════════
// SEND MESSAGE
// ═══════════════════════════════════════════════════════════
function sendMsg() {
  const inp = document.getElementById('chatInput');
  const text = inp.value.trim();
  if (!text) return;

  const textSteps = ['name', 'dob', 'email', 'phone'];
  if (!textSteps.includes(S.currentStep)) return;

  inp.value = ''; autoResize(inp);
  addUserMsg(text);
  setQuickActions([]);
  disableInput();
  setTimeout(() => handleStep(text), 200);
}

// ═══════════════════════════════════════════════════════════
// HANDLE STEP
// ═══════════════════════════════════════════════════════════
async function handleStep(text) {
  await ensureAppId();

  const appState = {
    app_id: S.appId,
    name:   S.userData.name,
    dob:    S.userData.dob,
    email:  S.userData.email,
    phone:  S.userData.phone,
    current_step: S.currentStep,
  };

  switch(S.currentStep) {

    case 'name': {
      const looksLikeName = text.trim().split(/\s+/).length >= 2 && !/[?]/.test(text) && !/\b(what|how|when|which|who|can|is|are|do|does|will|should|why)\b/i.test(text.trim().split(/\s+/)[0]);

      if (!looksLikeName) {
        const mEl = addAiMsg('<div class="connecting-anim"><div class="spinner"></div> Thinking…</div>');
        try {
          const res = await api('POST', '/api/chat/message', {
            application_id: S.appId, message: text, step: S.currentStep, app_state: appState, response_time: Date.now() - S.stepStartTime
          }).catch(() => {});
          updateBubble(mEl, res.reply || 'Let me get back to that. First, could you share your full name?');
        } catch(e) {
          updateBubble(mEl, handleLocalQuestion(text) + '<br><br>Now, what\'s your **full name** as on your ID?');
        }
        S.currentStep = 'name';
        enableInput('Ask me anything or enter your name…');
        return;
      }

      S.userData.name = text.trim();
      document.getElementById('inf-name').textContent = S.userData.name;
      logAI('Name: ' + S.userData.name);

      const mEl = addAiMsg('<div class="connecting-anim"><div class="spinner"></div></div>');
      try {
        const res = await api('POST', '/api/chat/message', {
          application_id: S.appId, message: text, step: S.currentStep, app_state: appState, response_time: Date.now() - S.stepStartTime
        }).catch(() => {});
        updateBubble(mEl, res.reply || `Nice to meet you, **${S.userData.name}**! What's your **date of birth**? (YYYY-MM-DD format, e.g., 1995-06-20)`);
      } catch(e) {
        updateBubble(mEl, `Nice to meet you, **${S.userData.name}**! What's your **date of birth**? (YYYY-MM-DD format)`);
      }
      S.currentStep = 'dob';
      enableInput('YYYY-MM-DD');
      S.stepStartTime = Date.now();
      break;
    }

    case 'dob': {
      if (/[?]/.test(text) || /\b(what|how|when|which|who|can|is|are|do|does|will|should|why)\b/i.test(text.trim().split(/\s+/)[0])) {
        const mEl = addAiMsg('<div class="connecting-anim"><div class="spinner"></div> Thinking…</div>');
        try {
          const res = await api('POST', '/api/chat/message', {
            application_id: S.appId, message: text, step: S.currentStep, app_state: appState, response_time: Date.now() - S.stepStartTime
          }).catch(() => {});
          updateBubble(mEl, res.reply || handleLocalQuestion(text) + '<br><br>When you\'re ready, please share your **date of birth** (YYYY-MM-DD).');
        } catch(e) {
          updateBubble(mEl, handleLocalQuestion(text) + '<br><br>When ready, what\'s your **date of birth**? (YYYY-MM-DD)');
        }
        enableInput('YYYY-MM-DD');
        S.stepStartTime = Date.now();
        return;
      }

      if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
        addAiMsg(`⚠️ Please use the format **YYYY-MM-DD** (e.g., 1995-06-20). What's your date of birth?`);
        S.currentStep = 'dob'; enableInput('YYYY-MM-DD'); return;
      }
      const age = Math.floor((Date.now() - new Date(text).getTime()) / (365.25 * 24 * 3600 * 1000));
      if (age < 18) {
        addAiMsg(`⛔ You must be **18 or older** to open an account. Your calculated age is **${age}**. Unfortunately we cannot proceed.`);
        S.currentStep = 'dob'; enableInput('YYYY-MM-DD'); return;
      }

      S.userData.dob = text;
      document.getElementById('inf-dob').textContent = text;
      logAI('DOB: ' + text + ' (age ' + age + ')');

      const mEl2 = addAiMsg('<div class="connecting-anim"><div class="spinner"></div></div>');
      try {
        const res = await api('POST', '/api/chat/message', {
          application_id: S.appId, message: text, step: S.currentStep, app_state: appState, response_time: Date.now() - S.stepStartTime
        }).catch(() => {});
        updateBubble(mEl2, res.reply || `✅ Age confirmed — **${age} years**. What's your **email address**?`);
      } catch(e) {
        updateBubble(mEl2, `✅ Age confirmed — **${age} years**. What's your **email address**?`);
      }
      S.currentStep = 'email'; enableInput('your@email.com');
      S.stepStartTime = Date.now();
      break;
    }

    case 'email': {
      if (/[?]/.test(text) || /\b(what|how|when|which|who|can|is|are|do|does|will|should|why)\b/i.test(text.trim().split(/\s+/)[0])) {
        const mEl = addAiMsg('<div class="connecting-anim"><div class="spinner"></div> Thinking…</div>');
        try {
          const res = await api('POST', '/api/chat/message', {
            application_id: S.appId, message: text, step: S.currentStep, app_state: appState, response_time: Date.now() - S.stepStartTime
          }).catch(() => {});
          updateBubble(mEl, res.reply || handleLocalQuestion(text));
        } catch(e) {
          updateBubble(mEl, handleLocalQuestion(text));
        }
        enableInput('your@email.com');
        S.stepStartTime = Date.now();
        return;
      }

      if (!/^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$/.test(text)) {
        addAiMsg("⚠️ That doesn't look like a valid email address. Could you double-check it?");
        S.currentStep = 'email'; enableInput('your@email.com'); return;
      }

      S.userData.email = text;
      document.getElementById('inf-email').textContent = text;

      const mEl3 = addAiMsg('<div class="connecting-anim"><div class="spinner"></div></div>');
      try {
        const res = await api('POST', '/api/chat/message', {
          application_id: S.appId, message: text, step: S.currentStep, app_state: appState, response_time: Date.now() - S.stepStartTime
        }).catch(() => {});
        updateBubble(mEl3, res.reply || `📧 Got it! What's your **mobile number** with country code?<br><span style="font-size:.8rem;color:var(--text2);">e.g., +91-9876543210</span>`);
      } catch(e) {
        updateBubble(mEl3, `📧 Got it! What's your **mobile number** with country code? (e.g., +91-9876543210)`);
      }
      S.currentStep = 'phone'; enableInput('+91-XXXXXXXXXX');
      S.stepStartTime = Date.now();
      break;
    }

    case 'phone': {
      S.userData.phone = text;
      S.currentStep = 'busy';
      disableInput();

      const saving = addAiMsg('<div class="connecting-anim"><div class="spinner"></div> Saving your details…</div>');
      try {
        api('POST', '/api/chat/message', {
          application_id: S.appId, message: text, step: 'phone', app_state: appState, response_time: Date.now() - S.stepStartTime
        }).catch(() => {});

        const idRes = await api('POST', '/api/identity/submit', {
          application_id: S.appId,
          name: S.userData.name, dob: S.userData.dob,
          email: S.userData.email, phone: text
        });

        markStep(1, 'done'); markVerify('vchk-id', 'done');
        logAI('Identity saved ✓');
        updateBubble(saving, `✅ **Identity verified and saved!**<br>Your details are secured with AES-256 encryption.`, 'ok');
        await delay(700);
        addAiMsg("Now I need your **ID document** for KYC verification. You can upload an Aadhaar Card, PAN Card, or Passport. Which do you have handy?");
        setQuickActions([
          { label: '📄 I have Aadhaar', val: 'Aadhaar ready' },
          { label: '🪪 I have PAN', val: 'PAN ready' },
          { label: '📘 I have Passport', val: 'Passport ready' },
        ]);
        S.currentStep = 'doc';
        setTimeout(showDocUpload, 600);
      } catch(e) {
        updateBubble(saving, `⚠️ ${e.message}. Please re-enter your name.`);
        S.currentStep = 'name'; enableInput('Your full name…');
      }
      S.stepStartTime = Date.now();
      break;
    }
  }
}

function handleLocalQuestion(text) {
  const t = text.toLowerCase();
  if (t.includes('document') || t.includes('which id') || t.includes('kyc'))
    return "For KYC, you can use **Aadhaar Card**, **PAN Card**, or **Passport**. Any one of these is sufficient.";
  if (t.includes('interest') || t.includes('rate'))
    return "NexaBank offers **3.5% – 4% p.a.** on savings accounts, credited quarterly.";
  if (t.includes('eligib') || t.includes('who can'))
    return "Any **Indian resident aged 18+** with a valid KYC document is eligible to open an account.";
  if (t.includes('safe') || t.includes('secur') || t.includes('privacy'))
    return "Your data is encrypted with **AES-256** and stored on RBI-compliant servers in India. We never share your information without consent.";
  if (t.includes('fee') || t.includes('charge') || t.includes('free'))
    return "Opening a NexaBank savings account is **completely free** with zero account maintenance charges for digital accounts.";
  if (t.includes('long') || t.includes('time') || t.includes('how long'))
    return "The entire KYC process takes about **3–5 minutes**. For Low risk applications, your account is active instantly!";
  return "That's a great question! Let me check on that for you.";
}

// ═══════════════════════════════════════════════════════════
// DOCUMENT UPLOAD
// ═══════════════════════════════════════════════════════════
function showDocUpload() {
  markStep(2, 'checking');
  const w = document.createElement('div');
  w.className = 'msg ai'; w.id = 'docWidget'; w.style.maxWidth = '100%';
  w.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div style="flex:1;">
      <select id="docTypeSelect" style="width:100%;background:var(--bg3);border:1px solid var(--border);color:var(--text);font-family:'Outfit',sans-serif;padding:9px 13px;border-radius:8px;margin-bottom:10px;outline:none;font-size:.85rem;">
        <option value="Aadhaar">Aadhaar Card</option>
        <option value="PAN">PAN Card</option>
        <option value="Passport">Passport</option>
      </select>
      <div class="upload-zone">
        <input type="file" accept="image/png,image/jpeg,image/jpg,.pdf" onchange="uploadRealDoc(this)">
        <div style="font-size:2rem;margin-bottom:8px;">📎</div>
        <div style="font-size:.85rem;color:var(--text2);">Click or drag to upload your ID document</div>
        <div style="font-size:.72rem;color:var(--text2);margin-top:4px;">PNG, JPG or PDF · Max 16MB</div>
      </div>
      <div style="margin-top:10px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap;">
        <button class="quick-btn" onclick="simulateDoc('Aadhaar')">📄 Simulate Aadhaar</button>
        <button class="quick-btn" onclick="simulateDoc('PAN')">🪪 Simulate PAN</button>
        <button class="quick-btn" onclick="simulateDoc('Passport')">📘 Simulate Passport</button>
      </div>
    </div>`;
  document.getElementById('chatMessages').appendChild(w);
  scrollChat();
}

async function uploadRealDoc(input) {
  const file = input.files[0];
  if (!file) return;
  const docType = document.getElementById('docTypeSelect')?.value || 'Aadhaar';
  document.getElementById('docWidget')?.remove();
  addUserMsg(`📎 Uploading: ${file.name} (${docType})`);
  const fd = new FormData();
  fd.append('file', file);
  fd.append('doc_type', docType);
  fd.append('application_id', S.appId);
  await processDoc(docType, fd);
}

async function simulateDoc(type) {
  document.getElementById('docWidget')?.remove();
  addUserMsg(`📄 Using simulated ${type} Card`);

  const canvas = document.createElement('canvas');
  canvas.width = 400; canvas.height = 240;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#f5f5f0'; ctx.fillRect(0, 0, 400, 240);
  ctx.fillStyle = '#1a1a2e'; ctx.fillRect(0, 0, 400, 50);
  ctx.fillStyle = '#ffffff'; ctx.font = 'bold 18px Arial'; ctx.fillText('GOVERNMENT OF INDIA', 15, 32);
  ctx.fillStyle = '#1a1a2e'; ctx.font = '14px Arial';
  const lines = {
    Aadhaar: [`Aadhaar Card`, `Name: ${S.userData.name || 'Demo Applicant'}`, `DOB: ${S.userData.dob || '01/01/1995'}`, `XXXX XXXX 1234`],
    PAN:     [`PAN Card`, `Name: ${(S.userData.name || 'DEMO APPLICANT').toUpperCase()}`, `DOB: ${S.userData.dob || '01/01/1995'}`, `ABCDE1234F`],
    Passport:[`Passport`, `Name: ${S.userData.name || 'Demo Applicant'}`, `DOB: ${S.userData.dob || '01/01/1995'}`, `P1234567`],
  };
  (lines[type] || lines.Aadhaar).forEach((l, i) => { ctx.fillText(l, 20, 80 + i * 32); });

  const blob = await new Promise(r => canvas.toBlob(r, 'image/png'));
  const fd = new FormData();
  fd.append('file', blob, `${type}_simulation.png`);
  fd.append('doc_type', type);
  fd.append('application_id', S.appId);
  await processDoc(type, fd);
}

async function processDoc(docType, fd) {
  document.getElementById('inf-idtype').textContent = docType;
  const mEl = addAiMsg(`<div><div class="connecting-anim"><div class="spinner"></div> Running OCR on ${docType}…</div><div class="ai-loading-bar"><div class="ai-loading-fill"></div></div></div>`);
  logAI('OCR: ' + docType);
  await delay(800);
  updateBubble(mEl, `<div><div class="connecting-anim"><div class="spinner"></div> Cross-referencing government database…</div><div class="ai-loading-bar"><div class="ai-loading-fill"></div></div></div>`);
  await delay(800);
  updateBubble(mEl, `<div><div class="connecting-anim"><div class="spinner"></div> Tamper detection & authenticity check…</div><div class="ai-loading-bar"><div class="ai-loading-fill"></div></div></div>`);

  try {
    const res = await apiForm('/api/documents/upload', fd);
    const ocr = res.ocr || {};
    const flags = res.tamper_flags || [];
    const conf = ocr.confidence || 0;
    const confColor = conf >= 70 ? 'var(--green)' : conf >= 40 ? '#f97316' : 'var(--red)';
    const ocrLine = (ocr.name || ocr.id_number) ? `<br>OCR → Name: ${ocr.name || '—'} | ID: ${ocr.id_number || '—'}` : '';
    const hashLine = `<br><span style="font-family:'DM Mono',monospace;font-size:.72rem;color:var(--text2);">SHA-256: ${(res.file_hash || '').substring(0, 22)}…</span>`;
    const flagLine = flags.length ? `<br><span style="color:#f97316;">⚠️ ${flags.join(', ')}</span>` : '';

    updateBubble(mEl,
      `✅ **${docType} processed!**<br>${res.file_size_kb}KB | OCR: <span style="color:${confColor}">${conf}%</span>${ocrLine}${flagLine}${hashLine}`,
      flags.length ? 'warn' : 'ok');

    markStep(2, 'done'); markVerify('vchk-doc', 'done');
    logAI(`Doc OK: conf ${conf}%`);
    await delay(800);
    addAiMsg("📸 Document looks good! Now I need a quick **selfie** for biometric face verification. This helps us confirm your identity against the document photo.");
    S.currentStep = 'selfie';
    setTimeout(showSelfieCapture, 400);
  } catch(e) {
    updateBubble(mEl, `⚠️ Upload failed: ${e.message}. Please try again.`);
    setTimeout(showDocUpload, 1000);
  }
}

// ═══════════════════════════════════════════════════════════
// SELFIE
// ═══════════════════════════════════════════════════════════
function showSelfieCapture() {
  markStep(3, 'checking');
  const w = document.createElement('div');
  w.className = 'msg ai'; w.id = 'selfieWidget'; w.style.maxWidth = '100%';
  w.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div style="flex:1;">
      <div class="selfie-zone">
        <input type="file" accept="image/*" capture="user" onchange="uploadSelfie(this)">
        <div style="font-size:3rem;">🤳</div>
        <div style="margin-top:8px;font-size:.85rem;color:var(--text2);">Click to take a selfie or upload a photo</div>
        <div style="font-size:.72rem;color:var(--text2);margin-top:4px;">Stored securely · Used only for KYC</div>
      </div>
      <div style="margin-top:10px;text-align:center;">
        <button class="quick-btn" onclick="simulateSelfie()">📸 Use Sample Selfie</button>
      </div>
    </div>`;
  document.getElementById('chatMessages').appendChild(w);
  scrollChat();
}

async function uploadSelfie(input) {
  const file = input.files[0];
  if (!file) return;
  document.getElementById('selfieWidget')?.remove();
  addUserMsg('📸 Selfie captured');
  const fd = new FormData();
  fd.append('selfie', file);
  fd.append('application_id', S.appId);
  await processSelfie(fd);
}

async function simulateSelfie() {
  document.getElementById('selfieWidget')?.remove();
  addUserMsg('📸 Sample selfie selected');

  const canvas = document.createElement('canvas');
  canvas.width = 300; canvas.height = 300;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#1a2744'; ctx.fillRect(0, 0, 300, 300);
  ctx.fillStyle = '#F5CBA7'; ctx.beginPath(); ctx.arc(150, 130, 70, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#2C3E50';
  ctx.beginPath(); ctx.arc(125, 115, 10, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(175, 115, 10, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = '#C9A84C'; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(150, 135, 30, 0, Math.PI); ctx.stroke();
  ctx.fillStyle = '#2C3E50'; ctx.beginPath(); ctx.arc(150, 72, 48, Math.PI, 0); ctx.fill();
  ctx.fillStyle = '#C9A84C'; ctx.beginPath();
  ctx.moveTo(80, 300); ctx.lineTo(80, 230); ctx.lineTo(150, 210); ctx.lineTo(220, 230); ctx.lineTo(220, 300); ctx.fill();

  const blob = await new Promise(r => canvas.toBlob(r, 'image/png'));
  const fd = new FormData();
  fd.append('selfie', blob, 'selfie.png');
  fd.append('application_id', S.appId);
  await processSelfie(fd);
}

async function processSelfie(fd) {
  const mEl = addAiMsg('<div class="connecting-anim"><div class="spinner"></div> Uploading selfie securely…</div>');
  logAI('Biometric upload started');
  await delay(700);
  updateBubble(mEl, '<div class="connecting-anim"><div class="spinner"></div> Running facial recognition…</div>');
  await delay(1000);
  updateBubble(mEl, '<div class="connecting-anim"><div class="spinner"></div> Liveness detection…</div>');

  try {
    const res = await apiForm('/api/biometric/selfie', fd);
    const score = res.face_score;
    const sc = score >= 90 ? 'var(--green)' : score >= 75 ? '#f97316' : 'var(--red)';
    updateBubble(mEl,
      `✅ **Selfie verified!**<br>Face match: <span style="color:${sc}"><strong>${score}%</strong></span> (${res.face_status})<br>Liveness: <span style="color:var(--green)">✓ Confirmed</span>`, 'ok');

    markStep(3, 'done'); markVerify('vchk-bio', 'done');
    logAI(`Face match: ${score}%`);
    await delay(800);
    await doOTP();
  } catch(e) {
    updateBubble(mEl, `⚠️ Selfie failed: ${e.message}`);
    setTimeout(showSelfieCapture, 1000);
  }
}

// ═══════════════════════════════════════════════════════════
// OTP
// ═══════════════════════════════════════════════════════════
// async function doOTP() {
//   markStep(4, 'checking');
//   S.currentStep = 'busy';
//   await ensureAppId();

//   S.generatedOTP = String(Math.floor(100000 + Math.random() * 900000));
//   const hash = await sha256(S.generatedOTP);

//   try {
//     await api('POST', '/api/otp/store', { application_id: S.appId, otp_hash: hash });
//     logAI('OTP stored ✓');
//   } catch(e) {
//     logAI('OTP store note: ' + e.message);
//   }

//   const otpDiv = document.createElement('div');
//   otpDiv.className = 'msg ai'; otpDiv.style.maxWidth = '100%';
//   otpDiv.innerHTML = `
//     <div class="msg-avatar">🤖</div>
//     <div class="msg-bubble gold">
//       📱 OTP sent to <strong>${S.userData.email || 'your registered email'}</strong>
//       <div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center;margin-top:10px;">
//         <div style="font-size:.72rem;color:var(--text2);margin-bottom:8px;">YOUR OTP (shown for demo)</div>
//         <div style="font-family:'DM Mono',monospace;font-size:2.2rem;letter-spacing:10px;color:var(--gold);font-weight:700;">${S.generatedOTP}</div>
//         <div style="font-size:.7rem;color:var(--text2);margin-top:8px;">Valid for 5 minutes</div>
//       </div>
//     </div>`;
//   document.getElementById('chatMessages').appendChild(otpDiv);
//   scrollChat();

//   await delay(500);
//   addAiMsg("Please enter the 6-digit OTP shown above to verify your phone and email.");
//   S.currentStep = 'otp';
//   setTimeout(showOTPBoxes, 400);
// }

async function doOTP() {
  markStep(4, 'checking');
  S.currentStep = 'busy';
  await ensureAppId();

  S.generatedOTP = String(Math.floor(100000 + Math.random() * 900000));
  const hash = await sha256(S.generatedOTP);

  try {
    await api('POST', '/api/otp/store', { application_id: S.appId, otp_hash: hash });
    logAI('OTP stored ✓');
  } catch(e) {
    logAI('OTP store note: ' + e.message);
  }

  const otpDiv = document.createElement('div');
  otpDiv.className = 'msg ai';
  otpDiv.style.maxWidth = '100%';
  otpDiv.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div class="msg-bubble gold">
      📱 OTP sent to <strong>${S.userData.email || 'your registered email'}</strong>
      <div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center;margin-top:10px;">
        <div style="font-size:.72rem;color:var(--text2);margin-bottom:8px;">YOUR OTP (shown for demo)</div>
        <div style="font-family:'DM Mono',monospace;font-size:2.2rem;letter-spacing:10px;color:var(--gold);font-weight:700;">${S.generatedOTP}</div>
        <div style="font-size:.7rem;color:var(--text2);margin-top:8px;">Valid for 5 minutes</div>
      </div>
    </div>`;
  document.getElementById('chatMessages').appendChild(otpDiv);
  scrollChat();

  await delay(600);

  // FIXED: set step to 'otp' BEFORE showing boxes so input state is correct
  S.currentStep = 'otp';

  addAiMsg("Please enter the 6-digit OTP shown above to verify your contact details.");

  // FIXED: slight delay so message renders before boxes appear
  await delay(800);
  showOTPBoxes();
}

function showOTPBoxes() {
  document.getElementById('otpWidget')?.remove();
  const w = document.createElement('div');
  w.className = 'msg ai'; w.id = 'otpWidget'; w.style.maxWidth = '100%';
  w.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div style="flex:1;">
      <div style="font-size:.85rem;margin-bottom:10px;color:var(--text2);">Enter your 6-digit OTP:</div>
      <div class="otp-boxes">
        ${[1,2,3,4,5,6].map(i => `<input class="otp-box" id="otp${i}" type="number" inputmode="numeric" min="0" max="9" oninput="otpNext(this,${i})" onkeydown="otpBack(event,${i})">`).join('')}
      </div>
      <div style="text-align:center;margin-top:14px;">
        <button class="quick-btn" onclick="verifyOTP()" style="padding:10px 30px;">Verify OTP ✓</button>
      </div>
    </div>`;
  document.getElementById('chatMessages').appendChild(w);
  scrollChat();
  setTimeout(() => { const el = document.getElementById('otp1'); if (el) el.focus(); }, 200);
}

function otpNext(el, i) {
  el.value = el.value.toString().slice(-1);
  if (el.value && i < 6) document.getElementById('otp' + (i + 1))?.focus();
  if (i === 6 && el.value) setTimeout(verifyOTP, 300);
}

function otpBack(e, i) {
  if (e.key === 'Backspace' && !e.target.value && i > 1) document.getElementById('otp' + (i - 1))?.focus();
}

// async function verifyOTP() {
//   const digits = [1,2,3,4,5,6].map(i => document.getElementById('otp' + i)?.value || '').join('');
//   if (digits.length !== 6 || !/^\d{6}$/.test(digits)) {
//     showToast('Please enter all 6 digits', 'error'); return;
//   }

//   await ensureAppId();
//   document.getElementById('otpWidget')?.remove();
//   addUserMsg('OTP entered: ••••••');
//   S.currentStep = 'busy';
//   disableInput();

//   const mEl = addAiMsg('<div class="connecting-anim"><div class="spinner"></div> Verifying OTP…</div>');

//   try {
//     const hash = await sha256(digits);
//     const res = await api('POST', '/api/otp/verify', { application_id: S.appId, otp_hash: hash });

//     if (res.verified || res.success) {
//       updateBubble(mEl, '✅ **OTP verified!** Your identity is confirmed.', 'ok');
//       markStep(4, 'done'); markVerify('vchk-otp', 'done');
//       logAI('OTP verified ✓');
//       await delay(800);
//       await runRiskEval();
//     } else {
//       throw new Error('OTP verification failed');
//     }
//   } catch(e) {
//     updateBubble(mEl, `❌ ${e.message || 'Incorrect OTP. Please try again.'}`);
//     S.currentStep = 'otp';
//     await delay(800);
//     setTimeout(showOTPBoxes, 100);
//   }
// }

async function verifyOTP() {
  const digits = [1,2,3,4,5,6].map(i => document.getElementById('otp' + i)?.value || '').join('');
  if (digits.length !== 6 || !/^\d{6}$/.test(digits)) {
    showToast('Please enter all 6 digits', 'error'); return;
  }

  await ensureAppId();
  document.getElementById('otpWidget')?.remove();
  addUserMsg('OTP entered: ••••••');

  // FIXED: set busy only after removing widget
  S.currentStep = 'busy';
  disableInput();

  const mEl = addAiMsg('<div class="connecting-anim"><div class="spinner"></div> Verifying OTP…</div>');

  try {
    const hash = await sha256(digits);
    const res = await api('POST', '/api/otp/verify', {
      application_id: S.appId,
      otp_hash: hash
    });

    if (res.verified || res.success) {
      updateBubble(mEl, '✅ **OTP verified!** Your identity is confirmed.', 'ok');
      markStep(4, 'done');
      markVerify('vchk-otp', 'done');
      logAI('OTP verified ✓');

      // FIXED: keep busy during risk eval, don't re-enable input
      await delay(800);
      await runRiskEval();
    } else {
      throw new Error('OTP verification failed');
    }
  } catch(e) {
    updateBubble(mEl, `❌ ${e.message || 'Incorrect OTP. Please try again.'}`);
    // FIXED: reset step properly so OTP boxes reappear
    S.currentStep = 'otp';
    await delay(800);
    showOTPBoxes();
  }
}

// ═══════════════════════════════════════════════════════════
// RISK EVALUATION
// ═══════════════════════════════════════════════════════════
async function runRiskEval() {
  markStep(5, 'checking'); markVerify('vchk-risk', 'checking');
  const checks = [
    'Analyzing document integrity…',
    'AML watchlist screening…',
    'Cross-referencing CIBIL data…',
    'Computing biometric confidence…',
    'Generating composite risk score…',
  ];
  const mEl = addAiMsg(`<div>
    <div class="connecting-anim"><div class="spinner"></div>${checks[0]}</div>
    <div class="ai-loading-bar"><div class="ai-loading-fill"></div></div>
    <div style="color:var(--text2);font-size:.75rem;margin-top:6px;">0/${checks.length} checks</div>
  </div>`);
  logAI('Risk engine: 5 factors');

  for (let i = 1; i < checks.length; i++) {
    await delay(800);
    updateBubble(mEl, `<div>
      <div class="connecting-anim"><div class="spinner"></div>${checks[i]}</div>
      <div class="ai-loading-bar"><div class="ai-loading-fill"></div></div>
      <div style="color:var(--text2);font-size:.75rem;margin-top:6px;">${i}/${checks.length} checks</div>
    </div>`);
  }
  await delay(900);

  try {
    const res = await api('POST', '/api/risk/evaluate', { application_id: S.appId });
    S.riskLevel = res.risk_level;
    S.riskScore = res.risk_score;
    S.accountNumber = res.account_number;
    S.ifsc = res.ifsc;

    const C  = { Low: 'var(--green)', Medium: '#f97316', High: 'var(--red)' };
    const E  = { Low: '🟢', Medium: '🟠', High: '🔴' };
    const CL = { Low: 'ok', Medium: 'warn', High: 'danger' };
    const c  = C[res.risk_level];

    const sigRows = (res.signals || []).map(s => `
      <div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:.78rem;">
        <span style="${s.weight < 0 ? 'color:var(--red)' : 'color:var(--text2)'};font-family:'DM Mono',monospace;min-width:36px;">${s.weight > 0 ? '+' + s.weight : s.weight || '0'}</span>
        <span style="color:var(--text2);min-width:110px;">${s.factor}</span>
        <span>${s.note}</span>
      </div>`).join('');

    updateBubble(mEl, `
      <div style="color:${c};font-weight:600;font-size:.95rem;margin-bottom:8px;">${E[res.risk_level]} Risk: <strong>${res.risk_level}</strong></div>
      <div style="font-size:.83rem;color:var(--text2);margin-bottom:10px;">${res.risk_reason}</div>
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
        <div style="flex:1;height:7px;background:rgba(255,255,255,.1);border-radius:4px;overflow:hidden;">
          <div style="height:100%;width:${res.risk_score}%;background:${c};border-radius:4px;"></div>
        </div>
        <span style="font-family:'DM Mono',monospace;font-size:.8rem;color:${c};">${res.risk_score}/100</span>
      </div>
      <div style="font-size:.75rem;border:1px solid rgba(255,255,255,.06);border-radius:8px;overflow:hidden;">
        <div style="padding:8px 12px;background:rgba(255,255,255,.02);font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--gold);">Signal Breakdown</div>
        <div style="padding:8px 12px;">${sigRows}</div>
      </div>`, CL[res.risk_level]);

    markVerify('vchk-risk', 'done'); markStep(5, 'done');
    const rEl = document.getElementById('inf-risk');
    if (rEl) { rEl.textContent = res.risk_level; rEl.className = 'risk-badge ' + (res.risk_level === 'Low' ? 'low' : res.risk_level === 'Medium' ? 'med' : 'high'); }
    logAI(`Risk: ${res.risk_level} (${res.risk_score}/100)`);

    await delay(1400);
    if (res.risk_level === 'High') {
      addAiMsg(`⚠️ Your application has been **escalated for manual review** by our compliance team. You'll receive an update within 2–3 business days at **${S.userData.email || 'your registered email'}**.<br><br>Reference ID: <strong>${S.appId}</strong>`);
    } else {
      addAiMsg(`🎉 Congratulations, **${S.userData.name || 'Applicant'}**! Your account has been created successfully. Welcome to NexaBank!`, 0, 'gold');
    }
    await delay(1800);
    showFinalScreen();
  } catch(e) {
    updateBubble(mEl, `⚠️ Risk evaluation failed: ${e.message}`);
  }
}

function showFinalScreen() {
  const title = document.getElementById('sc-title');
  const subtitle = document.getElementById('sc-subtitle');
  const kyc = document.getElementById('sc-kyc');
  const rEl = document.getElementById('sc-risk');

  document.getElementById('sc-appid').textContent = S.appId;
  document.getElementById('sc-name').textContent  = S.userData.name || '—';
  document.getElementById('sc-ifsc').textContent  = S.ifsc || 'NXBA0001234';

  // 🎯 RISK BADGE
  if (rEl) {
    rEl.textContent = S.riskLevel || 'Low';
    rEl.className = 'risk-badge ' + (
      S.riskLevel === 'High' ? 'high' :
      S.riskLevel === 'Medium' ? 'med' : 'low'
    );
  }

  // 🎯 CORE LOGIC
  if (S.riskLevel === "Low") {

    title.textContent = "🎉 Welcome to NexaBank!";
    subtitle.textContent = "Your account has been created successfully.";

    document.getElementById('sc-acno').textContent = S.accountNumber || '—';
    document.getElementById('sc-date').textContent = new Date().toLocaleDateString('en-IN');

    kyc.innerHTML = "✓ Verified";
    kyc.style.color = "var(--green)";

    launchConfetti(); // ✅ ONLY here
  }

  else if (S.riskLevel === "Medium") {

    title.textContent = "⏳ Verification in Progress";
    subtitle.textContent = "Your application is under manual review.";

    document.getElementById('sc-acno').textContent = "—";
    document.getElementById('sc-date').textContent = "—";

    kyc.innerHTML = "⏳ Pending Review";
    kyc.style.color = "#f97316";
  }

  else {

    title.textContent = "🚫 Verification Failed";
    subtitle.textContent = "High-risk signals detected. Application escalated.";

    document.getElementById('sc-acno').textContent = "—";
    document.getElementById('sc-date').textContent = "—";

    kyc.innerHTML = "❌ Failed";
    kyc.style.color = "var(--red)";
  }

  showScreen('success-screen');
}

function showSuccessScreen() {
  document.getElementById('sc-appid').textContent = S.appId;
  document.getElementById('sc-name').textContent  = S.userData.name || '—';
  document.getElementById('sc-acno').textContent  = S.accountNumber || '—';
  document.getElementById('sc-ifsc').textContent  = S.ifsc || 'NXBA0001234';
  document.getElementById('sc-date').textContent  = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
  const rEl = document.getElementById('sc-risk');
  if (rEl) { rEl.textContent = S.riskLevel || 'Low'; rEl.className = 'risk-badge ' + (S.riskLevel === 'High' ? 'high' : S.riskLevel === 'Medium' ? 'med' : 'low'); }
  showScreen('success-screen');
  launchConfetti();
}



// ═══════════════════════════════════════════════════════════
// ENSURE APP ID
// ═══════════════════════════════════════════════════════════
async function ensureAppId() {
  if (S.appId && !S.appId.startsWith('NXB-OFFLINE')) return S.appId;

  let retries = 3;
  while (retries > 0) {
    try {
      const res = await fetch('/api/session/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include'
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Session start failed');
      S.appId = data.application_id;
      const sessionEl = document.getElementById('sessionId');
      if (sessionEl) sessionEl.textContent = 'Session: ' + S.appId;
      const appIdEl = document.getElementById('inf-appid');
      if (appIdEl) appIdEl.textContent = S.appId;
      logAI('Session created ✓');
      return S.appId;
    } catch(e) {
      retries--;
      console.warn(`ensureAppId failed, retries left: ${retries}`, e.message);
      if (retries > 0) await delay(600);
    }
  }

  // Only fall back to offline if all retries exhausted
  S.appId = 'NXB-OFFLINE-' + Math.random().toString(36).substr(2,6).toUpperCase();
  const sessionEl = document.getElementById('sessionId');
  if (sessionEl) sessionEl.textContent = 'Offline: ' + S.appId;
  const statusEl = document.getElementById('apiStatus');
  if (statusEl) { statusEl.textContent = '● Offline'; statusEl.style.color = '#f97316'; }
  return S.appId;
}

// ═══════════════════════════════════════════════════════════
// CHAT HELPERS
// ═══════════════════════════════════════════════════════════
function addAiMsg(html, delay2 = 0, cls = '') {
  const chat = document.getElementById('chatMessages');
  const msgDiv = document.createElement('div');
  msgDiv.className = 'msg ai';
  msgDiv.innerHTML = `<div class="msg-avatar">🤖</div><div class="msg-bubble ${cls}"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>`;

  let autoTimeout = null;
  const insert = () => {
    chat.appendChild(msgDiv); scrollChat();
    autoTimeout = setTimeout(() => {
      const b = msgDiv.querySelector('.msg-bubble');
      if (b) { b.className = `msg-bubble ${cls}`; b.innerHTML = renderMarkdown(html); }
      scrollChat();
    }, 650);
  };
  msgDiv._cancelAuto = () => { if (autoTimeout) { clearTimeout(autoTimeout); autoTimeout = null; } };
  if (delay2) setTimeout(insert, delay2); else insert();
  return msgDiv;
}

function addAiMsgInstant(html, cls = '') {
  const chat = document.getElementById('chatMessages');
  const msgDiv = document.createElement('div');
  msgDiv.className = 'msg ai';
  msgDiv.innerHTML = `<div class="msg-avatar">🤖</div><div class="msg-bubble ${cls}">${renderMarkdown(html)}</div>`;
  chat.appendChild(msgDiv);
  scrollChat();
  return msgDiv;
}

function renderMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code style="font-family:\'DM Mono\',monospace;background:rgba(255,255,255,.07);padding:1px 5px;border-radius:4px;">$1</code>')
    .replace(/---\n/g, '<hr style="border-color:rgba(255,255,255,.08);margin:10px 0;">')
    .replace(/\n/g, '<br>');
}

function addUserMsg(text) {
  const chat = document.getElementById('chatMessages');
  const d = document.createElement('div');
  d.className = 'msg user';
  d.innerHTML = `<div class="msg-avatar" style="background:var(--bg3);border:1px solid var(--border);">👤</div><div class="msg-bubble">${text}</div>`;
  chat.appendChild(d); scrollChat();
}

function updateBubble(el, html, cls = '') {
  if (el && typeof el._cancelAuto === 'function') el._cancelAuto();
  const b = el?.querySelector('.msg-bubble');
  if (b) { b.innerHTML = renderMarkdown(html); if (cls) b.className = 'msg-bubble ' + cls; }
}

function scrollChat() {
  const el = document.getElementById('chatMessages');
  if (el) setTimeout(() => el.scrollTop = el.scrollHeight, 100);
}

function enableInput(ph = 'Ask me anything…') {
  const inp = document.getElementById('chatInput');
  const btn = document.getElementById('sendBtn');
  if (inp) { inp.disabled = false; inp.placeholder = ph; }
  if (btn) btn.disabled = false;
  if (inp) inp.focus();
}

function disableInput() {
  const inp = document.getElementById('chatInput');
  const btn = document.getElementById('sendBtn');
  if (inp) { inp.disabled = true; inp.placeholder = 'Please wait…'; }
  if (btn) btn.disabled = true;
}

function setQuickActions(actions) {
  const el = document.getElementById('quickActions');
  if (!el) return;
  el.innerHTML = '';
  (actions || []).forEach(a => {
    const btn = document.createElement('button');
    btn.className = 'quick-btn'; btn.textContent = a.label;
    btn.onclick = () => { const inp = document.getElementById('chatInput'); if (inp) inp.value = a.val; sendMsg(); };
    el.appendChild(btn);
  });
}

function handleKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); } }
function autoResize(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 120) + 'px'; }

// ═══════════════════════════════════════════════════════════
// STEP / VERIFY HELPERS
// ═══════════════════════════════════════════════════════════
function markStep(num, state) {
  const el = document.getElementById('step-' + num);
  if (!el) return;
  el.className = 'step-item ' + (state === 'done' ? 'done' : 'active');
  const c = el.querySelector('.step-circle');
  if (state === 'done') {
    if (c) c.textContent = '✓';
    const line = document.getElementById('line-' + (num - 1));
    if (line) line.classList.add('done');
    const next = document.getElementById('step-' + (num + 1));
    if (next && !next.classList.contains('done')) next.classList.add('active');
  }
}

function markVerify(id, status) {
  const el = document.getElementById(id);
  if (!el) return;
  const icons = { done: '✓', fail: '✗', checking: '⟳' };
  if (icons[status]) el.textContent = icons[status];
  el.className = 'verify-icon ' + status;
}

function logAI(msg) {
  const log = document.getElementById('aiLog');
  if (!log) return;
  const t = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  const item = document.createElement('div');
  item.className = 'timeline-item';
  item.innerHTML = `<span class="timeline-time">${t}</span><span>${msg}</span>`;
  log.appendChild(item);
  log.scrollTop = log.scrollHeight;
}

// ═══════════════════════════════════════════════════════════
// UTILS
// ═══════════════════════════════════════════════════════════
function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function showToast(msg, type = 'success') {
  const t = document.createElement('div');
  t.className = 'api-toast ' + type;
  t.innerHTML = renderMarkdown(msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

function launchConfetti() {
  const colors = ['#C9A84C', '#E8C97A', '#10B981', '#3B82F6', '#F59E0B', '#EF4444'];
  for (let i = 0; i < 80; i++) setTimeout(() => {
    const el = document.createElement('div'); el.className = 'confetti-piece';
    el.style.cssText = `left:${Math.random() * 100}vw;top:-20px;background:${colors[Math.floor(Math.random() * colors.length)]};animation-duration:${2 + Math.random() * 2}s;animation-delay:${Math.random() * .5}s;width:${6 + Math.random() * 8}px;height:${6 + Math.random() * 8}px;border-radius:${Math.random() > .5 ? '50%' : '2px'};`;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4500);
  }, i * 40);
}

// ═══════════════════════════════════════════════════════════
// ADMIN MODAL
// ═══════════════════════════════════════════════════════════
async function openReviewModal(appId) {
  S.selectedAppId = appId;
  try {
    const res = await api('GET', `/api/admin/application/${appId}`);
    const app = res.application;
    const rCls = app.risk_level === 'Low' ? 'low' : app.risk_level === 'Medium' ? 'med' : 'high';

    document.getElementById('modalContent').innerHTML = `
      <div class="info-row"><span class="info-key">Applicant</span><span class="info-val">${app.name || '—'}</span></div>
      <div class="info-row"><span class="info-key">App ID</span><span class="mono" style="font-size:.78rem;">${app.id}</span></div>
      <div class="info-row"><span class="info-key">DOB</span><span class="info-val">${app.dob || '—'}</span></div>
      <div class="info-row"><span class="info-key">Email</span><span class="info-val">${app.email || '—'}</span></div>
      <div class="info-row"><span class="info-key">Risk</span>${app.risk_level ? `<span class="risk-badge ${rCls}">${app.risk_level} (${app.risk_score}/100)</span>` : '—'}</div>
      <div class="info-row"><span class="info-key">Status</span><strong>${app.status || '—'}</strong></div>
      ${app.account_number ? `<div class="info-row"><span class="info-key">Account</span><span class="mono" style="color:var(--gold);">${app.account_number}</span></div>` : ''}
      <div style="background:rgba(201,168,76,.06);border:1px solid rgba(201,168,76,.12);border-radius:8px;padding:12px;margin:12px 0;font-size:.82rem;">
        <div style="color:var(--gold);font-size:.7rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">🤖 AI Risk Reasoning</div>
        ${app.risk_reason || 'Not evaluated'}
      </div>
      <textarea id="adminNotes" placeholder="Decision notes…" style="width:100%;background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:10px;font-family:'Outfit',sans-serif;font-size:.85rem;outline:none;resize:vertical;min-height:60px;margin-top:12px;"></textarea>`;

    document.getElementById('reviewModal').classList.add('open');
  } catch(e) { showToast('Failed to load: ' + e.message, 'error'); }
}

async function submitDecision(decision) {
  const notes = document.getElementById('adminNotes')?.value || '';
  try {
    await api('POST', '/api/admin/decision', { application_id: S.selectedAppId, decision, notes });
    closeModal();
    showToast(`✅ ${decision} recorded`, 'success');
  } catch(e) {}
}

function closeModal() {
  const el = document.getElementById('reviewModal');
  if (el) el.classList.remove('open');
}

// ═══════════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  checkUserSession();
});