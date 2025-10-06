// web/src/Header.jsx
// Path: web/src/Header.jsx
import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { loadUserEmail, loadToken, signOut } from './lib/auth';

export default function Header({ manualToken, onManualTokenChange }) {
  const loc = useLocation();
  const nav = useNavigate();
  const email = loadUserEmail();
  const hasToken = !!loadToken();

  return (
    <header className="border-b border-white/10 bg-neutral-900">
      <div className="mx-auto max-w-6xl px-4 py-4 flex items-center gap-4">
        <Link to="/" className="text-xl font-bold">Notes Copilot</Link>

        <nav className="flex items-center gap-4 text-sm">
          {/* Library link removed */}
          {!hasToken && (
            <Link
              to="/login"
              className={loc.pathname === '/login' ? 'underline' : 'hover:underline'}
            >
              Sign in
            </Link>
          )}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          {email && <span className="text-sm opacity-80">{email}</span>}
          {hasToken && (
            <button
              onClick={async () => { await signOut(); nav('/'); }}
              className="px-3 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700"
            >
              Sign out
            </button>
          )}
          {/* Dev helper: manual bearer box */}
          <input
            className="w-72 rounded-lg bg-neutral-800 border border-white/10 px-3 py-2 text-sm placeholder:text-neutral-400 outline-none focus:ring-2 focus:ring-violet-500"
            placeholder="Bearer token (optional)"
            value={manualToken}
            onChange={(e) => onManualTokenChange(e.target.value)}
          />
        </div>
      </div>
    </header>
  );
}
