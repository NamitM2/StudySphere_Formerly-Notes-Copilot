// web/src/App.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { loadToken, loadUserEmail, signIn, signUp, signOut, getAuthHeader, handleEmailVerification } from "./lib/auth";
import { postFile, postJSON, getJSON, delJSON, setUnauthorizedHandler } from "./lib/api";
import IDEPage from "./pages/IDEPage";
import LoadingLogo from "./components/LoadingLogo";
import LandingPage from "./components/LandingPage";
import { Analytics } from "@vercel/analytics/react";

export default function App() {
  // ---- navigation state ----
  const [currentPage, setCurrentPage] = useState("notes"); // "notes" or "ide"

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
  const [showLibrary, setShowLibrary] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [libError, setLibError] = useState("");

  // ---- auth ui ----
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [pwd, setPwd] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState(""); // For displaying token expiration

  // ---- toast notifications ----
  const [toast, setToast] = useState(null);

  const fileRef = useRef(null);
  const dropRef = useRef(null);

  // Show toast notification
  const showToast = (message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000); // Auto-dismiss after 4 seconds
  };

  // Ensure dark mode is always active
  useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);

  // Set up automatic sign-out on 401 errors
  useEffect(() => {
    const handleUnauthorized = async () => {
      await signOut();
      setToken("");
      setUserEmail("");
      showToast("Your session has expired. Please sign in again.", "error");
    };

    setUnauthorizedHandler(handleUnauthorized);
  }, []);

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
      setAuthError(""); // Clear auth error on success
    } catch (e) {
      const errorMsg = String(e?.message || e);
      setLibError(errorMsg);
      setDocs([]);
      // Check if it's an auth error
      if (errorMsg.includes("token") || errorMsg.includes("401") || errorMsg.includes("Unauthorized")) {
        setAuthError("Session expired - please sign in again");
      }
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
  const doSignIn = async (emailParam, pwdParam) => {
    setAuthBusy(true);
    try {
      // Use passed parameters if available (from LandingPage), otherwise use state
      const emailToUse = emailParam || email.trim();
      const pwdToUse = pwdParam || pwd;

      await signIn(emailToUse, pwdToUse);
      setToken(loadToken());
      setUserEmail(loadUserEmail());
      setEmail(""); setPwd("");
      showToast("Successfully signed in!");
      // Don't call refreshDocs here - it will be called automatically when the app renders
    } catch (e) {
      showToast(`Sign in failed: ${e?.message || e}`, "error");
      throw e; // Re-throw for LandingPage to handle
    } finally {
      setAuthBusy(false);
    }
  };

  const doSignUp = async (emailParam, pwdParam) => {
    setAuthBusy(true);
    try {
      // Use passed parameters if available (from LandingPage), otherwise use state
      const emailToUse = emailParam || email.trim();
      const pwdToUse = pwdParam || pwd;

      await signUp(emailToUse, pwdToUse);
      showToast("Check your email to confirm your account.", "info");
    } catch (e) {
      showToast(`Sign up failed: ${e?.message || e}`, "error");
      throw e; // Re-throw for LandingPage to handle
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
      setAuthError(""); // Clear auth error on success
    } catch (e) {
      console.error("Failed to load history:", e);
      setHistory([]);
      const errorMsg = String(e?.message || e);
      // Check if it's an auth error
      if (errorMsg.includes("token") || errorMsg.includes("401") || errorMsg.includes("Unauthorized")) {
        setAuthError("Session expired - please sign in again");
      }
    } finally {
      setLoadingHistory(false);
    }
  };

  // ---------- ask ----------
  async function handleAsk() {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) return;

    // Client-side validation for question length
    if (trimmedQuestion.length < 3) {
      showToast("Question too short (minimum 3 characters)", "error");
      return;
    }

    setAsking(true); setAnswer(""); setHasSourceCitations(false); setPdfSources([]); setAnswerMode("model_only"); setNotesPart(""); setEnrichmentPart("");
    try {
      const data = await postJSON("/ask", { q: question, k: 5, enrich: true, warm: true }, authedHeaders);
      setAnswer((data?.answer || "").trim());
      // Check if answer came from user's notes (has citations)
      const citations = data?.citations || [];
      setHasSourceCitations(citations.length > 0);
      setPdfSources(data?.pdf_sources || []);
      // Use backend mode if provided, otherwise infer from citations
      const backendMode = data?.mode;
      const inferredMode = citations.length > 0 ? "notes_only" : "model_only";
      console.log("[DEBUG] Backend response:", { backendMode, citations: citations.length, inferredMode, answer: data?.answer?.substring(0, 100) });
      setAnswerMode(backendMode || inferredMode);
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

  // If on IDE page, show IDE component
  if (currentPage === "ide") {
    return <IDEPage />;
  }

  // Show landing page if not signed in
  if (!isSignedIn) {
    return (
      <>
        <LandingPage onSignIn={doSignIn} onSignUp={doSignUp} />
        <Analytics />

        {/* Toast notifications */}
        {toast && (
          <div className={`fixed bottom-6 right-6 px-6 py-4 rounded-lg shadow-2xl border-2 z-50 animate-slideIn ${
            toast.type === "error"
              ? "bg-red-950 border-red-800 text-red-200"
              : toast.type === "info"
              ? "bg-blue-950 border-blue-800 text-blue-200"
              : "bg-green-950 border-green-800 text-green-200"
          }`}>
            <div className="flex items-center gap-3">
              <span className="text-lg">
                {toast.type === "error" ? "❌" : toast.type === "info" ? "ℹ️" : "✅"}
              </span>
              <p className="font-medium">{toast.message}</p>
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="min-h-screen bg-black">
      {/* Header */}
      <header className="border-b border-rose-950/50 bg-black/90 backdrop-blur-sm sticky top-0 z-50">
        <div className="mx-auto max-w-7xl px-6 py-5">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <img src="/favicon.svg" alt="StudySphere" className="w-10 h-10" />
              <div className="text-2xl font-bold bg-gradient-to-r from-amber-500 to-pink-400 bg-clip-text text-transparent">
                StudySphere
              </div>
            </div>

            {/* Navigation */}
            <div className="flex gap-2 ml-4">
              <button
                onClick={() => setCurrentPage("notes")}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  currentPage === "notes"
                    ? "bg-rose-500 text-white"
                    : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                Notes
              </button>
              <button
                onClick={() => setCurrentPage("ide")}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  currentPage === "ide"
                    ? "bg-rose-500 text-white"
                    : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                Assignments
              </button>
            </div>

            {/* Signed-in status pill */}
            <div
              className={`ml-4 flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-all duration-300 ${
                isSignedIn
                  ? "bg-rose-950/60 text-rose-400 border border-rose-900/60"
                  : "bg-red-950/50 text-red-400 border border-red-800/50"
              }`}
            >
              <div className={`w-2 h-2 rounded-full ${isSignedIn ? "bg-rose-400 animate-pulse" : "bg-red-400"}`} />
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
            <section className="bg-zinc-950 border border-rose-950/40 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent">Authentication</h3>
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
                            ? "bg-rose-500 text-black shadow-lg shadow-rose-500/25"
                            : "bg-zinc-900 text-zinc-400 border border-zinc-800 hover:bg-zinc-800 hover:text-zinc-300"
                        }`}
                        onClick={() => setMode(m)}
                      >
                        {m === "signin" ? "Sign In" : "Sign Up"}
                      </button>
                    ))}
                  </div>

                  <input
                    className="w-full px-4 py-3 mb-3 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-500 focus:border-amber-700/50 focus:ring-2 focus:ring-amber-700/20 outline-none transition-all duration-200"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                  <input
                    className="w-full px-4 py-3 mb-4 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-500 focus:border-amber-700/50 focus:ring-2 focus:ring-amber-700/20 outline-none transition-all duration-200"
                    placeholder="Password"
                    type="password"
                    value={pwd}
                    onChange={(e) => setPwd(e.target.value)}
                  />

                  <button
                    className="w-full py-3 rounded-lg font-medium transition-all duration-300 bg-gradient-to-r from-orange-500 via-amber-500 to-pink-500 text-white hover:from-rose-400 hover:via-amber-400 hover:to-amber-400 disabled:opacity-50 disabled:cursor-default shadow-lg shadow-rose-600/25 hover:shadow-rose-600/40 hover:scale-[1.02] active:scale-[0.98]"
                    disabled={authBusy || !email || !pwd}
                    onClick={mode === "signin" ? doSignIn : doSignUp}
                  >
                    {authBusy ? "Processing..." : mode === "signin" ? "Sign In" : "Create Account"}
                  </button>
                </>
              ) : (
                <div className="space-y-2">
                  <div className="text-rose-400 font-medium">{userEmail}</div>
                  {authError ? (
                    <div className="text-red-400 text-sm font-medium">{authError}</div>
                  ) : (
                    <div className="text-zinc-500 text-sm">Ready to upload and analyze documents</div>
                  )}
                </div>
              )}
            </section>

            {/* Library Card */}
            <section className="bg-zinc-950 border border-rose-950/40 rounded-2xl p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-semibold bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent">Document Library</h3>
                <div className="flex gap-2">
                  <button
                    className="text-xs px-3 py-1.5 rounded-lg bg-rose-950/50 text-amber-400 border border-rose-800/30 hover:bg-rose-950/70 hover:border-amber-700/50 transition-all duration-200 disabled:opacity-50 flex items-center gap-2 min-h-[28px]"
                    onClick={refreshDocs}
                    disabled={loadingDocs || !isSignedIn}
                    title={!isSignedIn ? "Sign in to refresh" : "Refresh"}
                  >
                    {loadingDocs ? <LoadingLogo size="xs" /> : "Refresh"}
                  </button>
                  <button
                    onClick={() => setShowLibrary(!showLibrary)}
                    disabled={!isSignedIn}
                    className="text-xs px-3 py-1.5 rounded-lg bg-rose-950/50 text-amber-400 border border-rose-800/30 hover:bg-rose-950/70 hover:border-amber-700/50 transition-all duration-200 disabled:opacity-50"
                  >
                    {showLibrary ? "Hide" : "Show"}
                  </button>
                </div>
              </div>

              {!isSignedIn ? (
                <div className="text-zinc-500 text-sm">Sign in to access your library</div>
              ) : showLibrary ? (
                libError ? (
                  <div className="text-red-400 text-sm whitespace-pre-wrap">{libError}</div>
                ) : docs.length === 0 ? (
                  <div className="text-zinc-500 text-sm">No documents yet. Upload your first file!</div>
                ) : (
                  <ul className="space-y-2 max-h-80 overflow-y-auto">
                    {docs.map((d) => (
                      <li
                        key={d.doc_id || d.id}
                        className="group rounded-lg border border-zinc-800 bg-zinc-900/50 p-2.5 hover:bg-zinc-900 hover:border-rose-900/40 transition-all duration-200"
                      >
                        <div className="flex items-start gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-zinc-200 text-sm truncate">{d.filename || d.name}</div>
                            <div className="text-zinc-500 text-xs mt-0.5">
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
                )
              ) : (
                <div className="text-zinc-500 text-sm">Click "Show" to view your documents</div>
              )}
            </section>

            {/* Question History */}
            <section className="bg-zinc-950 border border-rose-950/40 rounded-2xl p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-semibold bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent">Question History</h3>
                <div className="flex gap-2">
                  <button
                    className="text-xs px-3 py-1.5 rounded-lg bg-rose-950/50 text-amber-400 border border-rose-800/30 hover:bg-rose-950/70 hover:border-amber-700/50 transition-all duration-200 disabled:opacity-50 flex items-center gap-2 min-h-[28px]"
                    onClick={refreshHistory}
                    disabled={loadingHistory || !isSignedIn}
                    title={!isSignedIn ? "Sign in to view history" : "Refresh"}
                  >
                    {loadingHistory ? <LoadingLogo size="xs" /> : "Refresh"}
                  </button>
                  <button
                    onClick={() => {
                      if (!showHistory) {
                        // Load history when showing
                        refreshHistory();
                      }
                      setShowHistory(!showHistory);
                    }}
                    disabled={!isSignedIn}
                    className="text-xs px-3 py-1.5 rounded-lg bg-rose-950/50 text-amber-400 border border-rose-800/30 hover:bg-rose-950/70 hover:border-amber-700/50 transition-all duration-200 disabled:opacity-50"
                  >
                    {showHistory ? "Hide" : "Show"}
                  </button>
                </div>
              </div>

              {!isSignedIn ? (
                <div className="text-zinc-500 text-sm">Sign in to view your question history</div>
              ) : showHistory ? (
                loadingHistory ? (
                  <div className="flex items-center justify-center py-8">
                    <LoadingLogo size="lg" />
                  </div>
                ) : history.length === 0 ? (
                  <div className="text-zinc-500 text-sm">No questions asked yet. Ask your first question above!</div>
                ) : (
                  <ul className="space-y-2 max-h-80 overflow-y-auto">
                    {history.map((item) => (
                      <li
                        key={item.id}
                        className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-2.5 hover:bg-zinc-900 hover:border-rose-900/40 transition-all duration-200"
                      >
                        <div className="flex items-start gap-2.5">
                          <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gradient-to-br from-orange-500 to-amber-500 flex items-center justify-center">
                            <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clipRule="evenodd" />
                            </svg>
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-zinc-300 font-medium text-sm mb-0.5 truncate">{item.question}</div>
                            <div className="text-zinc-500 text-xs mb-1 line-clamp-2">{item.answer}</div>
                            <div className="flex items-center gap-1.5 text-xs text-zinc-600">
                              <span>{new Date(item.created_at).toLocaleDateString()}</span>
                              {item.citations && item.citations.length > 0 && (
                                <>
                                  <span>•</span>
                                  <span className="text-rose-500">{item.citations.length} citation{item.citations.length !== 1 ? 's' : ''}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )
              ) : (
                <div className="text-zinc-500 text-sm">Click "Show" to view your question history</div>
              )}
            </section>
          </aside>

          {/* Main Content */}
          <div className="space-y-6">
            {/* Hero */}
            <section className="relative rounded-2xl bg-gradient-to-br from-rose-950/60 via-pink-950/50 to-amber-900/60 p-6 border border-rose-950/40">
              <div className="relative">
                <h1 className="text-3xl font-bold bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent leading-relaxed">
                  Intelligent Document Analysis
                </h1>
                <p className="mt-2 text-base bg-gradient-to-r from-rose-400/80 via-amber-400/90 to-amber-400/90 bg-clip-text text-transparent">
                  Upload your documents and unlock insights with Sphere-powered answers
                </p>
              </div>
            </section>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 items-end">
              {/* Upload Card */}
              <section className="bg-zinc-950 border border-rose-950/40 rounded-2xl p-5">
                <h2 className="text-xl font-bold bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent mb-1.5">Upload Documents</h2>
                <p className="text-sm text-zinc-500 mb-3.5">PDF, Markdown, or Text files (max 200MB)</p>

                <div
                  ref={dropRef}
                  onDragEnter={handleDragEnter}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`relative border-2 border-dashed rounded-xl p-3 text-center transition-all duration-300 ${
                    isDragging ? "border-amber-600 bg-rose-950/30" : "border-zinc-800 bg-zinc-900/30 hover:border-rose-900/60 hover:bg-zinc-900/50"
                  } ${!isSignedIn ? "opacity-50 pointer-events-none" : ""}`}
                >
                  {file ? (
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5 flex-1 min-w-0">
                        <svg className="w-7 h-7 text-rose-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                        </svg>
                        <div className="text-left flex-1 min-w-0">
                          <p className="text-sm font-medium text-amber-400 truncate">{file.name}</p>
                          <p className="text-xs text-zinc-500">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                        </div>
                      </div>
                      <button
                        onClick={() => setFile(null)}
                        className="ml-2 text-zinc-400 hover:text-zinc-200 transition-colors flex-shrink-0"
                      >
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                        </svg>
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      <p className="text-zinc-300 font-medium text-sm">{isDragging ? "Drop your file here" : "Drag & drop or"}</p>
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
                        className="px-4 py-1.5 rounded-lg bg-gradient-to-r from-orange-500 to-amber-500 text-white text-sm font-medium hover:from-rose-400 hover:to-amber-400 transition-all duration-300 shadow-lg shadow-rose-500/25 hover:scale-[1.05] active:scale-[0.95]"
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
                  className="mt-2.5 w-full py-2.5 rounded-lg font-medium bg-gradient-to-r from-orange-500 via-amber-500 to-pink-500 text-white hover:from-rose-400 hover:via-amber-400 hover:to-amber-400 disabled:opacity-50 disabled:cursor-default transition-all duration-300 shadow-lg shadow-rose-600/20 hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-2 min-h-[42px]"
                >
                  {uploading ? <LoadingLogo size="sm" /> : "Upload File"}
                </button>
              </section>

              {/* Q&A Card */}
              <section className="bg-zinc-950 border border-rose-950/40 rounded-2xl p-5 h-fit">
                <h2 className="text-xl font-bold bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent mb-1.5">Ask Questions</h2>
                <p className="text-sm text-zinc-500 mb-3.5">Get Sphere-powered insights from your documents</p>

                <textarea
                  className="w-full h-20 px-3.5 py-2.5 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-500 focus:border-rose-700/50 focus:ring-2 focus:ring-rose-700/20 outline-none transition-all duration-200 resize-none text-sm"
                  placeholder='e.g., "What are the key findings?" or "Summarize the main arguments..."'
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  disabled={!isSignedIn}
                />

                <button
                  onClick={handleAsk}
                  disabled={asking || !question.trim() || !isSignedIn}
                  className="mt-2.5 w-full py-2.5 rounded-lg font-medium bg-gradient-to-r from-orange-500 via-amber-500 to-pink-500 text-white hover:from-rose-400 hover:via-amber-400 hover:to-amber-400 disabled:opacity-50 disabled:cursor-default transition-all duration-300 shadow-lg shadow-rose-600/20 hover:shadow-rose-600/40 hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-2 min-h-[42px]"
                >
                  {asking ? <LoadingLogo size="sm" /> : "Get Answer"}
                </button>
              </section>
            </div>

            {/* Answer section */}
            {answer && (
              <div className={`rounded-2xl border p-5 ${
                answerMode === "notes_only"
                  ? "border-amber-900/40 bg-amber-950/30"
                  : answerMode === "model_only"
                  ? "border-pink-900/40 bg-pink-950/30"
                  : "border-orange-900/40 bg-gradient-to-br from-amber-950/30 via-orange-950/20 to-pink-950/30"
              }`}>
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  {/* Mode tags */}
                  {answerMode === "notes_only" && (
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-amber-900/40 text-amber-400 border border-amber-700/50">
                      From Notes
                    </span>
                  )}
                  {answerMode === "model_only" && (
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-pink-900/40 text-pink-400 border border-pink-700/50">
                      Model Knowledge
                    </span>
                  )}
                  {answerMode === "mixed" && (
                    <>
                      <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-amber-900/40 text-amber-400 border border-amber-700/50">
                        From Notes
                      </span>
                      <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-pink-900/40 text-pink-400 border border-pink-700/50">
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
                    <div className="text-zinc-300 whitespace-pre-wrap leading-relaxed">
                      {notesPart}
                    </div>
                    <div className="text-zinc-300 whitespace-pre-wrap leading-relaxed">
                      {enrichmentPart}
                    </div>
                  </div>
                ) : (
                  <div className="text-zinc-300 whitespace-pre-wrap leading-relaxed">{answer}</div>
                )}
              </div>
            )}

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
              : "bg-rose-950/90 border-rose-800/50 text-amber-200"
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
      <Analytics />
    </div>
  );
}
