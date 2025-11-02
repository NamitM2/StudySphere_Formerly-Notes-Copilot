// web/src/lib/api.js
const API_BASE = (
  window.__API_BASE ||
  import.meta.env.VITE_API_URL ||
  "https://notes-copilot.onrender.com/api"
).replace(/\/$/, "");

// Global 401 handler - will be set by App.jsx
let onUnauthorized = null;

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

function joinURL(base, path) {
  const left = base.replace(/\/$/, "");
  const right = path.startsWith("/") ? path : `/${path}`;
  return left + right;
}

async function parseJsonResponse(resp, url) {
  const ct = resp.headers.get("content-type") || "";
  let text = "";

  try {
    text = await resp.text();
  } catch (e) {
    throw new Error(`Failed to read response from ${url}: ${e.message}`);
  }

  if (!resp.ok) {
    // Check for token expiry (401 - automatically sign out)
    if (resp.status === 401) {
      // Trigger automatic sign out
      if (onUnauthorized) {
        onUnauthorized();
      }
      throw new Error("Your session has expired. Please sign in again.");
    }

    throw new Error(`HTTP ${resp.status} ${resp.statusText} from ${url}\n${text.slice(0, 400)}`);
  }

  if (!ct.includes("application/json")) {
    throw new Error(`Expected JSON but got '${ct}' from ${url}\n${text.slice(0, 200)}`);
  }

  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`Invalid JSON from ${url}: ${e.message}\nResponse: ${text.slice(0, 200)}`);
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

export async function putJSON(path, body, headers = {}) {
  const url = joinURL(API_BASE, path);
  const resp = await fetch(url, {
    method: "PUT",
    headers: { Accept: "application/json", "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body ?? {}),
    credentials: "include",
  });
  resp.requestMethod = "PUT";
  return parseJsonResponse(resp, url);
}

export async function delJSON(path, headers = {}) {
  const url = joinURL(API_BASE, path);
  const resp = await fetch(url, {
    method: "DELETE",
    headers: { Accept: "application/json", ...headers },
    credentials: "include",
  });
  resp.requestMethod = "DELETE";
  return parseJsonResponse(resp, url);
}

// ==================== Worksheet API ====================

/**
 * Upload a PDF worksheet and detect fillable fields
 * @param {string} projectId - Assignment project ID
 * @param {File} pdfFile - PDF file to upload
 * @param {Object} authHeaders - Authorization headers from getAuthHeader()
 * @returns {Promise<{project_id, pdf_url, fields, page_count}>}
 */
export async function uploadWorksheet(projectId, pdfFile, authHeaders = {}) {
  const url = joinURL(API_BASE, `/ide/worksheet/upload?project_id=${projectId}`);
  const formData = new FormData();
  formData.append('file', pdfFile, pdfFile.name);

  const resp = await fetch(url, {
    method: 'POST',
    headers: { ...authHeaders },
    body: formData,
    credentials: 'include',
  });

  return parseJsonResponse(resp, url);
}

/**
 * Get worksheet fields and saved answers
 * @param {string} projectId - Assignment project ID
 * @param {Object} authHeaders - Authorization headers from getAuthHeader()
 * @returns {Promise<{project_id, pdf_url, fields, answers}>}
 */
export async function getWorksheetFields(projectId, authHeaders = {}) {
  return getJSON(`/ide/worksheet/${projectId}/fields`, { headers: authHeaders });
}

/**
 * Save worksheet field answers
 * @param {string} projectId - Assignment project ID
 * @param {Object} answers - Map of field_id -> answer
 * @param {Object} authHeaders - Authorization headers from getAuthHeader()
 * @returns {Promise<{project_id, saved_count, timestamp}>}
 */
export async function saveWorksheetAnswers(projectId, answers, authHeaders = {}) {
  return putJSON(`/ide/worksheet/${projectId}/save`, answers, authHeaders);
}

/**
 * Delete a worksheet
 * @param {string} projectId - Assignment project ID
 * @param {Object} authHeaders - Authorization headers from getAuthHeader()
 * @returns {Promise<{message}>}
 */
export async function deleteWorksheet(projectId, authHeaders = {}) {
  return delJSON(`/ide/worksheet/${projectId}`, authHeaders);
}

/**
 * Request an AI suggestion for a specific worksheet field
 * @param {string} projectId
 * @param {string} fieldId
 * @param {Object} body - { current_answer, instructions }
 * @param {Object} authHeaders
 * @returns {Promise<{project_id, field_id, suggestion, explanation, confidence}>}
 */
export async function getWorksheetFieldSuggestion(projectId, fieldId, body = {}, authHeaders = {}) {
  return postJSON(`/ide/worksheet/${projectId}/fields/${fieldId}/suggest`, body, authHeaders);
}

