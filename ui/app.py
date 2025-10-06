from __future__ import annotations
import os
import time
import requests
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------- page & config ----------------------------
st.set_page_config(page_title="Notes Copilot", page_icon="📚", layout="wide")

API_URL = os.getenv("API_URL", st.secrets.get("API_URL", "http://localhost:8000")).rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", st.secrets.get("SUPABASE_URL", "")).rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", st.secrets.get("SUPABASE_ANON_KEY", ""))

# ---------------------------- state ----------------------------
ss = st.session_state
ss.setdefault("auth", {})
ss.setdefault("library", [])
ss.setdefault("last_answer", None)
ss.setdefault("uploading", False)
ss.setdefault("uploader_key", 0)
ss.setdefault("q_input", "")

def _rerun():
    (getattr(st, "rerun", None) or getattr(st, "experimental_rerun", lambda: None))()

# ---------------------------- styles ----------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

:root{
  --primary:#4C1D95;--primary-light:#6D28D9;--primary-dark:#3B0764;--secondary:#0891B2;
  --success:#10B981;--danger:#EF4444;--bg-main:#0A0A0F;--bg-secondary:#13131A;
  --bg-card:rgba(19,19,26,.6);--border-color:rgba(139,92,246,.12);
  --text-primary:#E5E7EB;--text-secondary:#9CA3AF;--text-muted:#6B7280;
  --shadow-sm:0 1px 2px 0 rgb(0 0 0 / .3);--shadow-md:0 4px 6px -1px rgb(0 0 0 / .4);
  --shadow-lg:0 10px 15px -3px rgb(0 0 0 / .5);--shadow-xl:0 20px 25px -5px rgb(0 0 0 / .6);
  --glow-primary:0 0 20px rgba(109,40,217,.3);
}

*{font-family:'Plus Jakarta Sans',system-ui,-apple-system,sans-serif}
.stApp{background:linear-gradient(135deg,var(--bg-main) 0%,#0D0D15 50%,#0A0A12 100%);color:var(--text-primary);min-height:100vh}
.block-container{padding-top:2rem;padding-bottom:2rem;max-width:1400px}

/* hero */
.hero-section{background:linear-gradient(135deg,var(--primary-dark) 0%,var(--primary) 50%,var(--primary-light) 100%);
  border-radius:20px;padding:2.5rem;margin:1rem 0 2rem;box-shadow:var(--shadow-xl),var(--glow-primary);
  position:relative;overflow:hidden;border:1px solid rgba(109,40,217,.25);transition:.3s}
.hero-section:hover{transform:translateY(-2px);box-shadow:var(--shadow-xl),0 0 30px rgba(109,40,217,.5)}
.hero-section::before{content:'';position:absolute;top:-50%;right:-10%;width:60%;height:200%;
  background:radial-gradient(circle,rgba(255,255,255,.08) 0%,transparent 70%)}
.hero-section::after{content:'';position:absolute;left:0;right:0;bottom:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.2),transparent)}
.hero-title{font-size:2.25rem;font-weight:800;margin:0 0 .75rem;background:linear-gradient(to right,#fff,#DDD6FE,#E9D5FF);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;letter-spacing:-.02em}
.hero-subtitle{font-size:1.05rem;color:rgba(255,255,255,.85);font-weight:400;margin:0;max-width:600px;line-height:1.6}

/* cards */
.main-card{background:var(--bg-card);backdrop-filter:blur(20px);border:1px solid var(--border-color);
  border-radius:18px;padding:2rem;margin-bottom:1.5rem;box-shadow:var(--shadow-lg);transition:.3s;position:relative}
.main-card::before{content:'';position:absolute;inset:0;border-radius:18px;padding:1px;
  background:linear-gradient(135deg,rgba(109,40,217,.1),transparent);
  -webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none}
.main-card:hover{transform:translateY(-3px);box-shadow:var(--shadow-xl),var(--glow-primary);border-color:rgba(109,40,217,.3)}
.card-title{font-size:1.4rem;font-weight:700;margin-bottom:.5rem;color:var(--text-primary);letter-spacing:-.01em}
.card-subtitle{color:var(--text-secondary);margin-bottom:1.5rem;font-size:.92rem}

/* sidebar */
section[data-testid="stSidebar"]{background:var(--bg-secondary);border-right:1px solid var(--border-color)}
section[data-testid="stSidebar"] .block-container{padding-top:1.5rem}
.sidebar-section{background:var(--bg-card);border:1px solid var(--border-color);border-radius:16px;padding:1.5rem;margin-bottom:1.5rem;backdrop-filter:blur(10px)}
.sidebar-title{font-size:1.15rem;font-weight:600;margin-bottom:1rem;color:var(--text-primary);letter-spacing:-.01em}

/* doc items */
.doc-item{background:rgba(76,29,149,.08);border:1px solid rgba(109,40,217,.15);border-radius:12px;padding:1rem;margin-bottom:.75rem;transition:.2s}
.doc-item:hover{background:rgba(76,29,149,.12);transform:translateX(4px);border-color:rgba(109,40,217,.25)}
.doc-name{font-weight:600;color:var(--text-primary);margin-bottom:.25rem;font-size:.95rem}
.doc-meta{color:var(--text-muted);font-size:.85rem}

/* buttons */
.stButton > button{background:linear-gradient(135deg,var(--primary) 0%,var(--primary-light) 100%);color:#fff;border:none;border-radius:12px;
  padding:.75rem 1.5rem;font-weight:600;font-size:.95rem;transition:.2s;box-shadow:var(--shadow-md),var(--glow-primary);letter-spacing:.025em;position:relative;overflow:hidden}
.stButton > button::before{content:'';position:absolute;top:0;left:-100%;width:100%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.2),transparent);transition:left .5s}
.stButton > button:hover::before{left:100%}
.stButton > button:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg),0 0 25px rgba(109,40,217,.5)}
.stButton > button:active{transform:translateY(0)}
.stButton > button:disabled{opacity:.5;cursor:not-allowed;transform:none}
.stButton > button[kind="primary"]{background:linear-gradient(135deg,var(--primary) 0%,var(--primary-light) 100%);
  box-shadow:var(--shadow-md),0 0 20px rgba(109,40,217,.3)}
