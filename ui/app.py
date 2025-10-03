# ui/app.py
from __future__ import annotations

import io
import os
import json
import requests
import streamlit as st

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
API_URL = st.secrets.get("API_URL", os.getenv("API_URL", "http://localhost:8000")).rstrip("/")
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", "")).rstrip("/")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", os.getenv("SUPABASE_ANON_KEY", ""))

DOCS_CACHE_KEY = "docs_cache"
DOCS_WARN_KEY = "docs_warn_before_delete"

if "auth" not in st.session_state:
    st.session_state["auth"] = {}

# -----------------------------------------------------------------------------
# Auth helpers
# -----------------------------------------------------------------------------
def _save_token(tok: dict):
    st.session_state["auth"] = {
        "access_token": tok.get("access_token"),
        "refresh_token": tok.get("refresh_token"),
        "token_type": tok.get("token_type", "bearer"),
        "expires_in": tok.get("expires_in"),
        "raw": tok,
    }

def is_signed_in() -> bool:
    return bool(st.session_state.get("auth", {}).get("access_token"))

def bearer() -> str | None:
    tok = st.session_state.get("auth", {}).get("access_token")
    return f"Bearer {tok}" if tok else None

def sign_in(email: str, password: str) -> dict:
    """
    Supabase password login:
      POST {SUPABASE_URL}/auth/v1/token?grant_type=password
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY")

    url = f"{SUPABASE_URL}/auth/v1/token"
    params = {"grant_type": "password"}           # <- must be in query string
    headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    body = {"email": email, "password": password}

    r = requests.post(url, params=params, headers=headers, json=body, timeout=20)
    if r.status_code != 200:
        try:
            err = r.json()
        except Exception:
            err = {"message": r.text}
        raise RuntimeError(f"Login failed ({r.status_code}): {err}")

    data = r.json()
    _save_token(data)
    return data

def sign_out():
    st.session_state.pop("auth", None)

# -----------------------------------------------------------------------------
# API helpers
# -----------------------------------------------------------------------------
def _attach_auth(headers: dict | None = None) -> dict:
    headers = headers.copy() if headers else {}
    tok = bearer()
    if tok:
        headers["Authorization"] = tok
    return headers

def api_get(path: str, **kwargs) -> requests.Response:
    url = f"{API_URL}{path}"
    headers = _attach_auth(kwargs.pop("headers", None))
    return requests.get(url, headers=headers, timeout=30, **kwargs)

def api_post(path: str, **kwargs) -> requests.Response:
    url = f"{API_URL}{path}"
    headers = _attach_auth(kwargs.pop("headers", None))
    return requests.post(url, headers=headers, timeout=120, **kwargs)

def api_delete(path: str, **kwargs) -> requests.Response:
    url = f"{API_URL}{path}"
    headers = _attach_auth(kwargs.pop("headers", None))
    return requests.delete(url, headers=headers, timeout=30, **kwargs)

def get_json_relaxed(path_candidates: list[str], **kwargs):
    """
    Try several paths (first that succeeds), return parsed JSON or (status, text) on error.
    """
    last = None
    for p in path_candidates:
        r = api_get(p, **kwargs)
        last = r
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return {"error": "Non-JSON response from API", "body": r.text}
    # no success
    try:
        body = last.json()
    except Exception:
        body = last.text
    return {"status": last.status_code, "error": body}


def _rerun_app():
    rerun_fn = getattr(st, 'rerun', None) or getattr(st, 'experimental_rerun', None)
    if rerun_fn:
        rerun_fn()


# -----------------------------------------------------------------------------
# UI building blocks
# -----------------------------------------------------------------------------
def render_auth_sidebar():
    st.sidebar.markdown("## Account")
    mode = st.sidebar.radio("Auth mode", ["Sign in", "Sign up"], horizontal=True, index=0, key="auth_mode")

    email = st.sidebar.text_input("Email", value=st.session_state.get("last_email", ""), key="email")
    password = st.sidebar.text_input("Password", type="password", key="password")

    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button("Sign in", use_container_width=True):
            try:
                sign_in(email, password)
                st.session_state["last_email"] = email
                st.sidebar.success("Signed in.")
            except Exception as e:
                st.sidebar.error(str(e))
    with c2:
        if st.button("Sign out", use_container_width=True):
            sign_out()
            st.sidebar.info("Signed out.")

    if is_signed_in():
        st.sidebar.success("You are signed in and the access token is loaded.")
    else:
        st.sidebar.warning("Signed out. No access token loaded.")

    st.sidebar.caption(f"API={API_URL} • Supabase={SUPABASE_URL or '—'}")

def render_header():
    st.title("Notes Copilot — Login + Persistent Library")

def render_upload():
    st.markdown("### Upload")
    file = st.file_uploader("Drag and drop file here", type=["pdf", "md", "txt"], accept_multiple_files=False)
    if not file:
        return

    st.write(f"**Selected:** {file.name} — {file.size/1024:.1f}KB")
    if st.button("Ingest", disabled=not is_signed_in()):
        try:
            files = {"file": (file.name, file.getbuffer(), file.type or "application/octet-stream")}
            r = api_post("/upload", files=files)
            if r.status_code == 200:
                st.success(json.dumps(r.json(), indent=2))
                st.session_state.pop(DOCS_CACHE_KEY, None)
                _rerun_app()
            elif r.status_code == 409:
                st.warning("That document is already uploaded.")
            else:
                try:
                    st.error(json.dumps(r.json(), indent=2))
                except Exception:
                    st.error(f"{r.status_code} {r.text}")
        except Exception as e:
            st.error(str(e))

def _fetch_documents() -> list[dict]:
    data = get_json_relaxed(["/docs"])
    if isinstance(data, dict) and data.get("status") not in (None, 200):
        raise RuntimeError(data)
    if isinstance(data, dict):
        return [data]
    return data or []


def render_documents():
    st.markdown("### Your documents")

    if not is_signed_in():
        st.info("Sign in to view your uploaded files.")
        st.session_state.pop(DOCS_CACHE_KEY, None)
        return

    docs_cache = st.session_state.get(DOCS_CACHE_KEY)
    warn_default = st.session_state.get(DOCS_WARN_KEY, True)

    warn_choice = st.checkbox(
        "Warn before removing",
        value=warn_default,
        key="chk_docs_warn",
        help="Ask for confirmation before deleting a document",
    )
    st.session_state[DOCS_WARN_KEY] = warn_choice

    if docs_cache is None:
        try:
            docs_cache = _fetch_documents()
            st.session_state[DOCS_CACHE_KEY] = docs_cache
        except Exception as exc:
            st.error(f"Fetch failed: {exc}")
            return

    docs = docs_cache or []
    if not docs:
        st.info("No documents yet. Upload something!")
        return

    def _delete_doc(doc_id: int) -> bool:
        try:
            resp = api_delete(f"/docs/{doc_id}")
        except Exception as exc:
            st.error(str(exc))
            return False
        if resp.status_code == 404:
            st.session_state[DOCS_CACHE_KEY] = [
                d for d in st.session_state.get(DOCS_CACHE_KEY, []) if d.get("doc_id") != doc_id
            ]
            return True
        if resp.status_code not in (200, 204):
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            st.error(f"Delete failed ({resp.status_code}): {detail}")
            return False
        st.session_state[DOCS_CACHE_KEY] = [
            d for d in st.session_state.get(DOCS_CACHE_KEY, []) if d.get("doc_id") != doc_id
        ]
        return True

    for item in docs:
        doc_id = item.get("doc_id")
        if doc_id is None:
            continue
        title = item.get("filename") or "untitled"
        size = item.get("byte_size")
        created = item.get("created_at") or "(time unavailable)"
        pending_key = f"pending_delete_{doc_id}"

        info_col, action_col = st.columns([12, 1])
        with info_col:
            st.markdown(f"**{title}**  \
Size: {size or 'unknown'} bytes  \
Uploaded: {created}")
        with action_col:
            if st.button("X", key=f"btn_del_{doc_id}", help="Remove this document", use_container_width=True):
                if warn_choice:
                    st.session_state[pending_key] = True
                else:
                    if _delete_doc(int(doc_id)):
                        _rerun_app()

        if warn_choice and st.session_state.get(pending_key):
            st.warning(f"Remove {title}? This action cannot be undone.")
            confirm_col, cancel_col = st.columns([1, 1])
            with confirm_col:
                if st.button("Delete", key=f"btn_confirm_del_{doc_id}", use_container_width=True):
                    if _delete_doc(int(doc_id)):
                        st.session_state.pop(pending_key, None)
                        _rerun_app()
            with cancel_col:
                if st.button("Keep", key=f"btn_cancel_del_{doc_id}", use_container_width=True):
                    st.session_state.pop(pending_key, None)
                    _rerun_app()


def render_ask():
    st.markdown("### Ask about your notes here")
    q = st.text_input("Question", key="ask_q").strip()
    k = st.slider("Snippets to use", min_value=1, max_value=8, value=5, key="ask_k")

    # Optional knobs to control enrichment/tone (if your backend supports them)
    col1, col2 = st.columns(2)
    with col1:
        enrich = st.checkbox("Allow outside info (web/Gemini)", value=True, key="ask_enrich")
    with col2:
        warm = st.checkbox("Warm & welcoming tone", value=True, key="ask_warm")

    if st.button("Ask", disabled=not is_signed_in()):
        payload = {"q": q, "k": k, "enrich": enrich, "warm": warm}
        try:
            r = api_post("/ask", json=payload)
            if r.status_code != 200:
                try:
                    st.error(f"Ask failed ({r.status_code}): {r.json()}")
                except Exception:
                    st.error(f"Ask failed ({r.status_code}): {r.text}")
                return
            data = r.json()
            answer = data.get("answer") or data  # fallback if backend returns plain text/json
            st.markdown("**Answer**")
            if isinstance(answer, str):
                st.write(answer)
            else:
                st.write(json.dumps(answer, indent=2))

            cites = data.get("citations") or data.get("snippets")
            if cites:
                with st.expander("Snippets used"):
                    for i, c in enumerate(cites, 1):
                        st.markdown(f"**{i}. {c.get('filename','file')} — p.{c.get('page','?')}**")
                        t = (c.get("text") or "").strip()
                        st.write(t if len(t) < 1000 else t[:1000] + "…")
        except Exception as e:
            st.error(str(e))

# -----------------------------------------------------------------------------
# Page layout
# -----------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Notes Copilot", page_icon="🗂️", layout="wide")
    render_auth_sidebar()
    render_header()

    # Quick status row
    st.caption(f"Signed in as **{st.session_state.get('last_email','(not signed in)')}** · "
               f"API={API_URL} · Supabase={SUPABASE_URL or '—'}")

    st.divider()
    render_upload()
    st.divider()
    render_documents()
    st.divider()
    render_ask()

if __name__ == "__main__":
    main()










