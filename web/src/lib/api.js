// web/src/lib/api.js
const API_BASE = (
  window.__API_BASE ||
  import.meta.env.VITE_API_URL ||
  "https://notes-copilot.onrender.com/api"
).replace(/\/$/, "");

function joinURL(base, path) {
  const left = base.replace(/\/$/, "");
  const right = path.startsWith("/") ? path : `/${path}`;
  return left + right;
}

async function parseJsonResponse(resp, url) {
  const ct = resp.headers.get("content-type") || "";
  const text = await resp.text();

  if (!resp.ok) {

    // Check for token expiry (401 with specific message)
    if (resp.status === 401) {
      try {
        const errorData = JSON.parse(text);
        if (errorData.detail && errorData.detail.includes("legacy token")) {
          throw new Error("Login expired, please log in again");
        }
      } catch (e) {
        // If JSON parsing fails or no specific message, still show friendly message for 401
        if (e.message === "Login expired, please log in again") {
          throw e;
        }
        throw new Error("Login expired, please log in again");
      }
    }

    throw new Error(`HTTP ${resp.status} ${resp.statusText} from ${url}\n${text.slice(0, 400)}`);
  }
  if (!ct.includes("application/json")) {
    throw new Error(`Expected JSON but got '${ct}' from ${url}\n${text.slice(0, 200)}`);
  }
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`Invalid JSON from ${url}: ${e.message}`);
  }
}

export async function getJSON(path, opts = {}) {
  const url = joinURL(API_BASE, path);
  const headers = { Accept: "application/json", ...(opts.headers || {}) };
  const resp = await fetch(url, { ...opts, headers, credentials: "include" });
  resp.requestMethod = "GET";
  return parseJsonResponse(resp, url);
}

export async function postJSON(path, body, headers = {}) {
  const url = joinURL(API_BASE, path);
  const resp = await fetch(url, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body ?? {}),
    credentials: "include",
  });
  resp.requestMethod = "POST";
  return parseJsonResponse(resp, url);
}

export async function postFile(path, { file, fieldName = "file", extra = {} } = {}, headers = {}) {
  if (!file) throw new Error("postFile: missing file");
  const url = joinURL(API_BASE, path);
  const fd = new FormData();
  fd.append(fieldName, file, file.name);
  // attach any extra fields you may need (e.g., doc title)
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));

  // Important: do NOT set Content-Type; the browser will add the proper multipart boundary
  const resp = await fetch(url, {
    method: "POST",
    headers: { ...headers }, // e.g., Authorization
    body: fd,
    credentials: "include",
  });
  resp.requestMethod = "POST";
  return parseJsonResponse(resp, url);
}

