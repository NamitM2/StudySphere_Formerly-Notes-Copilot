# ui/app.py
# ---------------------------------------------------------------------
# Notes Copilot — Streamlit UI (safe rerun, robust upload, debug contexts)
# ---------------------------------------------------------------------
from __future__ import annotations
import os, json, hashlib, time
from typing import Any, Dict, List, Optional, Tuple
import requests
import streamlit as st

DEFAULT_API_URL = os.getenv("API_URL") or st.secrets.get("API_URL") or "http://localhost:8000"
PAGE_TITLE = "Notes Copilot"
st.set_page_config(page_title=PAGE_TITLE, page_icon="🗂️", layout="wide")

# --------- safe rerun helper (works on old/new Streamlit) ----------
def safe_rerun():
    """
    Prefer st.rerun() (new), fall back to experimental if present.
    If neither exists (very old version), do nothing.
    """
    try:
        if hasattr(st, "rerun"):
            st.rerun()
        elif hasattr(st, "experimental_rerun"):
            st.experimental_rerun()  # type: ignore[attr-defined]
    except Exception:
        # Don't crash the app if rerun isn't available
        pass

# ------------------------------
# Session State
# ------------------------------
def _init_state():
    ss = st.session_state
    ss.setdefault("api_url", DEFAULT_API_URL)
    ss.setdefault("jwt", "")
    ss.setdefault("user_email", "")
    ss.setdefault("last_file_fp", None)
    ss.setdefault("folders", [])
    ss.setdefault("folder_id", None)
    ss.setdefault("debug_mode", False)
    ss.setdefault("history", [])
    ss.setdefault("supports_folders", None)
    ss.setdefault("supports_list_docs", None)
_init_state()

# ------------------------------
# HTTP client
# ------------------------------
@st.cache_resource
def get_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    s.timeout = 120
    return s

def _headers() -> Dict[str, str]:
    h = {}
    if st.session_state.jwt:
        h["Authorization"] = f"Bearer {st.session_state.jwt.strip()}"
    return h

def api_get(path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Dict], Optional[str]]:
    try:
        r = get_client().get(st.session_state.api_url.rstrip("/") + path, params=params, headers=_headers(), timeout=120)
        if r.status_code == 404: return None, "404"
        r.raise_for_status()
        return (r.json() if r.content and "application/json" in r.headers.get("content-type","") else {}), None
    except Exception as e:
        return None, str(e)

def api_post_json(path: str, body: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[str]]:
    try:
        r = get_client().post(st.session_state.api_url.rstrip("/") + path, json=body, headers=_headers(), timeout=120)
        if r.status_code == 404: return None, "404"
        r.raise_for_status()
        return (r.json() if r.content else {}), None
    except Exception as e:
        return None, str(e)

def api_post_file(path: str, files: Dict[str, Any], data: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Dict], Optional[str]]:
    try:
        r = get_client().post(st.session_state.api_url.rstrip("/") + path, files=files, data=data or {}, headers=_headers(), timeout=300)
        if r.status_code == 404: return None, "404"
        r.raise_for_status()
        return (r.json() if r.content else {}), None
    except Exception as e:
        return None, str(e)

def api_delete(path: str) -> Optional[str]:
    try:
        r = get_client().delete(st.session_state.api_url.rstrip("/") + path, headers=_headers(), timeout=120)
        if r.status_code == 404: return "404"
        r.raise_for_status()
        return None
    except Exception as e:
        return str(e)

# ------------------------------
# Utilities
# ------------------------------
def file_fingerprint(upload: "UploadedFile") -> str:
    b = upload.getvalue()
    sha1 = hashlib.sha1(b).hexdigest()
    return f"{upload.name}:{len(b)}:{sha1}"

def show_contexts(contexts: List[Any]):
    if not contexts:
        st.info("No contexts returned.")
        return
    for i, c in enumerate(contexts, 1):
        with st.expander(f"Context {i}"):
            if isinstance(c, dict): st.json(c)
            else: st.write(c)

def detect_features():
    if st.session_state.supports_folders is None:
        _, err = api_get("/v1/folders")
        st.session_state.supports_folders = (err is None)
    if st.session_state.supports_list_docs is None:
        _, err2 = api_get("/v1/documents")
        st.session_state.supports_list_docs = (err2 is None)

def refresh_folders():
    if not st.session_state.supports_folders:
        st.session_state.folders = []; st.session_state.folder_id = None; return
    data, err = api_get("/v1/folders")
    if err is None and isinstance(data, dict):
        st.session_state.folders = data.get("folders", data.get("data", [])) or []
        ids = {f.get("id") for f in st.session_state.folders}
        if st.session_state.folder_id not in ids: st.session_state.folder_id = None
    else:
        st.session_state.folders = []; st.session_state.folder_id = None