.stButton > button[kind="primary"]:hover{box-shadow:var(--shadow-lg),0 0 25px rgba(109,40,217,.5)}

/* inputs */
.stTextInput input,.stTextArea textarea{background:rgba(10,10,15,.8);border:2px solid var(--border-color);border-radius:12px;color:var(--text-primary);padding:.75rem 1rem;transition:.2s;outline:none;box-shadow:none}
.stTextInput input:focus,.stTextArea textarea:focus{border-color:var(--primary-light);box-shadow:none;background:rgba(10,10,15,.95);outline:none}
.stTextInput input:focus-visible,.stTextArea textarea:focus-visible{outline:none;border-color:var(--primary-light);box-shadow:none}
.stTextInput input:active,.stTextArea textarea:active{outline:none;border-color:var(--primary-light);box-shadow:none}
/* ADDED: Remove browser's default red outline for invalid fields */
.stTextInput input:invalid, .stTextArea textarea:invalid {box-shadow: none;}
input:focus, textarea:focus, [contenteditable]:focus{outline:none!important;box-shadow:none!important}

/* uploader */
.stFileUploader{border:2px dashed var(--border-color);border-radius:12px;background:rgba(76,29,149,.05);transition:.2s}
.stFileUploader:hover{border-color:var(--primary-light);background:rgba(76,29,149,.1)}

/* answer box */
.answer-box{background:linear-gradient(135deg,rgba(76,29,149,.12),rgba(6,182,212,.08));border-left:3px solid var(--primary-light);
  border-radius:12px;padding:1.25rem;margin-top:1.5rem;animation:slideIn .3s ease;box-shadow:var(--shadow-md)}
@keyframes slideIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}

