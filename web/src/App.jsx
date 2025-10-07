// web/src/App.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { loadToken, loadUserEmail, signIn, signUp, signOut, getAuthHeader, handleEmailVerification } from "./lib/auth";
import { postFile, postJSON, getJSON } from "./lib/api";

// Only needed for DELETE helper
const API_BASE = (
  window.__API_BASE ||
  import.meta.env.VITE_API_URL ||
  "https://notes-copilot.onrender.com/api"
).replace(/\/$/, "");
console.log("[NC] VITE_API_URL =", import.meta.env.VITE_API_URL);
console.log("[NC] API_BASE     =", API_BASE);

async function delJSON(path, headers = {}) {
  const r = await fetch(`${API_BASE}${path}`, { method: "DELETE", headers });
  if (!r.ok) throw new Error(await r.text());
  try { return await r.json(); } catch { return {}; }
}

export default function App() {
  // ---- auth state ----
  const [token, setToken] = useState(loadToken());
  const [userEmail, setUserEmail] = useState(loadUserEmail());
  const authedHeaders = useMemo(() => getAuthHeader(), [token]);
  const isSignedIn = !!token;

  // ---- upload state ----
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  // ---- Q&A state ----
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState("");
  const [hasSourceCitations, setHasSourceCitations] = useState(false);
  const [pdfSources, setPdfSources] = useState([]);
  const [answerMode, setAnswerMode] = useState("notes_only"); // "notes_only", "mixed", "model_only"
  const [notesPart, setNotesPart] = useState("");
  const [enrichmentPart, setEnrichmentPart] = useState("");

  // ---- history state ----
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // ---- library state ----
  const [docs, setDocs] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [libError, setLibError] = useState("");

  // ---- auth ui ----
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [pwd, setPwd] = useState("");
  const [authBusy, setAuthBusy] = useState(false);

  // ---- toast notifications ----
  const [toast, setToast] = useState(null);

  const fileRef = useRef(null);
  const dropRef = useRef(null);

  // Show toast notification
  const showToast = (message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000); // Auto-dismiss after 4 seconds
  };

  // ---------- docs ----------
  const refreshDocs = async () => {
    if (!loadToken()) {
      setDocs([]);
      return;
    }
    setLibError("");
    setLoadingDocs(true);
    try {
      const data = await getJSON("/docs", { headers: authedHeaders });
      setDocs(Array.isArray(data) ? data : data?.docs || []);
    } catch (e) {
      setLibError(String(e?.message || e));
      setDocs([]);
    } finally {
      setLoadingDocs(false);
    }
  };

  useEffect(() => {
    refreshDocs();
  }, [token]);

  // Handle email verification on mount
  useEffect(() => {
    (async () => {
      const result = await handleEmailVerification();
      if (result?.success) {
        setToken(loadToken());
        setUserEmail(loadUserEmail());
        showToast("Account confirmed! You're now signed in.", "success");
      } else if (result?.error) {
        showToast(`Email verification failed: ${result.error}`, "error");
      }
    })();
  }, []);

  // Clear drag highlight if drag ends outside the drop zone/window
  useEffect(() => {
    const off = () => setIsDragging(false);
    window.addEventListener("dragend", off);
    window.addEventListener("drop", off);
    return () => {
      window.removeEventListener("dragend", off);
      window.removeEventListener("drop", off);
    };
  }, []);

  // ---------- drag and drop ----------
  const handleDragEnter = (e) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true); };
  const handleDragLeave = (e) => {
    e.preventDefault(); e.stopPropagation();
    if (dropRef.current && !dropRef.current.contains(e.relatedTarget)) setIsDragging(false);
  };
  const handleDragOver = (e) => { e.preventDefault(); e.stopPropagation(); };
  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false);
    const files = [...e.dataTransfer.files];
    if (files.length > 0) {
      const droppedFile = files[0];
      const allowedTypes = ["application/pdf", "text/markdown", "text/plain"];
      const allowedExtensions = [".pdf", ".md", ".txt"];
      if (allowedTypes.includes(droppedFile.type) || allowedExtensions.some(ext => droppedFile.name.toLowerCase().endsWith(ext))) {
        setFile(droppedFile);
      } else {
        alert("Please select a PDF, Markdown (.md), or Text (.txt) file.");
      }
    }
  };

  // ---------- auth ----------
  const doSignIn = async () => {
    setAuthBusy(true);
    try {
      await signIn(email.trim(), pwd);
      setToken(loadToken());
      setUserEmail(loadUserEmail());
      setEmail(""); setPwd("");
      showToast("Successfully signed in!");
    } catch (e) {
      showToast(`Sign in failed: ${e?.message || e}`, "error");
    } finally {
      setAuthBusy(false);
    }
  };

  const doSignUp = async () => {
    setAuthBusy(true);
    try {
      await signUp(email.trim(), pwd);
      showToast("Check your email to confirm your account.", "info");
    } catch (e) {
      showToast(`Sign up failed: ${e?.message || e}`, "error");
    } finally {
      setAuthBusy(false);
    }
  };

  const doSignOut = async () => {
    try { await signOut(); } finally {
      setToken(loadToken()); setUserEmail(loadUserEmail());
      setDocs([]); setAnswer("");
    }
  };

  // ---------- upload ----------
  async function handleUpload() {
    if (!file) return;

    const allowedTypes = ["application/pdf", "text/markdown", "text/plain"];
    const allowedExtensions = [".pdf", ".md", ".txt"];
    if (!(allowedTypes.includes(file.type) || allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext)))) {
      showToast("Please select a PDF, Markdown (.md), or Text (.txt) file.", "error");
      return;
    }
    const maxSize = 200 * 1024 * 1024;
    if (file.size > maxSize) {
      showToast(`File size (${(file.size / (1024 * 1024)).toFixed(1)}MB) exceeds the 200MB limit.`, "error");
      return;
    }

    setUploading(true);
    try {
      const res = await postFile("/upload", { file }, authedHeaders);
      showToast(`Successfully uploaded ${res?.filename || file.name}`);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      await refreshDocs();
    } catch (e) {
      showToast(`Upload failed: ${e?.message || e}`, "error");
    } finally {
      setUploading(false);
    }
  }

  // ---------- history ----------
  const refreshHistory = async () => {
    if (!loadToken()) {
      setHistory([]);
      return;
    }
    setLoadingHistory(true);
    try {
      const data = await getJSON("/history?limit=50", { headers: authedHeaders });
      setHistory(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to load history:", e);
      setHistory([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  // ---------- ask ----------
  async function handleAsk() {
    if (!question.trim()) return;
    setAsking(true); setAnswer(""); setHasSourceCitations(false); setPdfSources([]); setAnswerMode("notes_only"); setNotesPart(""); setEnrichmentPart("");
    try {
      const data = await postJSON("/ask", { q: question, k: 5, enrich: true, warm: true }, authedHeaders);
      setAnswer((data?.answer || "").trim());
      // Check if answer came from user's notes (has citations)
      const citations = data?.citations || [];
      setHasSourceCitations(citations.length > 0);
      setPdfSources(data?.pdf_sources || []);
      setAnswerMode(data?.mode || "notes_only");
      setNotesPart(data?.notes_part || "");
      setEnrichmentPart(data?.enrichment_part || "");
      // Refresh history after asking a question
      await refreshHistory();
    } catch (e) {
      setAnswer(`Error: ${e?.message || e}`);
      setHasSourceCitations(false);
      setPdfSources([]);
      setAnswerMode("model_only");
    } finally {
      setAsking(false);
    }
  }

  // ---------- delete doc ----------
  async function handleDeleteDoc(doc_id) {
    if (!confirm("Delete this document and its chunks?")) return;
    try {
      await delJSON(`/docs/${doc_id}`, authedHeaders);
      setDocs(prev => prev.filter(d => (d.doc_id || d.id) !== doc_id));
      showToast("Document deleted successfully");
    } catch (e) {
      showToast(`Delete failed: ${e?.message || e}`, "error");
    }
  }

  return (
    <div className="min-h-screen bg-black">
      {/* Header */}
      <header className="border-b border-teal-950/50 bg-black/90 backdrop-blur-sm sticky top-0 z-50">
        <div className="mx-auto max-w-7xl px-6 py-5">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-teal-600 to-rose-600 rounded-lg flex items-center justify-center shadow-lg shadow-rose-600/20">
                <span className="text-white font-bold text-lg">N</span>
              </div>
              <div className="text-2xl font-bold bg-gradient-to-r from-teal-500 to-rose-500 bg-clip-text text-transparent">
                Notes Copilot
              </div>
            </div>

            {/* Signed-in status pill */}
            <div
              className={`ml-4 flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-all duration-300 ${
                isSignedIn
                  ? "bg-teal-950/60 text-teal-500 border border-teal-900/60"
                  : "bg-red-950/50 text-red-400 border border-red-800/50"
              }`}
            >
              <div className={`w-2 h-2 rounded-full ${isSignedIn ? "bg-teal-500 animate-pulse" : "bg-red-400"}`} />
              {isSignedIn ? userEmail || "Connected" : "Not Connected"}
            </div>

            <div className="ml-auto" />
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-8">
          {/* Sidebar: Auth + Library */}
          <aside className="space-y-6">
            {/* Auth Card */}
            <section className="bg-zinc-950 border border-rose-950/40 rounded-2xl p-6 shadow-2xl shadow-rose-600/5 hover:shadow-rose-600/10 transition-shadow duration-500">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold bg-gradient-to-r from-teal-400 to-rose-400 bg-clip-text text-transparent">Authentication</h3>
                {isSignedIn && (
                  <button
                    onClick={doSignOut}
                    className="text-xs px-3 py-1.5 rounded-lg bg-red-950/50 text-red-400 border border-red-800/30 hover:bg-red-950/70 hover:border-red-700/50 transition-all duration-200"
                  >
                    Sign out
                  </button>
                )}
              </div>

              {!isSignedIn ? (
                <>
                  <div className="flex gap-2 mb-4">
                    {["signin", "signup"].map((m) => (
                      <button
                        key={m}
                        className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                          mode === m
                            ? "bg-teal-700 text-black shadow-lg shadow-teal-600/25"
                            : "bg-zinc-900 text-zinc-400 border border-zinc-800 hover:bg-zinc-800 hover:text-zinc-300"
                        }`}
                        onClick={() => setMode(m)}
                      >
                        {m === "signin" ? "Sign In" : "Sign Up"}
                      </button>
                    ))}
                  </div>

                  <input
                    className="w-full px-4 py-3 mb-3 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-500 focus:border-teal-700/50 focus:ring-2 focus:ring-teal-700/20 outline-none transition-all duration-200"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                  <input
                    className="w-full px-4 py-3 mb-4 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-500 focus:border-teal-700/50 focus:ring-2 focus:ring-teal-700/20 outline-none transition-all duration-200"
                    placeholder="Password"
                    type="password"
                    value={pwd}
                    onChange={(e) => setPwd(e.target.value)}
                  />

                  <button
                    className="w-full py-3 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-teal-700 via-teal-600 to-rose-700 text-white hover:from-teal-600 hover:via-rose-600 hover:to-rose-600 disabled:opacity-50 disabled:cursor-default shadow-lg shadow-rose-600/25 hover:shadow-rose-600/40 hover:scale-[1.02] active:scale-[0.98]"
                    disabled={authBusy || !email || !pwd}
                    onClick={mode === "signin" ? doSignIn : doSignUp}
                  >
                    {authBusy ? "Processing..." : mode === "signin" ? "Sign In" : "Create Account"}
                  </button>
                </>
              ) : (
                <div className="space-y-2">
                  <div className="text-teal-500 font-medium">{userEmail}</div>
                  <div className="text-zinc-500 text-sm">Ready to upload and analyze documents</div>
                </div>
              )}
            </section>

            {/* Library Card */}
            <section className="bg-zinc-950 border border-teal-950/40 rounded-2xl p-6 shadow-2xl shadow-teal-600/5 hover:shadow-teal-600/10 transition-shadow duration-500">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold bg-gradient-to-r from-teal-400 to-rose-400 bg-clip-text text-transparent">Document Library</h3>
                <button
                  className="text-xs text-teal-500 hover:text-teal-400 transition-colors duration-200 disabled:opacity-50"
                  onClick={refreshDocs}
                  disabled={loadingDocs || !isSignedIn}
                  title={!isSignedIn ? "Sign in to refresh" : "Refresh"}
                >
                  {loadingDocs ? "Loading..." : "Refresh"}
                </button>
              </div>

              {!isSignedIn ? (
                <div className="text-zinc-500 text-sm">Sign in to access your library</div>
              ) : libError ? (
                <div className="text-red-400 text-sm whitespace-pre-wrap">{libError}</div>
              ) : docs.length === 0 ? (
                <div className="text-zinc-500 text-sm">No documents yet. Upload your first file!</div>
              ) : (
                <ul className="space-y-2 max-h-96 overflow-y-auto">
                  {docs.map((d) => (
                    <li
                      key={d.doc_id || d.id}
                      className="group rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 hover:bg-zinc-900 hover:border-teal-900/40 transition-all duration-200"
                    >
                      <div className="flex items-start gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-zinc-200 truncate">{d.filename || d.name}</div>
                          <div className="text-zinc-500 text-xs mt-1">
                            {d.byte_size ? `${(d.byte_size / (1024 * 1024)).toFixed(2)} MB` : "—"}
                            {d.created_at ? ` • ${String(d.created_at).slice(0, 10)}` : ""}
                          </div>
                        </div>
                        <button
                          onClick={() => handleDeleteDoc(d.doc_id || d.id)}
                          className="opacity-0 group-hover:opacity-100 text-xs px-2 py-1 rounded bg-red-950/50 text-red-400 border border-red-800/30 hover:bg-red-900/50 transition-all duration-200"
                        >
                          Delete
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>

          {/* Main Content */}
          <div className="space-y-8">
            {/* Hero */}
            <section className="relative rounded-3xl bg-gradient-to-br from-teal-950/60 via-zinc-950 to-rose-950/40 p-8 pt-10 pb-10 border border-teal-950/40 shadow-2xl hover:shadow-teal-600/15 transition-all duration-500 hover:border-teal-900/60 group">
              <div className="absolute inset-0 bg-gradient-to-br from-teal-700/10 via-transparent to-rose-600/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl" />
              <div className="relative">
                <h1 className="text-4xl font-bold bg-gradient-to-r from-teal-500 via-teal-400 to-rose-500 bg-clip-text text-transparent leading-relaxed pb-1">
                  Intelligent Document Analysis
                </h1>
                <p className="mt-3 text-lg text-zinc-400">
                  Upload your documents and unlock insights with AI-powered answers
                </p>
              </div>
            </section>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {/* Upload Card */}
              <section className="bg-zinc-950 border border-teal-950/40 rounded-2xl p-6 shadow-2xl shadow-teal-600/5 h-fit hover:shadow-teal-600/10 transition-shadow duration-500">
                <h2 className="text-2xl font-bold bg-gradient-to-r from-teal-400 to-rose-400 bg-clip-text text-transparent mb-2">Upload Documents</h2>
                <p className="text-sm text-zinc-500 mb-4">PDF, Markdown, or Text files (max 200MB)</p>

                <div
                  ref={dropRef}
                  onDragEnter={handleDragEnter}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`relative border-2 border-dashed rounded-xl p-4 text-center transition-all duration-300 ${
                    isDragging ? "border-teal-600 bg-teal-950/30" : "border-zinc-800 bg-zinc-900/30 hover:border-teal-900/60 hover:bg-zinc-900/50"
                  } ${!isSignedIn ? "opacity-50 pointer-events-none" : ""}`}
                >
                  {file ? (
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <svg className="w-8 h-8 text-teal-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                        </svg>
                        <div className="text-left flex-1 min-w-0">
                          <p className="text-sm font-medium text-teal-400 truncate">{file.name}</p>
                          <p className="text-xs text-zinc-500">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                        </div>
                      </div>
                      <button
                        onClick={() => setFile(null)}
                        className="ml-3 text-zinc-400 hover:text-zinc-200 transition-colors flex-shrink-0"
                      >
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                        </svg>
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div>
                        <p className="text-zinc-300 font-medium text-sm mb-2">{isDragging ? "Drop your file here" : "Drag & drop or"}</p>
                      </div>

                      <input
                        ref={fileRef}
                        type="file"
                        className="hidden"
                        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                        accept=".pdf,.md,.txt"
                        disabled={!isSignedIn}
                      />
                      <button
                        onClick={() => fileRef.current?.click()}
                        className="px-5 py-2 rounded-lg bg-gradient-to-r from-teal-700 to-teal-600 text-white font-medium hover:from-teal-600 hover:to-teal-500 transition-all duration-300 shadow-lg shadow-teal-600/25 hover:scale-[1.05] active:scale-[0.95]"
                        disabled={!isSignedIn}
                      >
                        Browse Files
                      </button>
                    </div>
                  )}
                </div>

                <button
                  onClick={handleUpload}
                  disabled={!file || uploading || !isSignedIn}
                  className="mt-3 w-full py-2.5 rounded-lg font-medium bg-gradient-to-r from-teal-700 via-teal-600 to-rose-700 text-white hover:from-teal-600 hover:via-rose-600 hover:to-rose-600 disabled:opacity-50 disabled:cursor-default transition-all duration-300 shadow-lg shadow-rose-600/20 hover:scale-[1.02] active:scale-[0.98]"
                >
                  {uploading ? "Uploading..." : "Upload File"}
                </button>
              </section>

              {/* Q&A Card */}
              <section className="bg-zinc-950 border border-rose-950/40 rounded-2xl p-6 shadow-2xl shadow-rose-600/5 h-fit hover:shadow-rose-600/10 transition-shadow duration-500">
                <h2 className="text-2xl font-bold bg-gradient-to-r from-teal-400 to-rose-400 bg-clip-text text-transparent mb-2">Ask Questions</h2>
                <p className="text-sm text-zinc-500 mb-4">Get AI-powered insights from your documents</p>

                <textarea
                  className="w-full h-24 px-4 py-3 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-500 focus:border-rose-700/50 focus:ring-2 focus:ring-rose-700/20 outline-none transition-all duration-200 resize-none text-sm"
                  placeholder='e.g., "What are the key findings?" or "Summarize the main arguments..."'
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  disabled={!isSignedIn}
                />

                <button
                  onClick={handleAsk}
                  disabled={asking || !question.trim() || !isSignedIn}
                  className="mt-3 w-full py-2.5 rounded-lg font-medium bg-gradient-to-r from-teal-700 via-teal-600 to-rose-700 text-white hover:from-teal-600 hover:via-rose-600 hover:to-rose-600 disabled:opacity-50 disabled:cursor-default transition-all duration-300 shadow-lg shadow-rose-600/20 hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
                >
                  {asking ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Analyzing...
                    </span>
                  ) : "Get Answer"}
                </button>
              </section>
            </div>

            {/* Answer section */}
            {answer && (
              <div className={`rounded-2xl border p-6 shadow-2xl transition-all duration-500 ${
                answerMode === "notes_only"
                  ? "border-teal-900/40 bg-teal-950/30 shadow-teal-600/10 hover:shadow-teal-600/20"
                  : answerMode === "model_only"
                  ? "border-rose-900/40 bg-rose-950/30 shadow-rose-600/10 hover:shadow-rose-600/20"
                  : "border-teal-900/40 bg-gradient-to-br from-teal-950/30 via-purple-950/20 to-rose-950/30 shadow-purple-600/10 hover:shadow-purple-600/20"
              }`}>
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  {/* Mode tags */}
                  {answerMode === "notes_only" && (
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-teal-900/40 text-teal-400 border border-teal-700/50">
                      From Notes
                    </span>
                  )}
                  {answerMode === "model_only" && (
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-rose-900/40 text-rose-400 border border-rose-700/50">
                      Model Knowledge
                    </span>
                  )}
                  {answerMode === "mixed" && (
                    <>
                      <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-teal-900/40 text-teal-400 border border-teal-700/50">
                        From Notes
                      </span>
                      <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-rose-900/40 text-rose-400 border border-rose-700/50">
                        Model Knowledge
                      </span>
                    </>
                  )}
                  {/* PDF source tags */}
                  {pdfSources.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {pdfSources.map((filename, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-zinc-900/60 text-zinc-400 border border-zinc-700/50"
                          title={filename}
                        >
                          <svg className="w-3 h-3 mr-1.5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                          </svg>
                          {filename.length > 30 ? filename.substring(0, 27) + '...' : filename}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {/* Display answer - for mixed mode, show parts with visual separation */}
                {answerMode === "mixed" && notesPart && enrichmentPart ? (
                  <div className="space-y-4">
                    <div className="text-zinc-300 whitespace-pre-wrap leading-relaxed p-3 rounded-lg bg-teal-950/20 border-l-2 border-teal-600/50">
                      {notesPart}
                    </div>
                    <div className="text-zinc-300 whitespace-pre-wrap leading-relaxed p-3 rounded-lg bg-rose-950/20 border-l-2 border-rose-600/50">
                      {enrichmentPart}
                    </div>
                  </div>
                ) : (
                  <div className="text-zinc-300 whitespace-pre-wrap leading-relaxed">{answer}</div>
                )}
              </div>
            )}

            {/* History Panel */}
            <section className="bg-zinc-950 border border-teal-950/40 rounded-2xl p-6 shadow-2xl shadow-teal-600/5 hover:shadow-teal-600/10 transition-shadow duration-500">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-2xl font-bold bg-gradient-to-r from-teal-400 to-rose-400 bg-clip-text text-transparent">
                  Question History
                </h2>
                <div className="flex gap-2">
                  <button
                    onClick={refreshHistory}
                    disabled={loadingHistory || !isSignedIn}
                    className="text-xs text-teal-500 hover:text-teal-400 transition-colors duration-200 disabled:opacity-50"
                    title={!isSignedIn ? "Sign in to view history" : "Refresh"}
                  >
                    {loadingHistory ? "Loading..." : "Refresh"}
                  </button>
                  <button
                    onClick={() => setShowHistory(!showHistory)}
                    disabled={!isSignedIn}
                    className="text-xs px-3 py-1.5 rounded-lg bg-teal-950/50 text-teal-400 border border-teal-800/30 hover:bg-teal-950/70 hover:border-teal-700/50 transition-all duration-200 disabled:opacity-50"
                  >
                    {showHistory ? "Hide" : "Show"}
                  </button>
                </div>
              </div>

              {!isSignedIn ? (
                <div className="text-zinc-500 text-sm">Sign in to view your question history</div>
              ) : showHistory ? (
                history.length === 0 ? (
                  <div className="text-zinc-500 text-sm">No questions asked yet. Ask your first question above!</div>
                ) : (
                  <div className="space-y-4 max-h-[600px] overflow-y-auto">
                    {history.map((item) => (
                      <div
                        key={item.id}
                        className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 hover:bg-zinc-900 hover:border-teal-900/40 transition-all duration-200"
                      >
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-teal-600 to-rose-600 flex items-center justify-center">
                            <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clipRule="evenodd" />
                            </svg>
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-zinc-300 font-medium text-sm mb-1">{item.question}</div>
                            <div className="text-zinc-500 text-xs mb-2 line-clamp-2">{item.answer}</div>
                            <div className="flex items-center gap-2 text-xs text-zinc-600">
                              <span>{new Date(item.created_at).toLocaleDateString()}</span>
                              <span>•</span>
                              <span>{new Date(item.created_at).toLocaleTimeString()}</span>
                              {item.citations && item.citations.length > 0 && (
                                <>
                                  <span>•</span>
                                  <span className="text-teal-600">{item.citations.length} citation{item.citations.length !== 1 ? 's' : ''}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              ) : (
                <div className="text-zinc-500 text-sm">Click "Show" to view your question history</div>
              )}
            </section>
          </div>
        </div>
      </main>

      {/* Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-bottom-5 fade-in duration-300">
          <div className={`rounded-lg px-6 py-4 shadow-2xl border backdrop-blur-sm max-w-md ${
            toast.type === "error"
              ? "bg-red-950/90 border-red-800/50 text-red-200"
              : toast.type === "info"
              ? "bg-blue-950/90 border-blue-800/50 text-blue-200"
              : "bg-teal-950/90 border-teal-800/50 text-teal-200"
          }`}>
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-0.5">
                {toast.type === "error" ? (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                ) : toast.type === "info" ? (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                )}
              </div>
              <div className="flex-1 font-medium text-sm">{toast.message}</div>
              <button
                onClick={() => setToast(null)}
                className="flex-shrink-0 opacity-60 hover:opacity-100 transition-opacity"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
