// web/src/App.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { loadToken, loadUserEmail, signIn, signUp, signOut, getAuthHeader } from "./lib/auth";
import { postFile, postJSON, getJSON } from "./lib/api";

// Only needed for DELETE helper
const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
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

  // ---- library state ----
  const [docs, setDocs] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [libError, setLibError] = useState("");

  // ---- auth ui ----
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [pwd, setPwd] = useState("");
  const [authBusy, setAuthBusy] = useState(false);

  const fileRef = useRef(null);
  const dropRef = useRef(null);

  // ---------- docs ----------
  const refreshDocs = async () => {
    if (!loadToken()) {
      setDocs([]);
      return;
    }
    setLibError("");
    setLoadingDocs(true);
    try {
      // Hits: http://127.0.0.1:8000/api/docs
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
    } catch (e) {
      alert(`Sign in failed: ${e?.message || e}`);
    } finally {
      setAuthBusy(false);
    }
  };
  const doSignUp = async () => {
    setAuthBusy(true);
    try {
      await signUp(email.trim(), pwd);
      alert("Check your email to confirm your account.");
    } catch (e) {
      alert(`Sign up failed: ${e?.message || e}`);
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

    // Type/size guard
    const allowedTypes = ["application/pdf", "text/markdown", "text/plain"];
    const allowedExtensions = [".pdf", ".md", ".txt"];
    if (!(allowedTypes.includes(file.type) || allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext)))) {
      alert("Please select a PDF, Markdown (.md), or Text (.txt) file.");
      return;
    }
    const maxSize = 200 * 1024 * 1024;
    if (file.size > maxSize) {
      alert(`File size (${(file.size / (1024 * 1024)).toFixed(1)}MB) exceeds the 200MB limit.`);
      return;
    }

    setUploading(true);
    try {
      const res = await postFile("/upload", { file }, authedHeaders);
      alert(`Uploaded: ${res?.filename || file.name} (${res?.chunks ?? 0} chunks)`);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      await refreshDocs();
    } catch (e) {
      alert(`Upload failed: ${e?.message || e}`);
    } finally {
      setUploading(false);
    }
  }

  // ---------- ask ----------
  async function handleAsk() {
    if (!question.trim()) return;
    setAsking(true); setAnswer("");
    try {
      const data = await postJSON("/ask", { q: question, k: 5, enrich: true, warm: true }, authedHeaders);
      setAnswer((data?.answer || "").trim());
    } catch (e) {
      setAnswer(`Error: ${e?.message || e}`);
    } finally {
      setAsking(false);
    }
  }

  // ---------- delete doc ----------
  async function handleDeleteDoc(doc_id) {
    if (!confirm("Delete this document and its chunks?")) return;
    try {
      // Hits: http://127.0.0.1:8000/api/docs/{id}
      await delJSON(`/docs/${doc_id}`, authedHeaders);
      setDocs(prev => prev.filter(d => (d.doc_id || d.id) !== doc_id));
    } catch (e) {
      alert(`Delete failed: ${e?.message || e}`);
    }
  }

  return (
    <div className="min-h-screen bg-black">
      {/* Header */}
      <header className="border-b border-emerald-900/30 bg-black/90 backdrop-blur-sm sticky top-0 z-50">
        <div className="mx-auto max-w-7xl px-6 py-5">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-emerald-600 rounded-lg flex items-center justify-center shadow-lg shadow-emerald-500/20">
                <span className="text-black font-bold text-lg">N</span>
              </div>
              <div className="text-2xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-300 bg-clip-text text-transparent">
                Notes Copilot
              </div>
            </div>

            {/* Signed-in status pill */}
            <div
              className={`ml-4 flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-all duration-300 ${
                isSignedIn
                  ? "bg-emerald-950/50 text-emerald-400 border border-emerald-800/50"
                  : "bg-red-950/50 text-red-400 border border-red-800/50"
              }`}
            >
              <div className={`w-2 h-2 rounded-full ${isSignedIn ? "bg-emerald-400 animate-pulse" : "bg-red-400"}`} />
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
            <section className="bg-zinc-950 border border-emerald-900/20 rounded-2xl p-6 shadow-2xl shadow-emerald-500/5 hover:shadow-emerald-500/10 transition-shadow duration-500">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-emerald-300">Authentication</h3>
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
                            ? "bg-emerald-600 text-black shadow-lg shadow-emerald-500/25"
                            : "bg-zinc-900 text-zinc-400 border border-zinc-800 hover:bg-zinc-800 hover:text-zinc-300"
                        }`}
                        onClick={() => setMode(m)}
                      >
                        {m === "signin" ? "Sign In" : "Sign Up"}
                      </button>
                    ))}
                  </div>

                  <input
                    className="w-full px-4 py-3 mb-3 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-500 focus:border-emerald-600/50 focus:ring-2 focus:ring-emerald-600/20 outline-none transition-all duration-200"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                  <input
                    className="w-full px-4 py-3 mb-4 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-500 focus:border-emerald-600/50 focus:ring-2 focus:ring-emerald-600/20 outline-none transition-all duration-200"
                    placeholder="Password"
                    type="password"
                    value={pwd}
                    onChange={(e) => setPwd(e.target.value)}
                  />

                  <button
                    className="w-full py-3 rounded-lg font-medium transition-all duration-200 bg-gradient-to-r from-emerald-600 to-emerald-500 text-black hover:from-emerald-500 hover:to-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-emerald-500/25 hover:shadow-emerald-500/40"
                    disabled={authBusy || !email || !pwd}
                    onClick={mode === "signin" ? doSignIn : doSignUp}
                  >
                    {authBusy ? "Processing..." : mode === "signin" ? "Sign In" : "Create Account"}
                  </button>
                </>
              ) : (
                <div className="space-y-2">
                  <div className="text-emerald-400 font-medium">{userEmail}</div>
                  <div className="text-zinc-500 text-sm">Ready to upload and analyze documents</div>
                </div>
              )}
            </section>

            {/* Library Card */}
            <section className="bg-zinc-950 border border-emerald-900/20 rounded-2xl p-6 shadow-2xl shadow-emerald-500/5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-emerald-300">Document Library</h3>
                <button
                  className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors duration-200 disabled:opacity-50"
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
                      className="group rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 hover:bg-zinc-900 hover:border-emerald-800/30 transition-all duration-200"
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
            <section className="relative rounded-3xl bg-gradient-to-br from-emerald-950/50 via-zinc-950 to-emerald-950/30 p-8 pt-9 pb-12 border border-emerald-900/20 shadow-2xl">
              <div className="absolute inset-0 bg-gradient-to-br from-emerald-600/10 via-transparent to-emerald-500/5" />
              <div className="relative">
                <h1 className="text-4xl font-bold bg-gradient-to-r from-emerald-400 via-emerald-300 to-green-400 bg-clip-text text-transparent leading-[1.15]">
                  Intelligent Document Analysis
                </h1>
                <p className="mt-3 text-lg text-zinc-400">
                  Upload your documents and unlock insights with AI-powered question answering
                </p>
              </div>
            </section>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {/* Upload Card */}
              <section className="bg-zinc-950 border border-emerald-900/20 rounded-2xl p-6 shadow-2xl shadow-emerald-500/5">
                <h2 className="text-2xl font-bold text-emerald-300 mb-2">Upload Documents</h2>
                <p className="text-sm text-zinc-500">PDF, Markdown, or Text files (max 200MB)</p>
                <p className="text-xs text-zinc-600 mt-1">
                  Larger files (100–200MB) may take a bit longer to process after upload.
                </p>

                <div
                  ref={dropRef}
                  onDragEnter={handleDragEnter}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`mt-6 relative border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 ${
                    isDragging ? "border-emerald-500 bg-emerald-950/20" : "border-zinc-800 bg-zinc-900/30 hover:border-emerald-800/50 hover:bg-zinc-900/50"
                  } ${!isSignedIn ? "opacity-50 pointer-events-none" : ""}`}
                >
                  <div className="space-y-4">
                    <div className="w-16 h-16 mx-auto rounded-full bg-emerald-950/50 flex items-center justify-center">
                      <svg className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-zinc-300 font-medium">{isDragging ? "Drop your file here" : "Drag & drop your file here"}</p>
                      <p className="text-zinc-500 text-sm mt-1">or</p>
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
                      className="px-6 py-2.5 rounded-lg bg-emerald-600 text-black font-medium hover:bg-emerald-500 transition-all duration-200 shadow-lg shadow-emerald-500/25"
                      disabled={!isSignedIn}
                    >
                      Browse Files
                    </button>
                  </div>
                </div>

                {file && (
                  <div className="mt-4 p-3 rounded-lg bg-emerald-950/30 border border-emerald-800/30 flex items-center justify-between">
                    <span className="text-sm text-emerald-300 truncate flex-1">{file.name}</span>
                    <button onClick={() => setFile(null)} className="ml-2 text-zinc-500 hover:text-zinc-300">×</button>
                  </div>
                )}

                <button
                  onClick={handleUpload}
                  disabled={!file || uploading || !isSignedIn}
                  className="mt-4 w-full py-3 rounded-lg font-medium bg-gradient-to-r from-emerald-600 to-emerald-500 text-black hover:from-emerald-500 hover:to-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-emerald-500/25"
                >
                  {uploading ? "Uploading..." : "Upload File"}
                </button>
              </section>

              {/* Q&A Card */}
              <section className="bg-zinc-950 border border-emerald-900/20 rounded-2xl p-6 shadow-2xl shadow-emerald-500/5">
                <h2 className="text-2xl font-bold text-emerald-300 mb-2">Ask Questions</h2>
                <p className="text-sm text-zinc-500 mb-6">Get AI-powered insights from your documents</p>

                <textarea
                  className="w-full h-32 px-4 py-3 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-500 focus:border-emerald-600/50 focus:ring-2 focus:ring-emerald-600/20 outline-none transition-all duration-200 resize-none"
                  placeholder='e.g., "What are the key findings in this document?" or "Summarize the main arguments..."'
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  disabled={!isSignedIn}
                />

                <button
                  onClick={handleAsk}
                  disabled={asking || !question.trim() || !isSignedIn}
                  className="mt-4 w-full py-3 rounded-lg font-medium bg-gradient-to-r from-emerald-600 to-emerald-500 text-black hover:from-emerald-500 hover:to-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-emerald-500/25"
                >
                  {asking ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Analyzing...
                    </span>
                  ) : "Get Answer"}
                </button>

                {answer && (
                  <div className="mt-6 rounded-lg border border-emerald-800/30 bg-emerald-950/20 p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                      <span className="text-xs text-emerald-400 font-medium">AI Response</span>
                    </div>
                    <div className="text-zinc-300 whitespace-pre-wrap leading-relaxed">{answer}</div>
                  </div>
                )}
              </section>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

