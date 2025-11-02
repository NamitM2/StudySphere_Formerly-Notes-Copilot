// web/src/lib/auth.js
// Path: web/src/lib/auth.js
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, "");
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;

// Auto-login for local dev (optional - only if env vars are set)
const DEV_AUTO_LOGIN_EMAIL = import.meta.env.VITE_DEV_AUTO_LOGIN_EMAIL;
const DEV_AUTO_LOGIN_PASSWORD = import.meta.env.VITE_DEV_AUTO_LOGIN_PASSWORD;

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

  if (!r.ok) {
    const errorText = await r.text();
    try {
      const errorData = JSON.parse(errorText);
      const errorMsg = errorData?.msg || errorData?.message || errorData?.error_description || errorData?.error;

      // Provide user-friendly error message
      if (errorMsg?.toLowerCase().includes('invalid')) {
        throw new Error('Invalid email or password');
      }
      throw new Error(errorMsg || 'Sign in failed');
    } catch (e) {
      if (e.message === 'Invalid email or password' || e.message === 'Sign in failed') {
        throw e;
      }
      throw new Error('Invalid email or password');
    }
  }

  const data = await r.json();
  return saveTokenData(data);
}

export async function signUp(email, password) {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error("Missing Supabase env vars.");
  }
  const url = `${SUPABASE_URL}/auth/v1/signup`;

  // Get the current site URL for email redirect
  // Default to production URL if in production, otherwise use current origin for local dev
  const redirectTo = window.location.hostname === 'localhost'
    ? window.location.origin
    : 'https://notes-copilot.vercel.app';

  const r = await fetch(url, {
    method: "POST",
    headers: {
      apikey: SUPABASE_ANON_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      password,
      options: {
        emailRedirectTo: redirectTo
      }
    }),
  });

  const data = await r.json();

  // Check for duplicate email error in the response
  if (!r.ok) {
    const errorMsg = data?.msg || data?.message || data?.error_description || data?.error || JSON.stringify(data);
    if (errorMsg.toLowerCase().includes("already") || errorMsg.toLowerCase().includes("exist")) {
      throw new Error("Email already exists");
    }
    throw new Error(errorMsg);
  }

  // Even if r.ok is true, check if there's an error in the response body
  if (data?.error || data?.error_description) {
    const errorMsg = data.error_description || data.error;
    if (errorMsg.toLowerCase().includes("already") || errorMsg.toLowerCase().includes("exist")) {
      throw new Error("Email already exists");
    }
    throw new Error(errorMsg);
  }

  if (data?.access_token) saveTokenData(data); // some projects auto-sign in
  return data;
}

export async function signInWithGoogle() {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error("Missing Supabase env vars.");
  }

  // Get the current site URL for OAuth redirect
  const redirectTo = window.location.hostname === 'localhost'
    ? window.location.origin
    : 'https://studysphere.app'; // Use your custom domain when you have one

  // Construct the OAuth URL with additional parameters
  const oauthUrl = new URL(`${SUPABASE_URL}/auth/v1/authorize`);
  oauthUrl.searchParams.set('provider', 'google');
  oauthUrl.searchParams.set('redirect_to', redirectTo);

  // Redirect to Google OAuth
  window.location.href = oauthUrl.toString();
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

// Handle email verification callback
export async function handleEmailVerification() {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    return null;
  }

  // Check for tokens in URL hash (e.g., #access_token=...)
  const hashParams = new URLSearchParams(window.location.hash.substring(1));
  const accessToken = hashParams.get('access_token');
  const refreshToken = hashParams.get('refresh_token');

  // Also check query params (e.g., ?access_token=...)
  const queryParams = new URLSearchParams(window.location.search);
  const queryAccessToken = queryParams.get('access_token');
  const queryRefreshToken = queryParams.get('refresh_token');

  const token = accessToken || queryAccessToken;
  const refresh = refreshToken || queryRefreshToken;

  if (token) {
    // Exchange the token for user data
    try {
      const r = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
        headers: {
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${token}`,
        },
      });

      if (r.ok) {
        const user = await r.json();
        const tokenData = {
          access_token: token,
          refresh_token: refresh,
          user: user,
        };
        saveTokenData(tokenData);

        // Clean up the URL
        window.history.replaceState({}, document.title, window.location.pathname);

        return { success: true, user };
      }
    } catch (e) {
      console.error("Email verification error:", e);
      return { success: false, error: e.message };
    }
  }

  return null;
}

// Auto-login for local development
export async function autoLoginIfDev() {
  // Only auto-login if:
  // 1. We're in development (localhost)
  // 2. Not already logged in
  // 3. Dev credentials are configured
  const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  const hasToken = !!loadToken();

  if (!isLocalhost || hasToken || !DEV_AUTO_LOGIN_EMAIL || !DEV_AUTO_LOGIN_PASSWORD) {
    return false;
  }

  try {
    console.log('[DEV] Auto-logging in with dev credentials...');
    await signIn(DEV_AUTO_LOGIN_EMAIL, DEV_AUTO_LOGIN_PASSWORD);
    console.log('[DEV] Auto-login successful!');
    return true;
  } catch (error) {
    console.warn('[DEV] Auto-login failed:', error.message);
    return false;
  }
}
