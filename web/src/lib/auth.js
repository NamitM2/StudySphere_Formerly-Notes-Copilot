// web/src/lib/auth.js
// Path: web/src/lib/auth.js
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, "");
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;

// ---- local storage helpers ----
function saveTokenData(data) {
  const tok = data?.access_token || "";
  localStorage.setItem("nc_token", tok);
  if (data?.user?.email) localStorage.setItem("nc_user_email", data.user.email);
  return tok;
}

export function loadToken() {
  return localStorage.getItem("nc_token") || "";
}

export function loadUserEmail() {
  return localStorage.getItem("nc_user_email") || "";
}

export function signOutLocal() {
  localStorage.removeItem("nc_token");
  localStorage.removeItem("nc_user_email");
}

// ---- Supabase calls ----
export async function signIn(email, password) {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error("Missing Supabase env vars.");
  }
  const url = `${SUPABASE_URL}/auth/v1/token?grant_type=password`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      apikey: SUPABASE_ANON_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error(await r.text());
  const data = await r.json();
  return saveTokenData(data);
}

export async function signUp(email, password) {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error("Missing Supabase env vars.");
  }
  const url = `${SUPABASE_URL}/auth/v1/signup`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      apikey: SUPABASE_ANON_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error(await r.text());
  const data = await r.json();
  if (data?.access_token) saveTokenData(data); // some projects auto-sign in
  return data;
}
// --- extras to make pages trivial ---
export function getAuthHeader() {
  const tok = loadToken();
  if (!tok) return {};
  return { Authorization: tok.startsWith('Bearer') ? tok : `Bearer ${tok}` };
}

export async function signOut() {
  // optional server revoke (best-effort); safe if you didn't implement logout endpoint
  try {
    const token = loadToken();
    const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, "");
    const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;
    if (token && SUPABASE_URL && SUPABASE_ANON_KEY) {
      await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
        method: "POST",
        headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${token}` },
      }).catch(() => {});
    }
  } finally {
    signOutLocal();
  }
}