/* badges & status */
.badge{display:inline-block;padding:.35rem .85rem;border-radius:999px;font-size:.8rem;font-weight:600;margin-bottom:.75rem;letter-spacing:.02em}
.badge-notes{background:linear-gradient(135deg,var(--primary),var(--primary-light));color:#fff;box-shadow:0 0 15px rgba(109,40,217,.3)}
.badge-gk{background:linear-gradient(135deg,var(--secondary),#0891B2);color:#fff;box-shadow:0 0 15px rgba(6,182,212,.3)}
.status-signed-in{background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.3);color:var(--success);padding:.5rem 1rem;border-radius:8px;font-size:.9rem;margin-top:1rem}
.status-signed-out{background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:var(--danger);padding:.5rem 1rem;border-radius:8px;font-size:.9rem;margin-top:1rem}

/* radios/spinner/misc */
.stRadio > div{background:transparent!important}
.stRadio > div[role="radiogroup"]{gap:1rem}
.stSpinner > div{border-color:var(--primary-light)!important}
.stSuccess,.stError,.stWarning{border-radius:12px;padding:1rem;margin:1rem 0}

/* scrollbar */
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:var(--bg-secondary)}
::-webkit-scrollbar-thumb{background:var(--primary);border-radius:5px}
::-webkit-scrollbar-thumb:hover{background:var(--primary-light)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.8}}
.stButton > button:disabled{animation:pulse 2s ease-in-out infinite}
</style>
""", unsafe_allow_html=True)

# ---------------------------- auth helpers ----------------------------
def _save_token(tok: dict):
    ss.auth = {
        "access_token": tok.get("access_token"),
        "refresh_token": tok.get("refresh_token"),
        "token_type": tok.get("token_type", "bearer"),
        "expires_in": tok.get("expires_in"),
        "user": tok.get("user") or {},
        "raw": tok,
    }

def is_signed_in() -> bool:
    return bool(ss.auth.get("access_token"))

def bearer() -> str | None:
    tok = ss.auth.get("access_token")
    return f"Bearer {tok}" if tok else None

def sign_in(email: str, password: str) -> dict:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("Missing Supabase credentials.")
    url = f"{SUPABASE_URL}/auth/v1/token"
    params = {"grant_type": "password"}
    headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    body = {"email": email, "password": password}
    r = requests.post(url, params=params, headers=headers, json=body, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(r.text)
    data = r.json()
    _save_token(data)
    return data

def sign_up(email: str, password: str) -> dict:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("Missing Supabase credentials.")
    url = f"{SUPABASE_URL}/auth/v1/signup"
    headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    body = {"email": email, "password": password}
    r = requests.post(url, headers=headers, json=body, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError(r.text)
    return r.json()

def sign_out():
    ss.auth = {}

# ---------------------------- API helpers -----------------------------
def _headers(extra: dict | None = None) -> dict:
    h = {"Accept": "application/json"}
    if extra: h.update(extra)
    tok = bearer()
    if tok: h["Authorization"] = tok
    return h

def _get(path: str, timeout: int = 30):
    r = requests.get(f"{API_URL}{path}", headers=_headers(), timeout=timeout)
    if r.status_code >= 400: raise RuntimeError(r.text)
    return r.json()

def _post_json(path: str, payload: dict, timeout: int = 60):
    r = requests.post(f"{API_URL}{path}", headers=_headers({"Content-Type":"application/json"}), json=payload, timeout=timeout)
    if r.status_code >= 400: raise RuntimeError(r.text)
    return r.json()

def _post_files(path: str, files: dict, timeout: int = 120):
    r = requests.post(f"{API_URL}{path}", headers=_headers(), files=files, timeout=timeout)
    if r.status_code >= 400: raise RuntimeError(r.text)
    return r.json()

def _delete(path: str, timeout: int = 30):
    r = requests.delete(f"{API_URL}{path}", headers=_headers(), timeout=timeout)
    if r.status_code >= 400: raise RuntimeError(r.text)
    try: return r.json()
    except Exception: return {}

def _from_notes_badge(ans: str) -> str:
    s = (ans or "").lower().strip()
    return ('<span class="badge badge-gk">General Knowledge</span>'
            if s.startswith("i couldn't find an answer in your notes") else
            '<span class="badge badge-notes">From Your Notes</span>')

# ---------------------------- sidebar ----------------------------
with st.sidebar:
    st.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    st.markdown("<h3 class='sidebar-title'>Authentication</h3>", unsafe_allow_html=True)

    # non-empty label + collapsed + default index (removes warning & ghost row)
    try:
        mode = st.radio("Mode", ["Sign in", "Sign up"], horizontal=True,
                        key="auth_mode", label_visibility="collapsed", index=0)
    except TypeError:
        mode = st.radio("Mode", ["Sign in", "Sign up"], horizontal=True,
                        key="auth_mode", label_visibility="collapsed", index=0)

    email = st.text_input("Email", placeholder="you@example.com", key="auth_email")
    password = st.text_input("Password", type="password", placeholder="••••••••", key="auth_password")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Sign in", use_container_width=True, disabled=not email or not password):
            try:
                sign_in(email, password)
                st.success("Welcome back!")
            except Exception as e:
                st.error(f"{str(e)}")
    with col2:
        if st.button("Sign up", use_container_width=True, disabled=not email or not password):
            try:
                sign_up(email, password)
                st.success("Check your email to confirm!")
            except Exception as e:
                st.error(f"{str(e)})")

    if is_signed_in():
        user_email = ss.auth.get('user', {}).get('email', email)
        st.markdown(f"<div class='status-signed-in'>✓ {user_email}</div>", unsafe_allow_html=True)
        if st.button("Sign out", use_container_width=True):
            sign_out(); ss.last_answer=None; ss.library=[]; ss.uploading=False; ss.q_input=""; ss.uploader_key += 1; _rerun()
    else:
        st.markdown("<div class='status-signed-out'>Not signed in</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Library
    st.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    st.markdown("<h3 class='sidebar-title'>Your Library</h3>", unsafe_allow_html=True)

    if not is_signed_in():
        st.info("Sign in to manage your documents")
    else:
        try:
            data = _get("/docs")
            ss.library = (data.get("docs") if isinstance(data, dict) and "docs" in data else data) or []
        except Exception as e:
            st.error(f"Could not load documents: {e}"); ss.library = []

        if not ss.library:
            st.info("No documents uploaded yet")
        else:
            for d in ss.library:
                doc_id = d.get("id") or d.get("doc_id") or d.get("document_id")
                if not doc_id: continue
                fn = d.get("filename") or d.get("name") or "(file)"
                size = d.get("byte_size") or d.get("size") or d.get("bytes") or 0
                created = d.get("created_at") or d.get("uploaded_at") or d.get("timestamp") or ""
                st.markdown(f"""
                    <div class='doc-item'>
                        <div class='doc-name'>{fn}</div>
                        <div class='doc-meta'>{size:,} bytes • {created[:10] if created else 'Unknown date'}</div>
                    </div>
                """, unsafe_allow_html=True)
                if st.button("Remove", key=f"del_{doc_id}", use_container_width=True):
                    try:
                        _delete(f"/docs/{doc_id}"); st.toast("Document deleted successfully!"); _rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------- main content ----------------------------
# Hero
st.markdown("""
    <div class='hero-section'>
        <h1 class='hero-title'>Notes Copilot</h1>
        <p class='hero-subtitle'>Transform your documents into intelligent conversations. Upload your notes and get instant, accurate answers powered by AI.</p>
    </div>