# ------------------------------
# Sidebar — Settings & Upload
# ------------------------------
with st.sidebar:
    st.title("⚙️ Settings")
    st.text_input("API URL", key="api_url")
    st.text_input("User email (optional)", key="user_email")
    st.text_input("JWT (optional)", key="jwt", type="password")

    st.divider(); st.caption("Feature detection")
    if st.button("Probe API features", use_container_width=True):
        detect_features(); refresh_folders(); st.success("Probed API."); safe_rerun()
    if st.session_state.supports_folders is None or st.session_state.supports_list_docs is None:
        detect_features()
        if st.session_state.supports_folders: refresh_folders()

    st.divider(); st.header("📁 Add a document")
    if st.session_state.supports_folders:
        cols = st.columns([3,1])
        with cols[0]:
            opts = ["(No folder)"] + [f.get("name", f.get("id","folder")) for f in st.session_state.folders]
            chosen = st.selectbox("Folder", options=opts, index=0)
            if chosen == "(No folder)": st.session_state.folder_id = None
            else:
                idx = opts.index(chosen) - 1
                if 0 <= idx < len(st.session_state.folders):
                    st.session_state.folder_id = st.session_state.folders[idx].get("id")
        with cols[1]:
            if st.button("↻", help="Refresh folders"): refresh_folders(); safe_rerun()
        with st.popover("➕ New folder"):
            with st.form("new_folder_form", clear_on_submit=True):
                new_name = st.text_input("Folder name")
                if st.form_submit_button("Create") and new_name.strip():
                    data, err = api_post_json("/v1/folders", {"name": new_name.strip()})
                    if err: st.error(f"Create failed: {err}")
                    else: st.success("Folder created."); refresh_folders(); time.sleep(0.2); safe_rerun()

    with st.form("upload_form", clear_on_submit=False):
        up = st.file_uploader("Upload PDF", type=["pdf"], key="uploader")
        submit_up = st.form_submit_button("Add to index")
    if submit_up and up:
        fp = file_fingerprint(up)
        if fp == st.session_state.last_file_fp:
            st.info("That exact file is already indexed in this session.")
        else:
            with st.spinner("Indexing document…"):
                files = {"file": (up.name, up.getvalue(), "application/pdf")}
                data = {}
                if st.session_state.supports_folders and st.session_state.folder_id:
                    data["folder_id"] = st.session_state.folder_id
                resp, err = api_post_file("/v1/documents", files=files, data=data)
                if err == "404": resp, err = api_post_file("/v1/upload", files=files, data=data)
                if err: st.error(f"Upload failed: {err}")
                else:
                    st.session_state.last_file_fp = fp
                    st.success("Document added to index.")
                    # refresh the doc list pane if available
                    try: api_get("/v1/documents")
                    except Exception: pass
                    safe_rerun()

    st.divider(); st.header("🧹 Maintenance")
    if st.button("Clear ALL documents (THIS USER)", use_container_width=True):
        err = api_delete("/v1/documents")
        if err == "404": st.warning("DELETE /v1/documents not available.")
        elif err: st.error(f"Clear failed: {err}")
        else: st.success("Cleared."); st.session_state.last_file_fp = None; safe_rerun()

    st.toggle("Debug mode (show contexts)", key="debug_mode")

# ------------------------------
# Main — Search & Results
# ------------------------------
st.title("🗂️ Notes Copilot")

if st.session_state.supports_list_docs:
    with st.expander("📄 Documents (from API)"):
        docs, err = api_get("/v1/documents")
        if err: st.info("Could not list documents.")
        else:
            if isinstance(docs, dict) and docs.get("documents"):
                for d in docs["documents"]:
                    st.markdown(f"- **{d.get('filename','?')}** · id=`{d.get('id','?')}` · folder=`{d.get('folder_id','')}`")
            else: st.info("No documents reported.")

st.subheader("Ask a question about your notes")
q_cols = st.columns([6,2,1])
with q_cols[0]:
    query = st.text_input("Question", placeholder="e.g., Where does Namit go to school?")
with q_cols[1]:
    enrich = st.toggle("Add outside context", value=True)
with q_cols[2]:
    go = st.button("Search", type="primary", use_container_width=True)

if go and query.strip():
    body = {"query": query.strip(), "enrich": bool(enrich)}
    if st.session_state.debug_mode: body["debug"] = True
    with st.spinner("Thinking…"):
        res, err = api_post_json("/v1/search", body)
        if err: st.error(f"Search failed: {err}")
        else:
            answer = None; contexts = None
            if isinstance(res, dict):
                answer = res.get("answer") or res.get("data", {}).get("answer") or res.get("message")
                if st.session_state.debug_mode:
                    contexts = res.get("contexts") or res.get("data", {}).get("contexts")
            st.markdown("### ✅ Answer"); st.write(answer or "No answer returned.")
            if st.session_state.debug_mode:
                st.markdown("### 🔎 Retrieved contexts"); show_contexts(contexts if isinstance(contexts, list) else [])
            st.session_state.history.insert(0, (query.strip(), answer, contexts if st.session_state.debug_mode else None))

if st.session_state.history:
    st.divider(); st.subheader("Recent questions")
    for i, (hq, ha, hc) in enumerate(st.session_state.history[:10], 1):
        with st.expander(f"{i}. {hq}"):
            st.write(ha)
            if st.session_state.debug_mode and hc:
                st.caption("Contexts snapshot:"); show_contexts(hc)

st.markdown("<hr/><small>Tip: turn on <b>Debug mode</b> to see the exact chunks retrieved.</small>", unsafe_allow_html=True)