""", unsafe_allow_html=True)

# Columns
col1, col2 = st.columns([1, 1])

# Upload Section
with col1:
    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='card-title'>Upload Documents</h2>", unsafe_allow_html=True)
    st.markdown("<p class='card-subtitle'>Support for PDF, Markdown, and Text files (up to 200MB)</p>", unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Drop your file here or click to browse",
        type=["pdf", "md", "txt"],
        label_visibility="collapsed",
        key=f"uploader_{ss.uploader_key}"
    )

    if st.button("Upload File", use_container_width=True, disabled=ss.uploading):
        if not is_signed_in():
            st.warning("Please sign in to upload documents")
        elif not uploaded_file:
            st.warning("Please select a file to upload")
        else:
            ss.uploading = True
            with st.spinner("Processing your document..."):
                try:
                    res = _post_files("/upload", {
                        "file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")
                    })
                    st.success(f"Successfully uploaded **{res.get('filename')}** ({res.get('chunks', 0)} chunks processed)")
                    _rerun()
                except Exception as e:
                    st.error(f"Upload failed: {str(e)}")
                finally:
                    ss.uploading = False
    st.markdown("</div>", unsafe_allow_html=True)

# Q&A Section
with col2:
    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
    st.markdown("<h2 class='card-title'>Ask Questions</h2>", unsafe_allow_html=True)
    st.markdown("<p class='card-subtitle'>Get intelligent answers from your uploaded documents</p>", unsafe_allow_html=True)

    question = st.text_input("Your question", placeholder="e.g., What are the key findings in the research paper?", key="q_input")

    if st.button("Get Answer", type="primary", use_container_width=True):
        if not is_signed_in():
            st.warning("Please sign in to ask questions")
        elif not question or not question.strip():
            st.warning("Please enter a question")
        else:
            with st.spinner("Analyzing your documents..."):
                try:
                    data = _post_json("/ask", {"q": question, "k": 5, "enrich": True, "warm": True}, timeout=60)
                    answer = (data.get("answer") or "").strip()
                    ss.last_answer = answer
                    st.markdown(_from_notes_badge(answer), unsafe_allow_html=True)
                    st.markdown(f"<div class='answer-box'>{answer}</div>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # Only show previous answer if we're not currently displaying a new one
    elif is_signed_in() and ss.last_answer:
        st.markdown(_from_notes_badge(ss.last_answer), unsafe_allow_html=True)
        st.markdown(f"<div class='answer-box'>{ss.last_answer}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)